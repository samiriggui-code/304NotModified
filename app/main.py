"""API de la version d'essai : un cache de réponses vérifiées pour agents."""

import hashlib
import hmac
import ipaddress
import json
import logging
import os
import time
from datetime import UTC, datetime
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field

from . import admin_auth, config
from .aliases import CONTEXT_ALIASES, DOMAIN_ALIASES, QUESTION_ALIASES
from .calc.routes import register_calc_routes
from .engine import SearchCoordinator
from .normalize import question_key
from .public import home_page, llms_text
from .resolver import (
    REASONS,
    TRANSIENT_REASONS,
    ClaudeResolver,
    FallbackResolver,
    NullResolver,
    OpenRouterResolver,
    Resolution,
    Resolver,
    official_source_count,
)
from .store import CachedAnswer, Store

log = logging.getLogger("304notmodified")


class AnswerRequest(BaseModel):
    question: str = Field(min_length=3, max_length=config.MAX_QUESTION_CHARS, validation_alias=QUESTION_ALIASES)
    domain: str | None = Field(
        default=None,
        description="Indice facultatif : " + ", ".join(sorted(config.DOMAIN_TTL_SECONDS)),
        validation_alias=DOMAIN_ALIASES,
    )
    context: str | None = Field(
        default=None,
        max_length=500,
        description="Facultatif : la tâche en cours de l'agent (sans données personnelles). Aide à améliorer le service.",
        validation_alias=CONTEXT_ALIASES,
    )


# Proxys de confiance : seuls eux peuvent ajouter une adresse à X-Forwarded-For (Traefik, le serveur
# MCP, le tableau de bord, tous sur la machine ou le réseau Docker). Même liste que le « trust proxy »
# du serveur MCP de Context7 : boucle locale, lien local, adresses privées, CGNAT.
TRUSTED_PROXIES = [
    ipaddress.ip_network(n)
    for n in (
        "127.0.0.0/8",
        "::1/128",
        "169.254.0.0/16",
        "fe80::/10",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "fc00::/7",
        "100.64.0.0/10",
    )
]


def client_address(forwarded_for: str, peer: str | None) -> str:
    """Adresse du client : on remonte X-Forwarded-For de droite à gauche et on s'arrête à la première
    adresse qui n'est pas un proxy de confiance. Un client ne peut donc pas se faire passer pour un
    autre en ajoutant une adresse en tête de l'en-tête."""
    chain = [part.strip() for part in forwarded_for.split(",") if part.strip()]
    # L'adresse de la connexion directe (Traefik, le serveur MCP…) ferme la chaîne, si c'en est une.
    try:
        if peer:
            ipaddress.ip_address(peer)
            chain.append(peer)
    except ValueError:
        pass
    for candidate in reversed(chain):
        try:
            ip = ipaddress.ip_address(candidate)
        except ValueError:
            return candidate  # valeur illisible : on la garde telle quelle, sans lui faire confiance
        if not any(ip in net for net in TRUSTED_PROXIES):
            return candidate
    return chain[0] if chain else "?"


class FeedbackRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=64)
    useful: bool = Field(description="La réponse a-t-elle aidé l'agent à accomplir sa tâche ?")
    issue: Literal[config.FEEDBACK_ISSUES] | None = None
    comment: str | None = Field(default=None, max_length=1000)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class KeyRequest(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    quota: int = Field(default=config.FREE_QUOTA, ge=1)


class SelfServiceKeyRequest(BaseModel):
    agent: str = Field(min_length=1, max_length=100, description="Nom (et version) de votre agent ou de votre outil.")
    use_case: str | None = Field(
        default=None,
        max_length=500,
        description="Facultatif : à quoi vont servir vos questions (sans données personnelles).",
    )
    contact: str | None = Field(
        default=None, max_length=200, description="Facultatif : une adresse ou une page pour vous joindre."
    )


class DailyCounter:
    """Compteur par adresse IP et par jour, en mémoire (remis à zéro au redémarrage)."""

    def __init__(self):
        self._day = ""
        self._counts: dict[str, int] = {}

    def hit(self, who: str) -> int:
        today = time.strftime("%Y-%m-%d")
        if today != self._day:
            self._day, self._counts = today, {}
        self._counts[who] = self._counts.get(who, 0) + 1
        return self._counts[who]


def default_resolver() -> Resolver:
    """Moteur de recherche selon les clés présentes : Anthropic d'abord, OpenRouter en secours (y compris
    quand Anthropic refuse, par exemple crédit épuisé), sinon aucun (les questions sont seulement enregistrées)."""
    engines: list[Resolver] = []
    if os.environ.get("ANTHROPIC_API_KEY"):
        engines.append(ClaudeResolver())
    if os.environ.get("OPENROUTER_API_KEY"):
        engines.append(OpenRouterResolver(os.environ["OPENROUTER_API_KEY"]))
    if not engines:
        return NullResolver()
    return engines[0] if len(engines) == 1 else FallbackResolver(*engines)


def create_app(store: Store | None = None, resolver: Resolver | None = None) -> FastAPI:
    store = store or Store(config.DB_PATH)
    store.purge_older_than(config.LOG_RETENTION_DAYS)
    if resolver is None:
        resolver = default_resolver()

    app = FastAPI(
        title="304NotModified",
        version="0.2.0",
        description=(
            "Réponses factuelles vérifiées, sourcées et datées, partagées entre agents IA. "
            f"Guide pour les agents : {config.PUBLIC_URL}/llms.txt"
        ),
    )
    app.state.store = store
    # Compte technique des requêtes faites sans clé (quelques questions par jour et par adresse IP).
    store.create_key("Accès sans clé", 10**12, origin="anonymous", key=config.ANON_KEY)
    anon_counter = DailyCounter()
    signup_counter = DailyCounter()
    searches = SearchCoordinator(
        config.MAX_CONCURRENT_SEARCHES,
        config.SEARCH_QUEUE_TIMEOUT_SECONDS,
        flight_timeout=config.SEARCH_QUEUE_TIMEOUT_SECONDS + config.PROVIDER_TIMEOUT_SECONDS,
    )
    app.state.searches = searches

    def client_ip(request: Request) -> str:
        return client_address(
            request.headers.get("x-forwarded-for", ""), request.client.host if request.client else None
        )

    def presented_key(request: Request) -> str:
        key = request.headers.get("x-api-key", "").strip()
        auth = request.headers.get("authorization", "")
        if not key and auth.lower().startswith("bearer "):
            key = auth[7:].strip()
        return key

    def require_key(request: Request):
        key = presented_key(request)
        if not key:
            if config.ANON_DAILY_LIMIT <= 0:
                raise HTTPException(
                    401, f"Clé d'API requise : obtenez-en une gratuitement, POST {config.PUBLIC_URL}/v1/keys."
                )
            if anon_counter.hit(client_ip(request)) > config.ANON_DAILY_LIMIT:
                raise HTTPException(
                    429,
                    f"Limite de {config.ANON_DAILY_LIMIT} questions par jour sans clé atteinte. "
                    f"Clé gratuite : POST {config.PUBLIC_URL}/v1/keys (voir {config.PUBLIC_URL}/llms.txt).",
                )
            return config.ANON_KEY
        row = store.get_key(key)
        if row is None or key == config.ANON_KEY:
            raise HTTPException(401, "Clé d'API inconnue.")
        if row["used"] >= row["quota"]:
            raise HTTPException(429, "Quota épuisé pour cette clé.")
        store.touch_key(key)
        return row["key"]

    throttle = admin_auth.LoginThrottle()

    def require_admin(authorization: str = Header(default="")):
        # Jeton fixe (scripts) ou jeton de session du tableau de bord.
        if config.ADMIN_TOKEN and hmac.compare_digest(authorization, f"Bearer {config.ADMIN_TOKEN}"):
            return "script"
        token = authorization.removeprefix("Bearer ")
        email = admin_auth.read_session_token(token, config.SESSION_SECRET) if token != authorization else None
        if email is None or email != config.ADMIN_EMAIL:
            raise HTTPException(403, "Accès administrateur requis.")
        return email

    @app.get("/health")
    def health():
        return {"status": "ok", "resolver": type(resolver).__name__}

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def home():
        return home_page()

    @app.get("/llms.txt", response_class=PlainTextResponse)
    def llms_txt():
        return llms_text()

    @app.get("/v1/domains", summary="Domaines couverts et durée de fraîcheur de leurs réponses")
    def public_domains():
        return [
            {
                "domain": d,
                "label": config.DOMAIN_LABELS.get(d, (d, ""))[0],
                "description": config.DOMAIN_LABELS.get(d, (d, ""))[1],
                "specialty": d in config.DOMAIN_GUIDANCE,
                "freshness_seconds": ttl,
            }
            for d, ttl in config.DOMAIN_TTL_SECONDS.items()
        ]

    @app.post("/v1/keys", summary="Obtenir une clé d'API gratuite (sans inscription)")
    def self_service_key(body: SelfServiceKeyRequest, request: Request):
        if signup_counter.hit(client_ip(request)) > config.SELF_SERVICE_PER_IP_PER_DAY:
            raise HTTPException(429, "Trop de clés demandées depuis cette adresse aujourd'hui.")
        if store.count_keys_since("self", time.time() - 86400) >= config.SELF_SERVICE_MAX_PER_DAY:
            raise HTTPException(429, "Trop de clés demandées aujourd'hui : réessayez demain.")
        key = store.create_key(
            body.agent.strip(),
            config.SELF_SERVICE_QUOTA,
            origin="self",
            use_case=(body.use_case or "").strip() or None,
            contact=(body.contact or "").strip() or None,
        )
        return {
            "api_key": key,
            "quota": config.SELF_SERVICE_QUOTA,
            "usage": f"En-tête X-API-Key: {key} sur POST {config.PUBLIC_URL}/v1/answer",
            "mcp": f"{config.PUBLIC_URL}/mcp (en-tête X-API-Key)",
            "note": "Gardez cette clé : elle ne sera plus affichée. Les questions sans réponse ne sont pas décomptées.",
        }

    @app.post("/v1/answer")
    def answer(
        body: AnswerRequest,
        request: Request,
        response: Response,
        api_key: str = Depends(require_key),
        x_client: str = Header(default=""),
        user_agent: str = Header(default=""),
        idempotency_key: str = Header(
            default="",
            max_length=200,
            description="Facultatif : même valeur pour les relances d'une même demande. La réponse enregistrée "
            f"est renvoyée pendant {config.IDEMPOTENCY_TTL_SECONDS // 3600} h, sans être décomptée deux fois.",
        ),
    ):
        # Idempotence (préparation de la facturation) : une relance porte la même clé et reçoit le même
        # résultat, sans nouvelle recherche ni nouveau décompte. Sans clé d'API, la portée est l'adresse IP.
        idem = None
        if idempotency_key:
            scope = api_key if api_key != config.ANON_KEY else f"{config.ANON_KEY}:{client_ip(request)}"
            fingerprint = hashlib.sha256(json.dumps(body.model_dump(), sort_keys=True).encode()).hexdigest()
            state, stored = store.idempotency_begin(
                scope, idempotency_key, fingerprint, time.time(), config.IDEMPOTENCY_TTL_SECONDS
            )
            if state == "replay":
                response.headers["Idempotent-Replayed"] = "true"
                return stored
            if state == "conflict":
                raise HTTPException(422, "Cette Idempotency-Key a déjà servi pour une autre demande.")
            if state == "pending":
                raise HTTPException(
                    409,
                    "La même demande est déjà en cours : réessayez dans quelques secondes.",
                    headers={"Retry-After": "2"},
                )
            idem = (scope, idempotency_key)

        try:
            result = serve(body, api_key, x_client, user_agent)
        except BaseException:
            if idem:
                store.idempotency_abort(*idem)
            raise
        if idem:
            # Une cause passagère (busy, timeout…) n'est pas figée : la relance tentera à nouveau.
            if result.get("retryable"):
                store.idempotency_abort(*idem)
            else:
                store.idempotency_finish(*idem, result)
        return result

    def serve(body: AnswerRequest, api_key: str, x_client: str, user_agent: str) -> dict:
        started = time.monotonic()
        now = time.time()
        key = question_key(body.question)
        hint = body.domain if body.domain in config.DOMAIN_TTL_SECONDS else None
        # Le serveur MCP s'annonce avec « mcp: » ; sinon, c'est un appel direct à l'API.
        client = (x_client or user_agent)[:200] or None
        channel = "mcp" if x_client.startswith("mcp:") else "http"

        def record(outcome, domain, *, cost_eur=0.0, version_id=None, reason=None):
            return store.log(
                api_key=api_key,
                key=key,
                question=body.question,
                domain=domain,
                outcome=outcome,
                latency_ms=int((time.monotonic() - started) * 1000),
                cost_eur=cost_eur,
                channel=channel,
                client=client,
                context=body.context,
                answer_version_id=version_id,
                reason=reason,
            )

        def serve_cached(cached: CachedAnswer) -> dict:
            store.consume(api_key)
            request_id = record("hit", cached.domain, version_id=cached.version_id)
            return _payload(cached, cached=True, request_id=request_id)

        cached = store.get_fresh(key, now)
        if cached is not None:
            return serve_cached(cached)

        # Seule la question (publique) part vers le moteur de recherche : le contexte de l'agent reste
        # dans son journal et n'influence jamais une réponse mutualisée.
        outcome = searches.resolve(key, hint or config.DEFAULT_DOMAIN, lambda: resolver.resolve(body.question, hint))
        resolution = outcome.resolution
        if outcome.shared and resolution.answer is not None:
            # Une autre requête vient de payer la recherche : on sert ce qu'elle a mis en cache.
            cached = store.get_fresh(key, time.time())
            if cached is not None:
                return serve_cached(cached)

        if resolution.answer is None:
            reason = resolution.reason or "no_reliable_answer"
            request_id = record("unanswered", resolution.domain, cost_eur=resolution.cost_eur, reason=reason)
            retryable = reason in TRANSIENT_REASONS
            return {
                "status": "unanswered",
                "request_id": request_id,
                "question": body.question,
                "cached": False,
                "reason": reason,
                "message": REASONS.get(reason, ""),
                "retryable": retryable,
                "retry_after": config.RETRY_AFTER_SECONDS if retryable else None,
                "billable": False,
            }

        fresh = CachedAnswer(
            key=key,
            question=body.question,
            domain=resolution.domain,
            answer=resolution.answer,
            sources=resolution.sources,
            confidence=resolution.confidence,
            created_at=now,
            expires_at=_expiry(now, config.DOMAIN_TTL_SECONDS[resolution.domain], resolution),
            claims=resolution.claims,
            valid_from=resolution.valid_from,
            valid_until=resolution.valid_until,
        )
        store.put(fresh)
        store.consume(api_key)
        request_id = record("miss", fresh.domain, cost_eur=resolution.cost_eur, version_id=fresh.version_id)
        return _payload(fresh, cached=False, request_id=request_id)

    # Calculs sur les bougies fournies par l'agent (repris d'IchiVol ; 304 ne fournit aucune donnée).
    register_calc_routes(app, store, require_key)

    @app.post("/v1/feedback")
    def feedback(body: FeedbackRequest, request: Request):
        # Pas de contrôle de quota : un retour ne coûte rien et ne doit jamais être refusé pour ça.
        # Sans clé, le retour porte sur une requête faite elle aussi sans clé.
        api_key = presented_key(request) or config.ANON_KEY
        if store.get_key(api_key) is None:
            raise HTTPException(401, "Clé d'API inconnue.")
        if not store.add_feedback(
            request_id=body.request_id,
            api_key=api_key,
            useful=body.useful,
            issue=body.issue,
            comment=body.comment,
        ):
            raise HTTPException(404, "Requête inconnue pour cette clé.")
        return {"status": "recorded", "request_id": body.request_id}

    @app.post("/internal/keys", dependencies=[Depends(require_admin)], include_in_schema=False)
    def create_key(body: KeyRequest):
        return {"api_key": store.create_key(body.label, body.quota), "quota": body.quota}

    # Filtre facultatif par domaine, commun aux routes du tableau de bord.
    DomainFilter = Query(default=None, max_length=40)

    @app.get("/internal/stats", dependencies=[Depends(require_admin)], include_in_schema=False)
    def stats(days: float | None = Query(default=None, gt=0, le=3650), domain: str | None = DomainFilter):
        since = time.time() - days * 86400 if days else 0.0
        return {
            **store.stats(config.PRICE_PER_REQUEST_EUR, since=since, domain=domain),
            # Calculs /v1/calc/* : comptés à part (ils ne passent ni par le cache ni par une recherche).
            "calculations": store.calc_stats(since),
        }

    @app.get("/internal/timeseries", dependencies=[Depends(require_admin)], include_in_schema=False)
    def timeseries(
        days: float = Query(default=7, gt=0, le=3650),
        bucket: Literal["hour", "day"] = "day",
        tz_offset_min: int = Query(default=0, ge=-14 * 60, le=14 * 60),
        domain: str | None = DomainFilter,
    ):
        return store.timeseries(
            since=time.time() - days * 86400,
            bucket_seconds=3600 if bucket == "hour" else 86400,
            tz_offset_seconds=tz_offset_min * 60,
            domain=domain,
        )

    @app.get("/internal/domains", dependencies=[Depends(require_admin)], include_in_schema=False)
    def domains(days: float | None = Query(default=None, gt=0, le=3650)):
        now = time.time()
        overview = store.domain_overview(now - days * 86400 if days else 0.0, now)
        rows = []
        for domain, ttl in config.DOMAIN_TTL_SECONDS.items():
            label, description = config.DOMAIN_LABELS.get(domain, (domain, ""))
            o = overview.get(domain, {})
            hit, miss = o.get("hit") or 0, o.get("miss") or 0
            rows.append(
                {
                    "domain": domain,
                    "label": label,
                    "description": description,
                    "ttl_seconds": ttl,
                    # Spécialité : le chercheur a des consignes et des sources officielles propres au domaine.
                    "specialty": domain in config.DOMAIN_GUIDANCE,
                    "requests": o.get("requests") or 0,
                    "distinct_questions": o.get("distinct_questions") or 0,
                    "hit": hit,
                    "miss": miss,
                    "unanswered": o.get("unanswered") or 0,
                    "cache_hit_rate": round(hit / (hit + miss), 3) if hit + miss else 0.0,
                    "cost_eur": round(o.get("cost_eur") or 0.0, 4),
                    "last_ts": o.get("last_ts"),
                    "answers": o.get("answers") or 0,
                    "fresh_answers": o.get("fresh_answers") or 0,
                    "served": o.get("served") or 0,
                    "feedback": o.get("feedback") or 0,
                    "useful": o.get("useful") or 0,
                }
            )
        return sorted(rows, key=lambda r: (not r["specialty"], -r["requests"], r["label"]))

    @app.get("/internal/settings", dependencies=[Depends(require_admin)], include_in_schema=False)
    def settings():
        return {
            "public_url": config.PUBLIC_URL,
            "mcp_url": f"{config.PUBLIC_URL}/mcp",
            # Recherche fraîche active seulement si un fournisseur est configuré (clé présente).
            "resolver": type(resolver).__name__,
            "search_enabled": not isinstance(resolver, NullResolver),
            "anon_daily_limit": config.ANON_DAILY_LIMIT,
            "self_service_quota": config.SELF_SERVICE_QUOTA,
            "free_quota": config.FREE_QUOTA,
            "price_per_request_eur": config.PRICE_PER_REQUEST_EUR,
            "log_retention_days": config.LOG_RETENTION_DAYS,
            "max_question_chars": config.MAX_QUESTION_CHARS,
            # Moteur : causes d'absence de réponse (libellés) et limites de recherche.
            "reasons": REASONS,
            "transient_reasons": sorted(TRANSIENT_REASONS),
            "max_concurrent_searches": config.MAX_CONCURRENT_SEARCHES,
            "provider_timeout_seconds": config.PROVIDER_TIMEOUT_SECONDS,
            "searches_in_flight": searches.in_flight(),
        }

    @app.get("/internal/keys", dependencies=[Depends(require_admin)], include_in_schema=False)
    def list_keys():
        return store.list_keys()

    @app.get("/internal/requests", dependencies=[Depends(require_admin)], include_in_schema=False)
    def recent_requests(limit: int = Query(default=50, ge=1, le=500), domain: str | None = DomainFilter):
        return store.recent_requests(limit, domain)

    @app.get("/internal/feedback", dependencies=[Depends(require_admin)], include_in_schema=False)
    def list_feedback(limit: int = Query(default=50, ge=1, le=500), domain: str | None = DomainFilter):
        return store.list_feedback(limit, domain)

    @app.get("/internal/answers", dependencies=[Depends(require_admin)], include_in_schema=False)
    def list_answers(limit: int = Query(default=50, ge=1, le=500), domain: str | None = DomainFilter):
        return store.list_answers(limit, domain)

    # Connexion du tableau de bord (front Next.js séparé, voir admin/). Les routes /internal/* ne sont
    # pas exposées sur Internet : Traefik ne les route pas, seul le front, sur le serveur, les appelle.
    @app.post("/internal/auth/login", include_in_schema=False)
    def login(body: LoginRequest, request: Request, x_forwarded_for: str = Header(default="")):
        if not (config.ADMIN_EMAIL and config.ADMIN_PASSWORD_HASH and config.SESSION_SECRET):
            raise HTTPException(503, "Connexion non configurée : ADMIN_EMAIL, ADMIN_PASSWORD_HASH, SESSION_SECRET.")
        who = client_address(x_forwarded_for, request.client.host if request.client else None)
        wait = throttle.locked_for(who)
        if wait:
            raise HTTPException(429, f"Trop d'essais : réessayez dans {wait // 60 + 1} min.")
        email = body.email.strip().lower()
        password_ok = admin_auth.verify_password(body.password, config.ADMIN_PASSWORD_HASH)
        if not (password_ok and hmac.compare_digest(email, config.ADMIN_EMAIL)):
            throttle.failure(who)
            raise HTTPException(401, "E-mail ou mot de passe incorrect.")
        throttle.success(who)
        return {
            "access_token": admin_auth.make_session_token(email, config.SESSION_SECRET),
            "expires_in": admin_auth.SESSION_TTL_SECONDS,
            "user": {"email": email},
        }

    @app.get("/internal/auth/me", include_in_schema=False)
    def me(who: str = Depends(require_admin)):
        return {"email": who}

    return app


def _day_start(iso_day: str) -> float:
    return datetime.fromisoformat(iso_day).replace(tzinfo=UTC).timestamp()


def _expiry(now: float, ttl: float, resolution: Resolution) -> float:
    """Durée de garde en mémoire : celle du domaine, raccourcie si le fait change de statut avant.

    Une règle « applicable à partir du 1er novembre » est recherchée à nouveau ce jour-là (la réponse
    parlait d'une règle à venir) ; une valeur qui cesse de s'appliquer n'est pas resservie au-delà."""
    expires = now + ttl
    for day in (resolution.valid_from, resolution.valid_until):
        if day and now < _day_start(day) < expires:
            expires = _day_start(day)
    return expires


def _in_force(a: CachedAnswer, now: float) -> bool | None:
    """Le fait décrit s'applique-t-il aujourd'hui ? None si la réponse ne donne aucune date."""
    if not (a.valid_from or a.valid_until):
        return None
    if a.valid_from and now < _day_start(a.valid_from):
        return False
    return not (a.valid_until and now >= _day_start(a.valid_until))


def _payload(a: CachedAnswer, *, cached: bool, request_id: str) -> dict:
    official = official_source_count(a.domain, a.sources)
    confidence = a.confidence
    if official == 0:
        # Même règle qu'à la recherche, appliquée aussi aux réponses déjà en mémoire avant son ajout.
        confidence = min(confidence, config.NO_OFFICIAL_SOURCE_MAX_CONFIDENCE)
    return {
        "status": "answered",
        "request_id": request_id,
        "question": a.question,
        "answer": a.answer,
        "domain": a.domain,
        "confidence": confidence,
        "sources": a.sources,
        # Nombre de sources officielles du domaine (Légifrance, impots.gouv.fr…) ; null si le domaine n'en
        # a pas de liste. 0 : seulement des sites tiers, à vérifier avant de s'y fier.
        "official_sources": official,
        # Chaque fait de la réponse avec les URL qui le justifient : vérifiable phrase par phrase.
        "claims": a.claims,
        # Période où le fait s'applique (AAAA-MM-JJ, null si inconnue) et s'il s'applique aujourd'hui.
        "valid_from": a.valid_from,
        "valid_until": a.valid_until,
        "in_force": _in_force(a, time.time()),
        "cached": cached,
        "fetched_at": a.created_at,
        "expires_at": a.expires_at,
        # Une réponse livrée est décomptée du quota (future facturation) ; une absence de réponse ne l'est jamais.
        "billable": True,
    }


app = create_app() if os.environ.get("NM304_AUTOSTART", "1") == "1" else None
