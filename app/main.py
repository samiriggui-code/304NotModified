"""API de la version d'essai : un cache de réponses vérifiées pour agents."""

import hmac
import os
import time
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from . import admin_auth, config
from .normalize import question_key
from .resolver import ClaudeResolver, NullResolver, Resolver
from .store import CachedAnswer, Store


class AnswerRequest(BaseModel):
    question: str = Field(min_length=3, max_length=config.MAX_QUESTION_CHARS)
    domain: str | None = Field(
        default=None, description="Indice facultatif : " + ", ".join(sorted(config.DOMAIN_TTL_SECONDS))
    )
    context: str | None = Field(
        default=None,
        max_length=500,
        description="Facultatif : la tâche en cours de l'agent (sans données personnelles). Aide à améliorer le service.",
    )


class FeedbackRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=64)
    useful: bool = Field(description="La réponse a-t-elle aidé l'agent à accomplir sa tâche ?")
    issue: Literal["wrong", "outdated", "incomplete", "bad_source", "other"] | None = None
    comment: str | None = Field(default=None, max_length=1000)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class KeyRequest(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    quota: int = Field(default=config.FREE_QUOTA, ge=1)


LLMS_TXT = f"""# 304NotModified (version d'essai)

> Réponses factuelles vérifiées, sourcées et datées, partagées entre agents.
> Une question déjà résolue par un autre agent est servie immédiatement depuis le cache.
> Spécialité : la facturation électronique française sous tous ses aspects (domaine « facturation ») :
> réglementation (qui, quand, obligations), technique (Factur-X, UBL, CII, normes AFNOR XP Z12-012/013/014),
> intégration (API des plateformes agréées, annuaire, Peppol) et process (statuts de cycle de vie,
> rejets, avoirs, e-reporting, archivage). Toujours avec la version et la date des sources officielles.
> Deuxième spécialité : la formation professionnelle (domaine « formation ») : Qualiopi (référentiel
> national qualité, guide de lecture, audits), CPF et EDOF, OPCO, RNCP et Répertoire spécifique.
> Aussi : impôts, finances (banque, épargne, taux réglementés), vie quotidienne (démarches, aides),
> droit en vigueur, réglementation des entreprises. Toujours à partir des sources officielles françaises
> et européennes, avec les dates d'application.
> Information générale : pas de conseil juridique, fiscal ou financier personnalisé.

## Utilisation
POST /v1/answer
En-tête : X-API-Key: <clé>
Corps JSON : {{"question": "...", "domain": "facultatif"}}
Domaines : {", ".join(sorted(config.DOMAIN_TTL_SECONDS))}

Corps JSON complet : {{"question": "...", "domain": "facultatif", "context": "facultatif : votre tâche en cours"}}
En-tête facultatif : X-Client: <nom et version de votre agent>

Réponse : status (answered | unanswered), request_id, answer, sources [url, title], confidence (0-1),
domain, cached (bool), fetched_at et expires_at (horodatages Unix).
Vérifiez vous-même les sources si l'enjeu est important : confidence est une estimation.

## Dire si la réponse vous a servi
POST /v1/feedback (même clé)
Corps JSON : {{"request_id": "...", "useful": true, "issue": "wrong | outdated | incomplete | bad_source | other",
"comment": "facultatif"}}
Votre retour est lu par l'équipe pour améliorer le service ; il ne modifie jamais directement une réponse.

## Données enregistrées
Chaque requête est enregistrée (question, contexte, réponse servie, nom de l'agent) pour améliorer
le service, puis effacée après {config.LOG_RETENTION_DAYS} jours. N'envoyez pas de données personnelles.

Documentation OpenAPI : /docs et /openapi.json
"""


def create_app(store: Store | None = None, resolver: Resolver | None = None) -> FastAPI:
    store = store or Store(config.DB_PATH)
    store.purge_older_than(config.LOG_RETENTION_DAYS)
    if resolver is None:
        resolver = ClaudeResolver() if os.environ.get("ANTHROPIC_API_KEY") else NullResolver()

    app = FastAPI(title="304NotModified", version="0.1.0")
    app.state.store = store

    def require_key(x_api_key: str = Header(default="")):
        row = store.get_key(x_api_key) if x_api_key else None
        if row is None:
            raise HTTPException(401, "Clé d'API absente ou inconnue.")
        if row["used"] >= row["quota"]:
            raise HTTPException(429, "Quota épuisé pour cette clé.")
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

    @app.get("/llms.txt", response_class=PlainTextResponse)
    def llms_txt():
        return LLMS_TXT

    @app.post("/v1/answer")
    def answer(
        body: AnswerRequest,
        api_key: str = Depends(require_key),
        x_client: str = Header(default=""),
        user_agent: str = Header(default=""),
    ):
        started = time.monotonic()
        now = time.time()
        key = question_key(body.question)
        hint = body.domain if body.domain in config.DOMAIN_TTL_SECONDS else None
        # Le serveur MCP s'annonce avec « mcp: » ; sinon, c'est un appel direct à l'API.
        client = (x_client or user_agent)[:200] or None
        channel = "mcp" if x_client.startswith("mcp:") else "http"

        def record(outcome, domain, *, cost_eur=0.0, version_id=None):
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
            )

        cached = store.get_fresh(key, now)
        if cached is not None:
            store.consume(api_key)
            request_id = record("hit", cached.domain, version_id=cached.version_id)
            return _payload(cached, cached=True, request_id=request_id)

        resolution = resolver.resolve(body.question, hint)
        if resolution.answer is None:
            request_id = record("unanswered", resolution.domain, cost_eur=resolution.cost_eur)
            return {"status": "unanswered", "request_id": request_id, "question": body.question, "cached": False}

        fresh = CachedAnswer(
            key=key,
            question=body.question,
            domain=resolution.domain,
            answer=resolution.answer,
            sources=resolution.sources,
            confidence=resolution.confidence,
            created_at=now,
            expires_at=now + config.DOMAIN_TTL_SECONDS[resolution.domain],
        )
        store.put(fresh)
        store.consume(api_key)
        request_id = record("miss", fresh.domain, cost_eur=resolution.cost_eur, version_id=fresh.version_id)
        return _payload(fresh, cached=False, request_id=request_id)

    @app.post("/v1/feedback")
    def feedback(body: FeedbackRequest, x_api_key: str = Header(default="")):
        # Pas de contrôle de quota : un retour ne coûte rien et ne doit jamais être refusé pour ça.
        if not x_api_key or store.get_key(x_api_key) is None:
            raise HTTPException(401, "Clé d'API absente ou inconnue.")
        if not store.add_feedback(
            request_id=body.request_id,
            api_key=x_api_key,
            useful=body.useful,
            issue=body.issue,
            comment=body.comment,
        ):
            raise HTTPException(404, "Requête inconnue pour cette clé.")
        return {"status": "recorded", "request_id": body.request_id}

    @app.post("/internal/keys", dependencies=[Depends(require_admin)], include_in_schema=False)
    def create_key(body: KeyRequest):
        return {"api_key": store.create_key(body.label, body.quota), "quota": body.quota}

    @app.get("/internal/stats", dependencies=[Depends(require_admin)], include_in_schema=False)
    def stats(days: float | None = Query(default=None, gt=0, le=3650)):
        since = time.time() - days * 86400 if days else 0.0
        return store.stats(config.PRICE_PER_REQUEST_EUR, since=since)

    @app.get("/internal/timeseries", dependencies=[Depends(require_admin)], include_in_schema=False)
    def timeseries(
        days: float = Query(default=7, gt=0, le=3650),
        bucket: Literal["hour", "day"] = "day",
        tz_offset_min: int = Query(default=0, ge=-14 * 60, le=14 * 60),
    ):
        return store.timeseries(
            since=time.time() - days * 86400,
            bucket_seconds=3600 if bucket == "hour" else 86400,
            tz_offset_seconds=tz_offset_min * 60,
        )

    @app.get("/internal/keys", dependencies=[Depends(require_admin)], include_in_schema=False)
    def list_keys():
        return store.list_keys()

    @app.get("/internal/requests", dependencies=[Depends(require_admin)], include_in_schema=False)
    def recent_requests(limit: int = Query(default=50, ge=1, le=500)):
        return store.recent_requests(limit)

    @app.get("/internal/feedback", dependencies=[Depends(require_admin)], include_in_schema=False)
    def list_feedback(limit: int = Query(default=50, ge=1, le=500)):
        return store.list_feedback(limit)

    @app.get("/internal/answers", dependencies=[Depends(require_admin)], include_in_schema=False)
    def list_answers(limit: int = Query(default=50, ge=1, le=500)):
        return store.list_answers(limit)

    # Connexion du tableau de bord (front Next.js séparé, voir admin/). Les routes /internal/* ne sont
    # pas exposées sur Internet : Caddy les bloque, seul le front, sur le serveur, les appelle.
    @app.post("/internal/auth/login", include_in_schema=False)
    def login(body: LoginRequest, request: Request, x_forwarded_for: str = Header(default="")):
        if not (config.ADMIN_EMAIL and config.ADMIN_PASSWORD_HASH and config.SESSION_SECRET):
            raise HTTPException(503, "Connexion non configurée : ADMIN_EMAIL, ADMIN_PASSWORD_HASH, SESSION_SECRET.")
        who = x_forwarded_for.split(",")[0].strip() or (request.client.host if request.client else "?")
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


def _payload(a: CachedAnswer, *, cached: bool, request_id: str) -> dict:
    return {
        "status": "answered",
        "request_id": request_id,
        "question": a.question,
        "answer": a.answer,
        "domain": a.domain,
        "confidence": a.confidence,
        "sources": a.sources,
        "cached": cached,
        "fetched_at": a.created_at,
        "expires_at": a.expires_at,
    }


app = create_app() if os.environ.get("NM304_AUTOSTART", "1") == "1" else None
