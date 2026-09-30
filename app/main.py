"""API de la version d'essai : un cache de réponses vérifiées pour agents."""

import hmac
import os
import time
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field

from . import config
from .normalize import question_key
from .resolver import ClaudeResolver, NullResolver, Resolver
from .store import CachedAnswer, Store


class AnswerRequest(BaseModel):
    question: str = Field(min_length=3, max_length=config.MAX_QUESTION_CHARS)
    domain: str | None = Field(
        default=None, description="Indice facultatif : " + ", ".join(sorted(config.DOMAIN_TTL_SECONDS))
    )


class KeyRequest(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    quota: int = Field(default=config.FREE_QUOTA, ge=1)


LLMS_TXT = f"""# 304NotModified (version d'essai)

> Réponses factuelles vérifiées, sourcées et datées, partagées entre agents.
> Une question déjà résolue par un autre agent est servie immédiatement depuis le cache.

## Utilisation
POST /v1/answer
En-tête : X-API-Key: <clé>
Corps JSON : {{"question": "...", "domain": "facultatif"}}
Domaines : {", ".join(sorted(config.DOMAIN_TTL_SECONDS))}

Réponse : status (answered | unanswered), answer, sources [url, title], confidence (0-1),
domain, cached (bool), fetched_at et expires_at (horodatages Unix).
Vérifiez vous-même les sources si l'enjeu est important : confidence est une estimation.

Documentation OpenAPI : /docs et /openapi.json
"""


DASHBOARD_HTML = (Path(__file__).parent / "dashboard.html").read_text(encoding="utf-8")


def create_app(store: Store | None = None, resolver: Resolver | None = None) -> FastAPI:
    store = store or Store(config.DB_PATH)
    if resolver is None:
        resolver = ClaudeResolver() if os.environ.get("ANTHROPIC_API_KEY") else NullResolver()

    app = FastAPI(title="304NotModified", version="0.1.0")

    def require_key(x_api_key: str = Header(default="")):
        row = store.get_key(x_api_key) if x_api_key else None
        if row is None:
            raise HTTPException(401, "Clé d'API absente ou inconnue.")
        if row["used"] >= row["quota"]:
            raise HTTPException(429, "Quota épuisé pour cette clé.")
        return row["key"]

    def require_admin(authorization: str = Header(default="")):
        expected = f"Bearer {config.ADMIN_TOKEN}"
        if not config.ADMIN_TOKEN or not hmac.compare_digest(authorization, expected):
            raise HTTPException(403, "Accès administrateur requis.")

    @app.get("/health")
    def health():
        return {"status": "ok", "resolver": type(resolver).__name__}

    @app.get("/llms.txt", response_class=PlainTextResponse)
    def llms_txt():
        return LLMS_TXT

    @app.post("/v1/answer")
    def answer(body: AnswerRequest, api_key: str = Depends(require_key)):
        started = time.monotonic()
        now = time.time()
        key = question_key(body.question)
        hint = body.domain if body.domain in config.DOMAIN_TTL_SECONDS else None

        def elapsed_ms():
            return int((time.monotonic() - started) * 1000)

        cached = store.get_fresh(key, now)
        if cached is not None:
            store.consume(api_key)
            store.log(
                api_key=api_key,
                key=key,
                question=body.question,
                domain=cached.domain,
                outcome="hit",
                latency_ms=elapsed_ms(),
            )
            return _payload(cached, cached=True)

        resolution = resolver.resolve(body.question, hint)
        if resolution.answer is None:
            store.log(
                api_key=api_key,
                key=key,
                question=body.question,
                domain=resolution.domain,
                outcome="unanswered",
                latency_ms=elapsed_ms(),
                cost_eur=resolution.cost_eur,
            )
            return {"status": "unanswered", "question": body.question, "cached": False}

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
        store.log(
            api_key=api_key,
            key=key,
            question=body.question,
            domain=fresh.domain,
            outcome="miss",
            latency_ms=elapsed_ms(),
            cost_eur=resolution.cost_eur,
        )
        return _payload(fresh, cached=False)

    @app.post("/admin/keys", dependencies=[Depends(require_admin)])
    def create_key(body: KeyRequest):
        return {"api_key": store.create_key(body.label, body.quota), "quota": body.quota}

    @app.get("/admin/stats", dependencies=[Depends(require_admin)])
    def stats():
        return store.stats(config.PRICE_PER_REQUEST_EUR)

    @app.get("/admin/keys", dependencies=[Depends(require_admin)])
    def list_keys():
        return store.list_keys()

    @app.get("/admin/requests", dependencies=[Depends(require_admin)])
    def recent_requests(limit: int = Query(default=50, ge=1, le=500)):
        return store.recent_requests(limit)

    @app.get("/admin/answers", dependencies=[Depends(require_admin)])
    def list_answers(limit: int = Query(default=50, ge=1, le=500)):
        return store.list_answers(limit)

    # Tableau de bord : la page elle-même est publique, mais elle ne montre rien sans le jeton
    # administrateur, qu'elle envoie à chaque appel des routes /admin/* ci-dessus.
    @app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
    def dashboard():
        return DASHBOARD_HTML

    return app


def _payload(a: CachedAnswer, *, cached: bool) -> dict:
    return {
        "status": "answered",
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
