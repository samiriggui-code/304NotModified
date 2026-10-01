"""Routes /v1/services : découverte, devis, exécution. Le serveur MCP relaie vers ces mêmes routes.

Parcours d'une exécution :
1. clé et quota vérifiés (require_key, comme /v1/answer) ; paramètres validés par le contrat ;
2. prix : celui du devis (quote_id) s'il est donné, valable et lié à ces paramètres, sinon calculé ;
3. budget : refus (402) si le prix dépasse max_price_eur ou le plafond journalier de la clé ;
4. résultat encore frais en mémoire → servi tel quel ; sinon exécution, une seule à la fois par demande ;
5. contrôle du schéma de sortie ; facturation seulement si status=completed ;
6. journal : coûts par étape, prix facturé, état final.

Paiement : en version d'essai, « facturé » veut dire décompté du quota de la clé. La couche x402
prendra place à l'étape 3 (vérification de l'autorisation) et à l'étape 5 (encaissement), sans
toucher aux services. Un message de l'agent disant « payé » n'est jamais une preuve de paiement.
"""

import hashlib
import json
import secrets
import time
from collections.abc import Callable

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field, ValidationError

from .. import config
from . import COST_KINDS, Outcome, RunContext, ServiceSpec, SingleFlight, fingerprint


class QuoteRequest(BaseModel):
    params: dict = Field(description="Paramètres du service (voir input_schema dans GET /v1/services/{id}).")


class RunRequest(BaseModel):
    params: dict = Field(description="Paramètres du service (voir input_schema dans GET /v1/services/{id}).")
    quote_id: str | None = Field(default=None, max_length=64, description="Devis à utiliser (prix ferme).")
    max_price_eur: float | None = Field(
        default=None, ge=0, description="Budget maximal pour cet appel : au-delà, rien n'est exécuté (402)."
    )


def register_service_routes(
    app: FastAPI, store, require_key: Callable, client_ip: Callable[[Request], str], specs: list[ServiceSpec]
) -> None:
    catalog = {s.id: s for s in specs}
    flights = SingleFlight()

    def spec_or_404(service_id: str) -> ServiceSpec:
        spec = catalog.get(service_id)
        if spec is None:
            raise HTTPException(404, f"Service inconnu. Liste : GET {config.PUBLIC_URL}/v1/services")
        return spec

    def validate(spec: ServiceSpec, params: dict):
        try:
            return spec.input_model.model_validate(params)
        except ValidationError as exc:
            errors = [
                {"field": ".".join(str(p) for p in e["loc"]) or "params", "message": e["msg"]} for e in exc.errors()
            ]
            raise HTTPException(422, {"error": "invalid_params", "details": errors}) from exc

    tags = ["Services"]

    @app.get("/v1/services", tags=tags, summary="Catalogue des services : contrats, prix, délais, limites")
    def list_services():
        return [s.describe(config.PUBLIC_URL) for s in catalog.values()]

    @app.get("/v1/services/{service_id}", tags=tags, summary="Contrat d'un service")
    def get_service(service_id: str):
        return spec_or_404(service_id).describe(config.PUBLIC_URL)

    @app.post("/v1/services/{service_id}/quote", tags=tags, summary="Devis : prix ferme pour ces paramètres")
    def quote(service_id: str, body: QuoteRequest, api_key: str = Depends(require_key)):
        spec = spec_or_404(service_id)
        params = validate(spec, body.params)
        # Le devis ne consomme rien : prix calculé par règle, sans appel à un fournisseur.
        q = store.create_quote(
            api_key=api_key,
            service=spec.id,
            version=spec.version,
            fingerprint=fingerprint(params),
            price_eur=spec.price(params),
            now=time.time(),
            ttl=config.QUOTE_TTL_SECONDS,
        )
        return {
            "quote_id": q["quote_id"],
            "service": spec.id,
            "version": spec.version,
            "price_eur": q["price_eur"],
            "currency": "EUR",
            "expires_at": q["expires_at"],
            "billing": "Facturé seulement si status=completed. Un devis ne sert qu'une fois.",
            "capabilities": spec.capabilities(),
        }

    @app.post("/v1/services/{service_id}/run", tags=tags, summary="Exécuter un service")
    def run(
        service_id: str,
        body: RunRequest,
        request: Request,
        response: Response,
        api_key: str = Depends(require_key),
        x_client: str = Header(default=""),
        user_agent: str = Header(default=""),
        idempotency_key: str = Header(
            default="",
            max_length=200,
            description="Facultatif : même valeur pour les relances. Le résultat enregistré est renvoyé, "
            "sans nouvelle exécution ni nouvelle facturation.",
        ),
    ):
        spec = spec_or_404(service_id)
        params = validate(spec, body.params)

        idem = None
        if idempotency_key:
            scope = api_key if api_key != config.ANON_KEY else f"{config.ANON_KEY}:{client_ip(request)}"
            scope = f"{scope}:svc:{spec.id}"
            fp = hashlib.sha256(json.dumps(body.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()
            state, stored = store.idempotency_begin(
                scope, idempotency_key, fp, time.time(), config.IDEMPOTENCY_TTL_SECONDS
            )
            if state == "replay":
                response.headers["Idempotent-Replayed"] = "true"
                return stored
            if state == "conflict":
                raise HTTPException(422, "Cette Idempotency-Key a déjà servi pour une autre demande.")
            if state == "pending":
                raise HTTPException(409, "La même demande est déjà en cours.", headers={"Retry-After": "2"})
            idem = (scope, idempotency_key)

        try:
            result = execute(spec, params, body, api_key, x_client, user_agent)
        except BaseException:
            if idem:
                store.idempotency_abort(*idem)
            raise
        if idem:
            if result.get("retryable"):
                store.idempotency_abort(*idem)
            else:
                store.idempotency_finish(*idem, result)
        return result

    def execute(spec: ServiceSpec, params, body: RunRequest, api_key: str, x_client: str, user_agent: str) -> dict:
        started = time.monotonic()
        now = time.time()
        run_id = "run_" + secrets.token_urlsafe(12)
        fp = fingerprint(params)

        # Prix : devis ferme, ou calcul direct.
        quote_id = body.quote_id
        if quote_id:
            state, q = store.claim_quote(quote_id, api_key, run_id, now)
            if state == "unknown":
                raise HTTPException(404, {"error": "quote_unknown"})
            if state == "expired":
                raise HTTPException(410, {"error": "quote_expired", "expired_at": q["expires_at"]})
            if state == "used":
                raise HTTPException(409, {"error": "quote_used", "detail": "Un devis ne sert qu'une fois."})
            if q["service"] != spec.id or q["version"] != spec.version or q["fingerprint"] != fp:
                store.release_quote(quote_id, run_id)
                raise HTTPException(
                    409, {"error": "quote_mismatch", "detail": "Devis établi pour d'autres paramètres."}
                )
            price = q["price_eur"]
        else:
            price = spec.price(params)

        def refuse(status: int, detail: dict):
            if quote_id:
                store.release_quote(quote_id, run_id)
            raise HTTPException(status, detail)

        # Budget : rien n'est exécuté ni dépensé au-delà de ce que l'agent autorise.
        if body.max_price_eur is not None and price > body.max_price_eur:
            refuse(402, {"error": "budget_exceeded", "price_eur": price, "max_price_eur": body.max_price_eur})
        spent = store.billed_since(api_key, now - 86400)
        if spent + price > config.SERVICE_DAILY_CAP_EUR:
            refuse(
                402,
                {
                    "error": "daily_cap_reached",
                    "spent_24h_eur": round(spent, 6),
                    "cap_eur": config.SERVICE_DAILY_CAP_EUR,
                },
            )

        cache_key = hashlib.sha256(f"{spec.id}|{spec.version}|{fp}".encode()).hexdigest()
        ctx = RunContext()
        cached = store.service_cache_get(cache_key, now)
        outcome: Outcome | None = None
        if cached is None:
            outcome = flights.run(
                cache_key, lambda: spec.execute(params, ctx), wait_timeout=config.PROVIDER_TIMEOUT_SECONDS
            )
            if outcome is None:
                # Une demande identique vient d'être exécutée : on relit son résultat.
                cached = store.service_cache_get(cache_key, time.time())
                if cached is None:
                    outcome = Outcome("failed", reason="busy", retryable=True)
        if cached is not None:
            outcome = Outcome("completed", **cached["result"])

        # Contrôle du résultat par le moteur : un résultat hors contrat n'est ni livré ni facturé.
        if outcome.result is not None:
            try:
                outcome.result = spec.output_model.model_validate(outcome.result).model_dump(mode="json")
            except ValidationError:
                outcome = Outcome("failed", reason="invalid_output", retryable=False)

        billed = outcome.status == "completed" and outcome.billable
        if billed:
            store.consume(api_key)
        elif quote_id:
            store.release_quote(quote_id, run_id)
        if outcome.status == "completed" and cached is None and spec.cache_seconds:
            stored = {
                "billable": outcome.billable,
                "result": outcome.result,
                "sources": outcome.sources,
                "limits": outcome.limits,
                "missing": outcome.missing,
            }
            store.service_cache_put(cache_key, spec.id, stored, now, spec.cache_seconds)

        costs = {k: ctx.cost(k) for k in COST_KINDS}
        client = (x_client or user_agent)[:200] or None
        store.log_service_run(
            {
                "run_id": run_id,
                "ts": now,
                "api_key": api_key,
                "service": spec.id,
                "version": spec.version,
                "quote_id": quote_id,
                "status": outcome.status,
                "billed": int(billed),
                "price_eur": price if billed else 0.0,
                **{f"cost_{k}_eur": v for k, v in costs.items()},
                "latency_ms": int((time.monotonic() - started) * 1000),
                "cached": int(cached is not None),
                "steps": ctx.steps,
                "reason": outcome.reason,
                "channel": "mcp" if x_client.startswith("mcp:") else "http",
                "client": client,
            }
        )
        return {
            "status": outcome.status,
            "run_id": run_id,
            "service": spec.id,
            "version": spec.version,
            "result": outcome.result,
            "sources": outcome.sources,
            "limits": outcome.limits,
            "missing": outcome.missing,
            "cached": cached is not None,
            "produced_at": cached["created_at"] if cached else now,
            "expires_at": cached["expires_at"]
            if cached
            else (now + spec.cache_seconds if outcome.status == "completed" else None),
            "reason": outcome.reason,
            "retryable": outcome.retryable,
            "retry_after": config.RETRY_AFTER_SECONDS if outcome.retryable else None,
            "billing": {
                "billed": billed,
                "price_eur": price if billed else 0.0,
                "quote_id": quote_id,
                "method": "quota",  # version d'essai : décompte du quota, aucun encaissement
            },
        }
