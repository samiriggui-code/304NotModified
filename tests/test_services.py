"""Catalogue de services : contrat, devis, budget, exécution, facturation, reprises, MCP.

Les fournisseurs sont SIMULÉS (httpx.MockTransport) : aucun appel réseau, aucune dépense. Les réponses
simulées reprennent la forme réelle de l'API Recherche d'entreprises (relevée le 01/10/2026), de l'API
Jev (docs.typesafe.ai) et de l'API Apify (docs.apify.com).
"""

import anyio
import httpx
import pytest
from fastapi.testclient import TestClient
from mcp import Client

from app import config
from app.main import create_app
from app.providers import ProviderFailed, RateLimiter
from app.providers.apify import ApifyCollector
from app.providers.jev import JevClassifier, verdict
from app.providers.recherche_entreprises import RechercheEntreprises, normalize
from app.services import suppliers_fr
from app.store import Store
from mcp_server.server import create_server
from tests.test_api import ADMIN, FakeResolver


def company(siren: str, name: str, diffusion: str = "O") -> dict:
    return {
        "siren": siren,
        "nom_complet": name,
        "activite_principale": "17.21A",
        "activite_principale_naf25": "17.21Y",
        "categorie_entreprise": "PME",
        "tranche_effectif_salarie": "12",
        "annee_tranche_effectif_salarie": "2023",
        "date_creation": "1972-01-01",
        "etat_administratif": "A",
        "statut_diffusion": diffusion,
        "nombre_etablissements_ouverts": 1,
        "dirigeants": [
            {"nom": "DUPONT", "prenoms": "JEAN", "date_de_naissance": "1970-01", "type_dirigeant": "personne physique"}
        ],
        "siege": {
            "siret": siren + "00011",
            "adresse": "RUE DE LA VALLEE 60700 FLEURINES",
            "code_postal": "60700",
            "libelle_commune": "FLEURINES",
            "departement": "60",
            "region": "32",
        },
    }


class FakeGov:
    """Faux serveur de l'API Recherche d'entreprises."""

    def __init__(self, results=None, total_pages=1, fail_status=None):
        self.results = (
            results
            if results is not None
            else [company("111111111", "CARTONS DU NORD"), company("222222222", "EMBALLAGES SUD", "P")]
        )
        self.total_pages = total_pages
        self.fail_status = fail_status
        self.calls: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(dict(request.url.params))
        if self.fail_status:
            return httpx.Response(self.fail_status)
        page = int(request.url.params.get("page", 1))
        return httpx.Response(
            200, json={"results": self.results, "total_results": 40, "page": page, "total_pages": self.total_pages}
        )


class FakeJev:
    def __init__(self, probabilities, status=200):
        self.probabilities = probabilities
        self.status = status
        self.bodies: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content)
        self.bodies.append(body)
        if self.status != 200:
            return httpx.Response(self.status)
        answers = {qid: {"type": "noul", "noul": self.probabilities[i]} for i, qid in enumerate(body["questions"])}
        return httpx.Response(
            200,
            json={"model": "jev-1.13.0", "answers": answers, "usage": {"input_tokens": 1_000_000, "output_tokens": 20}},
        )


def fast_limiter():
    return RateLimiter(per_second=1000, max_concurrent=4, queue_timeout=1)


def make(tmp_path, monkeypatch, gov=None, jev=None, quota=10):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "test-admin")
    gov = gov or FakeGov()
    collector = RechercheEntreprises(httpx.Client(transport=httpx.MockTransport(gov.handler)), fast_limiter())
    classifier = JevClassifier(
        "test-key" if jev else None,
        httpx.Client(transport=httpx.MockTransport(jev.handler)) if jev else None,
        fast_limiter(),
    )
    store = Store(str(tmp_path / "s.sqlite3"))
    client = TestClient(create_app(store, FakeResolver(), [suppliers_fr.build(collector, classifier)]))
    key = client.post("/internal/keys", json={"label": "svc", "quota": quota}, headers=ADMIN).json()["api_key"]
    return client, gov, store, {"X-API-Key": key}


PARAMS = {"query": "emballage carton", "naf_codes": ["17.21a"], "departements": ["60"], "max_results": 10}


def used(store, headers):
    return store.get_key(headers["X-API-Key"])["used"]


# --- découverte -------------------------------------------------------------------------------------


def test_catalog_publishes_full_contract(tmp_path, monkeypatch):
    client, *_ = make(tmp_path, monkeypatch)
    services = client.get("/v1/services").json()
    spec = services[0]
    assert spec["id"] == "fr-suppliers" and spec["version"] == "1.0.0" and spec["mode"] == "sync"
    for field in (
        "input_schema",
        "output_schema",
        "pricing",
        "typical_latency_seconds",
        "freshness",
        "limits",
        "errors",
    ):
        assert spec[field]
    assert spec["capabilities"]["relevance"]["available"] is False
    assert "/v1/services" in client.get("/llms.txt").text


# --- exécution et contenu ------------------------------------------------------------------------------


def test_run_delivers_sourced_structured_result_without_personal_data(tmp_path, monkeypatch):
    client, gov, store, headers = make(tmp_path, monkeypatch)
    body = client.post("/v1/services/fr-suppliers/run", json={"params": PARAMS}, headers=headers).json()

    assert body["status"] == "completed" and body["billing"]["billed"] is True
    assert body["billing"]["price_eur"] == config.SUPPLIERS_PRICE_EUR
    assert gov.calls[0]["activite_principale"] == "17.21A" and gov.calls[0]["etat_administratif"] == "A"
    first, second = body["result"]["companies"]
    assert first["source_url"].endswith("/entreprise/111111111")
    assert "dirigeants" not in first and "DUPONT" not in str(body)
    assert second["head_office"] is None and second["address_withheld"] is True
    assert body["sources"][0]["collected_at"] and body["sources"][0]["params"]["q"] == "emballage carton"
    assert any("Coordonnées" in m for m in body["missing"])
    assert used(store, headers) == 1

    stats = client.get("/internal/stats", headers=ADMIN).json()["services"]["fr-suppliers"]
    assert stats["runs"] == 1 and stats["billed"] == 1 and stats["revenue_eur"] == config.SUPPLIERS_PRICE_EUR


def test_same_params_are_served_from_memory(tmp_path, monkeypatch):
    client, gov, _, headers = make(tmp_path, monkeypatch)
    client.post("/v1/services/fr-suppliers/run", json={"params": PARAMS}, headers=headers)
    again = client.post(
        "/v1/services/fr-suppliers/run", json={"params": {**PARAMS, "naf_codes": ["17.21A"]}}, headers=headers
    ).json()
    assert again["cached"] is True and again["status"] == "completed"
    assert len(gov.calls) == 1


def test_empty_result_is_not_billed_even_from_memory(tmp_path, monkeypatch):
    client, _, store, headers = make(tmp_path, monkeypatch, gov=FakeGov(results=[]))
    first = client.post("/v1/services/fr-suppliers/run", json={"params": PARAMS}, headers=headers).json()
    again = client.post("/v1/services/fr-suppliers/run", json={"params": PARAMS}, headers=headers).json()
    assert first["status"] == "completed" and first["billing"]["billed"] is False
    assert any("naf_codes" in m for m in first["missing"])
    assert again["cached"] is True and again["billing"]["billed"] is False
    assert used(store, headers) == 0


def test_matching_establishment_shows_the_site_in_the_area():
    raw = company("123456789", "X")
    raw["matching_etablissements"] = [
        {
            "siret": "12345678900099",
            "adresse": "1 RUE A 59000 LILLE",
            "code_postal": "59000",
            "libelle_commune": "LILLE",
            "est_siege": False,
        }
    ]
    record = normalize(raw)
    assert record["matching_establishment"]["city"] == "LILLE"
    assert record["matching_establishment"]["is_head_office"] is False
    assert normalize({**raw, "statut_diffusion": "P"})["matching_establishment"] is None


def test_invalid_params_are_refused_before_any_call(tmp_path, monkeypatch):
    client, gov, _, headers = make(tmp_path, monkeypatch)
    r = client.post("/v1/services/fr-suppliers/run", json={"params": {"naf_codes": ["1721"]}}, headers=headers)
    assert r.status_code == 422 and r.json()["detail"]["error"] == "invalid_params"
    r = client.post("/v1/services/fr-suppliers/run", json={"params": {"departements": ["60"]}}, headers=headers)
    assert r.status_code == 422
    assert gov.calls == []


def test_provider_failure_is_not_billed_and_retryable(tmp_path, monkeypatch):
    client, _, store, headers = make(tmp_path, monkeypatch, gov=FakeGov(fail_status=503))
    body = client.post("/v1/services/fr-suppliers/run", json={"params": PARAMS}, headers=headers).json()
    assert body["status"] == "failed" and body["reason"] == "provider_error" and body["retryable"] is True
    assert body["billing"]["billed"] is False and used(store, headers) == 0


def test_pagination_failure_after_first_page_is_partial_and_not_billed(tmp_path, monkeypatch):
    gov = FakeGov(results=[company(f"{i:09d}", f"E{i}") for i in range(25)], total_pages=3)
    original = gov.handler

    def flaky(request):
        return httpx.Response(503) if request.url.params.get("page") == "2" else original(request)

    gov.handler = flaky
    client, _, store, headers = make(tmp_path, monkeypatch, gov=gov)
    body = client.post(
        "/v1/services/fr-suppliers/run", json={"params": {**PARAMS, "max_results": 50}}, headers=headers
    ).json()
    assert body["status"] == "partial" and body["result"]["truncated"] is True and body["result"]["count"] == 25
    assert body["billing"]["billed"] is False and used(store, headers) == 0


# --- devis, budget, double facturation ------------------------------------------------------------------


def test_quote_is_firm_single_use_and_bound_to_params(tmp_path, monkeypatch):
    client, _, store, headers = make(tmp_path, monkeypatch)
    quote = client.post("/v1/services/fr-suppliers/quote", json={"params": PARAMS}, headers=headers).json()
    assert quote["price_eur"] == config.SUPPLIERS_PRICE_EUR and quote["expires_at"] > 0

    other = {**PARAMS, "query": "autre chose"}
    mismatch = client.post(
        "/v1/services/fr-suppliers/run", json={"params": other, "quote_id": quote["quote_id"]}, headers=headers
    )
    assert mismatch.status_code == 409 and mismatch.json()["detail"]["error"] == "quote_mismatch"

    ok = client.post(
        "/v1/services/fr-suppliers/run", json={"params": PARAMS, "quote_id": quote["quote_id"]}, headers=headers
    )
    assert ok.json()["billing"]["quote_id"] == quote["quote_id"]
    reused = client.post(
        "/v1/services/fr-suppliers/run", json={"params": PARAMS, "quote_id": quote["quote_id"]}, headers=headers
    )
    assert reused.status_code == 409 and reused.json()["detail"]["error"] == "quote_used"
    assert used(store, headers) == 1


def test_expired_quote_is_refused(tmp_path, monkeypatch):
    client, _, _, headers = make(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "QUOTE_TTL_SECONDS", -1)
    quote = client.post("/v1/services/fr-suppliers/quote", json={"params": PARAMS}, headers=headers).json()
    r = client.post(
        "/v1/services/fr-suppliers/run", json={"params": PARAMS, "quote_id": quote["quote_id"]}, headers=headers
    )
    assert r.status_code == 410


def test_unbilled_run_gives_the_quote_back(tmp_path, monkeypatch):
    client, _, _, headers = make(tmp_path, monkeypatch, gov=FakeGov(fail_status=503))
    quote = client.post("/v1/services/fr-suppliers/quote", json={"params": PARAMS}, headers=headers).json()
    first = client.post(
        "/v1/services/fr-suppliers/run", json={"params": PARAMS, "quote_id": quote["quote_id"]}, headers=headers
    )
    second = client.post(
        "/v1/services/fr-suppliers/run", json={"params": PARAMS, "quote_id": quote["quote_id"]}, headers=headers
    )
    assert first.json()["status"] == "failed" and second.status_code == 200


def test_budget_is_enforced_before_spending(tmp_path, monkeypatch):
    client, gov, store, headers = make(tmp_path, monkeypatch)
    r = client.post("/v1/services/fr-suppliers/run", json={"params": PARAMS, "max_price_eur": 0.001}, headers=headers)
    assert r.status_code == 402 and r.json()["detail"]["error"] == "budget_exceeded"
    assert gov.calls == [] and used(store, headers) == 0


def test_daily_cap_per_key(tmp_path, monkeypatch):
    client, _, _, headers = make(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "SERVICE_DAILY_CAP_EUR", config.SUPPLIERS_PRICE_EUR * 1.5)
    assert client.post("/v1/services/fr-suppliers/run", json={"params": PARAMS}, headers=headers).status_code == 200
    r = client.post("/v1/services/fr-suppliers/run", json={"params": {**PARAMS, "query": "bois"}}, headers=headers)
    assert r.status_code == 402 and r.json()["detail"]["error"] == "daily_cap_reached"


def test_idempotency_key_prevents_double_billing(tmp_path, monkeypatch):
    client, gov, store, headers = make(tmp_path, monkeypatch)
    h = {**headers, "Idempotency-Key": "commande-0001"}
    first = client.post("/v1/services/fr-suppliers/run", json={"params": PARAMS}, headers=h)
    second = client.post("/v1/services/fr-suppliers/run", json={"params": PARAMS}, headers=h)
    assert second.headers.get("Idempotent-Replayed") == "true"
    assert first.json()["run_id"] == second.json()["run_id"]
    assert used(store, headers) == 1 and len(gov.calls) == 1


# --- classement de pertinence (Jev) ----------------------------------------------------------------------


def test_relevance_without_jev_key_is_partial_and_free(tmp_path, monkeypatch):
    client, _, store, headers = make(tmp_path, monkeypatch)
    params = {**PARAMS, "relevance_criterion": "fabrique des emballages alimentaires"}
    body = client.post("/v1/services/fr-suppliers/run", json={"params": params}, headers=headers).json()
    assert body["status"] == "partial" and body["billing"]["billed"] is False
    assert body["result"]["relevance"]["evaluated"] is False
    assert {c["relevance"]["verdict"] for c in body["result"]["companies"]} == {"not_evaluated"}
    assert used(store, headers) == 0


def test_relevance_with_jev_three_outcomes_and_real_cost(tmp_path, monkeypatch):
    gov = FakeGov(results=[company("111111111", "A"), company("222222222", "B"), company("333333333", "C")])
    jev = FakeJev([0.9, 0.5, 0.1])
    client, _, _, headers = make(tmp_path, monkeypatch, gov=gov, jev=jev)
    params = {**PARAMS, "relevance_criterion": "fabrique des emballages alimentaires", "drop_no_match": True}
    body = client.post("/v1/services/fr-suppliers/run", json={"params": params}, headers=headers).json()

    assert body["status"] == "completed"
    assert [c["relevance"]["verdict"] for c in body["result"]["companies"]] == ["match", "undetermined"]
    assert body["billing"]["price_eur"] == config.SUPPLIERS_PRICE_EUR + config.SUPPLIERS_RELEVANCE_PRICE_EUR
    sent = jev.bodies[0]
    assert sent["model"] == config.JEV_MODEL and sent["state"]["criterion"].startswith("fabrique")
    assert all(q["type"] == "noul" for q in sent["questions"].values())

    stats = client.get("/internal/stats", headers=ADMIN).json()["services"]["fr-suppliers"]
    # 1 million de jetons simulés × 0,042 $ × taux de change : le coût vient de usage.input_tokens.
    assert stats["cost_classify_eur"] == pytest.approx(config.JEV_USD_PER_MTOK * config.USD_TO_EUR)


def test_jev_overload_degrades_cleanly(tmp_path, monkeypatch):
    client, _, store, headers = make(tmp_path, monkeypatch, jev=FakeJev([0.9, 0.9], status=529))
    params = {**PARAMS, "relevance_criterion": "fabrique des emballages alimentaires"}
    body = client.post("/v1/services/fr-suppliers/run", json={"params": params}, headers=headers).json()
    assert body["status"] == "partial" and any("busy" in m for m in body["missing"])
    assert used(store, headers) == 0


def test_verdict_thresholds():
    assert verdict(0.9) == "match" and verdict(0.1) == "no_match"
    assert verdict(0.5) == "undetermined" and verdict(None) == "undetermined"


def test_normalize_drops_personal_data():
    record = normalize(company("123456789", "X"))
    assert "dirigeants" not in record and record["naf2025_code"] == "17.21Y"


# --- Apify (adaptateur prêt, aucun Actor branché) ---------------------------------------------------------


def test_apify_runs_actor_with_caps_and_reads_real_cost():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, dict(request.url.params)))
        assert request.headers["Authorization"] == "Bearer tok"
        if request.url.path.endswith("/runs"):
            return httpx.Response(201, json={"data": {"id": "r1", "status": "RUNNING"}})
        if request.url.path == "/v2/actor-runs/r1":
            return httpx.Response(
                200, json={"data": {"id": "r1", "status": "SUCCEEDED", "defaultDatasetId": "d1", "usageTotalUsd": 0.1}}
            )
        return httpx.Response(200, json=[{"url": "https://exemple.fr", "title": "Exemple"}])

    apify = ApifyCollector(
        "tok", httpx.Client(base_url="https://api.apify.com/v2", transport=httpx.MockTransport(handler)), fast_limiter()
    )
    collection = apify.run_actor(
        "user~actor", {"startUrls": []}, max_items=10, max_total_charge_usd=0.5, timeout_secs=60
    )

    method, path, params = seen[0]
    assert method == "POST" and path == "/v2/actors/user~actor/runs"
    assert params["maxTotalChargeUsd"] == "0.5" and params["maxItems"] == "10"
    assert collection.items[0]["url"] == "https://exemple.fr"
    assert collection.cost_eur == pytest.approx(0.1 * config.USD_TO_EUR)
    assert collection.source["run_id"] == "r1"


def test_apify_failed_run_still_reports_its_cost():
    def handler(request):
        return httpx.Response(201, json={"data": {"id": "r1", "status": "FAILED", "usageTotalUsd": 0.2}})

    apify = ApifyCollector(
        "tok", httpx.Client(base_url="https://api.apify.com/v2", transport=httpx.MockTransport(handler)), fast_limiter()
    )
    with pytest.raises(ProviderFailed) as exc:
        apify.run_actor("user~actor", {}, max_items=1, max_total_charge_usd=0.5, timeout_secs=1)
    assert exc.value.cost_eur == pytest.approx(0.2 * config.USD_TO_EUR)


# --- MCP : même logique que HTTP ----------------------------------------------------------------------------


def test_mcp_tools_use_the_same_routes(tmp_path, monkeypatch):
    client, _, store, headers = make(tmp_path, monkeypatch)
    server = create_server(client, headers["X-API-Key"])

    async def run():
        async with Client(server) as mcp:
            listed = await mcp.call_tool("list_services", {})
            ran = await mcp.call_tool(
                "run_service", {"service": "fr-suppliers", "params": PARAMS, "request_key": "mcp-cmd-0001"}
            )
            again = await mcp.call_tool(
                "run_service", {"service": "fr-suppliers", "params": PARAMS, "request_key": "mcp-cmd-0001"}
            )
            refused = await mcp.call_tool(
                "run_service", {"service": "fr-suppliers", "params": PARAMS, "max_price_eur": 0.0001}
            )
            return listed, ran, again, refused

    listed, ran, again, refused = anyio.run(run)
    assert listed.structured_content["services"][0]["id"] == "fr-suppliers"
    assert ran.structured_content["status"] == "completed"
    assert again.structured_content["run_id"] == ran.structured_content["run_id"]
    assert refused.is_error and "budget_exceeded" in refused.content[0].text
    assert used(store, headers) == 1
