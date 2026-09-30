"""Moteur : causes d'absence de réponse, fournisseur (erreurs, délai, pas de relance), recherches
simultanées (déduplication, limite), alias d'arguments, adresse du client, idempotence.

Tous les fournisseurs sont simulés : aucun appel réseau, aucune recherche payante.
"""

import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import anyio
import httpx
import pytest
from fastapi.testclient import TestClient
from mcp import Client

from app import config
from app.main import client_address, create_app
from app.resolver import ClaudeResolver, NullResolver, ProviderError, ProviderTimeout, Resolution
from app.store import Store
from mcp_server.server import create_server
from tests.test_api import ADMIN

SOURCE = [{"url": "https://exemple.gouv.fr/page", "title": "Source officielle"}]


class SlowResolver:
    """Fournisseur simulé : attend `delay` secondes puis répond (ou échoue)."""

    def __init__(self, delay=0.3, fail_with=None, answer="42"):
        self.delay, self.fail_with, self.answer = delay, fail_with, answer
        self.calls = 0
        self._lock = threading.Lock()

    def resolve(self, question, domain_hint):
        with self._lock:
            self.calls += 1
        time.sleep(self.delay)
        if self.fail_with:
            raise self.fail_with
        if self.answer is None:
            return Resolution(None, domain_hint or "general", 0.0, cost_eur=0.01, reason="no_reliable_answer")
        return Resolution(self.answer, domain_hint or "general", 0.9, SOURCE, cost_eur=0.02)


def make_client(tmp_path, monkeypatch, resolver, **settings):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "test-admin")
    for name, value in settings.items():
        monkeypatch.setattr(config, name, value)
    client = TestClient(create_app(Store(str(tmp_path / "e.sqlite3")), resolver))
    key = client.post("/internal/keys", json={"label": "moteur", "quota": 100}, headers=ADMIN).json()["api_key"]
    return client, {"X-API-Key": key}


def ask(client, headers, question="Quelle est la date d'entrée en vigueur ?", **extra):
    return client.post("/v1/answer", json={"question": question, **extra}, headers=headers)


# --- causes d'absence de réponse ---------------------------------------------------------


def test_search_disabled_is_explained_and_not_billable(tmp_path, monkeypatch):
    client, headers = make_client(tmp_path, monkeypatch, NullResolver())
    body = ask(client, headers).json()
    assert body["status"] == "unanswered" and body["reason"] == "search_disabled"
    assert body["retryable"] is False and body["retry_after"] is None and body["billable"] is False
    assert "désactivée" in body["message"]
    [row] = client.get("/internal/requests", headers=ADMIN).json()
    assert row["reason"] == "search_disabled"
    assert client.get("/internal/stats", headers=ADMIN).json()["unanswered_reasons"] == {"search_disabled": 1}
    # Rien n'est décompté.
    assert [k["used"] for k in client.get("/internal/keys", headers=ADMIN).json() if k["label"] == "moteur"] == [0]


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (ProviderError("APIConnectionError"), "provider_error"),
        (ProviderTimeout("x"), "timeout"),
        (RuntimeError(), "internal_error"),
    ],
)
def test_provider_failures_are_classified_and_retryable(tmp_path, monkeypatch, error, reason):
    client, headers = make_client(tmp_path, monkeypatch, SlowResolver(delay=0, fail_with=error))
    response = ask(client, headers)
    body = response.json()
    assert response.status_code == 200 and body["reason"] == reason
    assert body["retryable"] is True and body["retry_after"] == config.RETRY_AFTER_SECONDS
    # Aucun détail interne dans le message renvoyé à l'agent.
    assert "Error" not in body["message"] and "anthropic" not in body["message"].lower()


def _fake_response(text, stop_reason="end_turn", citations=()):
    block = SimpleNamespace(type="text", text=text, citations=list(citations))
    usage = SimpleNamespace(input_tokens=10, output_tokens=10, cache_creation_input_tokens=0, server_tool_use=None)
    return SimpleNamespace(content=[block], stop_reason=stop_reason, usage=usage)


class FakeClient:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, 0
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        return self.response


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (_fake_response("", stop_reason="refusal"), "refused"),
        (_fake_response("pas de JSON ici"), "parse_error"),
        (_fake_response('{"answer": null, "domain": "general", "confidence": 0, "sources": []}'), "no_reliable_answer"),
        (_fake_response('{"answer": "oui", "domain": "general", "confidence": 0.9, "sources": []}'), "no_source"),
    ],
)
def test_claude_resolver_reasons(response, reason):
    resolution = ClaudeResolver(client=FakeClient(response)).resolve("Question ?", None)
    assert resolution.answer is None and resolution.reason == reason


def test_claude_resolver_answer_keeps_sources():
    text = '{"answer": "Le 1er septembre 2026.", "domain": "facturation", "confidence": 0.8, "sources": [{"url": "https://www.impots.gouv.fr/x", "title": "impots.gouv.fr"}]}'
    resolution = ClaudeResolver(client=FakeClient(_fake_response(text))).resolve("Date ?", "facturation")
    assert resolution.answer == "Le 1er septembre 2026." and resolution.reason is None
    assert resolution.sources[0]["url"] == "https://www.impots.gouv.fr/x"


def test_claude_resolver_maps_provider_errors_and_never_retries():
    import anthropic

    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    timeout = FakeClient(error=anthropic.APITimeoutError(request=request))
    with pytest.raises(ProviderTimeout):
        ClaudeResolver(client=timeout).resolve("Q ?", None)
    down = FakeClient(error=anthropic.APIConnectionError(request=request))
    with pytest.raises(ProviderError):
        ClaudeResolver(client=down).resolve("Q ?", None)
    # Une seule tentative : aucune relance d'un appel payant.
    assert timeout.calls == 1 and down.calls == 1


def test_claude_client_has_timeout_and_no_automatic_retry(monkeypatch):
    import anthropic

    captured = {}
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kwargs: captured.update(kwargs) or object())
    ClaudeResolver()
    assert captured == {"timeout": config.PROVIDER_TIMEOUT_SECONDS, "max_retries": 0}


# --- recherches simultanées -----------------------------------------------------------------


def test_identical_concurrent_questions_pay_one_search(tmp_path, monkeypatch):
    resolver = SlowResolver(delay=0.4)
    client, headers = make_client(tmp_path, monkeypatch, resolver)
    # Variantes triviales : même clé normalisée, donc la même recherche.
    variants = ["Quelle est la date ?", "quelle est la DATE", "  Quelle est la date  ", "Quelle est la date ?!"] * 2
    with ThreadPoolExecutor(len(variants)) as pool:
        bodies = [r.json() for r in pool.map(lambda q: ask(client, headers, q), variants)]

    assert resolver.calls == 1
    assert all(b["status"] == "answered" and b["answer"] == "42" for b in bodies)
    assert sorted(b["cached"] for b in bodies) == [False] + [True] * (len(variants) - 1)
    stats = client.get("/internal/stats", headers=ADMIN).json()
    assert stats["outcomes"] == {"miss": 1, "hit": len(variants) - 1}
    assert stats["estimated_cost_eur"] == pytest.approx(0.02)  # coût payé une seule fois


def test_different_questions_are_never_merged(tmp_path, monkeypatch):
    resolver = SlowResolver(delay=0.2)
    client, headers = make_client(tmp_path, monkeypatch, resolver)
    questions = ["Taux du Livret A en 2026 ?", "Taux du LEP en 2026 ?", "Plafond du Livret A ?"]
    with ThreadPoolExecutor(3) as pool:
        bodies = [r.json() for r in pool.map(lambda q: ask(client, headers, q), questions)]
    assert resolver.calls == 3 and all(not b["cached"] for b in bodies)


def test_waiting_agents_share_a_failure_without_new_searches(tmp_path, monkeypatch):
    resolver = SlowResolver(delay=0.3, fail_with=ProviderError("panne"))
    client, headers = make_client(tmp_path, monkeypatch, resolver)
    with ThreadPoolExecutor(5) as pool:
        bodies = [r.json() for r in pool.map(lambda _: ask(client, headers), range(5))]
    assert resolver.calls == 1
    assert {b["reason"] for b in bodies} == {"provider_error"}


def test_saturated_engine_answers_busy_instead_of_queuing(tmp_path, monkeypatch):
    resolver = SlowResolver(delay=0.5)
    client, headers = make_client(
        tmp_path, monkeypatch, resolver, MAX_CONCURRENT_SEARCHES=1, SEARCH_QUEUE_TIMEOUT_SECONDS=0.05
    )
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(ask, client, headers, "Première question longue ?")
        time.sleep(0.1)
        second = pool.submit(ask, client, headers, "Seconde question différente ?")
        results = [first.result().json(), second.result().json()]
    assert results[0]["status"] == "answered"
    assert results[1]["reason"] == "busy" and results[1]["retryable"] is True
    assert resolver.calls == 1


# --- alias d'arguments --------------------------------------------------------------------


def test_http_accepts_common_argument_aliases(tmp_path, monkeypatch):
    client, headers = make_client(tmp_path, monkeypatch, SlowResolver(delay=0))
    body = client.post(
        "/v1/answer",
        json={"query": "Question avec alias ?", "category": "facturation", "task": "facture"},
        headers=headers,
    ).json()
    assert body["status"] == "answered" and body["domain"] == "facturation"
    assert client.post("/v1/answer", json={"q": "Autre alias ?"}, headers=headers).status_code == 200
    # Le contrat publié ne change pas : seuls les noms officiels apparaissent dans le schéma.
    schema = client.get("/openapi.json").json()["components"]["schemas"]["AnswerRequest"]["properties"]
    assert set(schema) == {"question", "domain", "context"}


def test_mcp_ask_accepts_argument_aliases(tmp_path, monkeypatch):
    client, headers = make_client(tmp_path, monkeypatch, SlowResolver(delay=0))

    async def run():
        async with Client(create_server(client, headers["X-API-Key"])) as mcp:
            schema = (await mcp.list_tools()).tools
            result = await mcp.call_tool("ask", {"query": "Question MCP ?", "topic": "formation"})
            return schema, result

    tools, result = anyio.run(run)
    ask_tool = next(t for t in tools if t.name == "ask")
    assert set(ask_tool.input_schema["properties"]) == {"question", "domain", "context"}
    assert not result.is_error and result.structured_content["domain"] == "formation"


# --- adresse du client --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("forwarded", "peer", "expected"),
    [
        ("203.0.113.9", "127.0.0.1", "203.0.113.9"),
        # Adresse ajoutée en tête par le client : ignorée, on garde celle posée par le proxy.
        ("1.2.3.4, 203.0.113.9", "127.0.0.1", "203.0.113.9"),
        ("1.2.3.4, 203.0.113.9, 172.18.0.1", "127.0.0.1", "203.0.113.9"),
        ("", "198.51.100.7", "198.51.100.7"),
        ("", "127.0.0.1", "127.0.0.1"),
        ("10.0.0.5", "127.0.0.1", "10.0.0.5"),
    ],
)
def test_client_address_ignores_spoofed_prefixes(forwarded, peer, expected):
    assert client_address(forwarded, peer) == expected


def test_anonymous_limit_cannot_be_bypassed_by_spoofing(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch, SlowResolver(delay=0), ANON_DAILY_LIMIT=2)
    codes = [
        client.post(
            "/v1/answer", json={"question": f"Question {i} ?"}, headers={"X-Forwarded-For": f"9.9.9.{i}, 203.0.113.50"}
        ).status_code
        for i in range(3)
    ]
    assert codes == [200, 200, 429]


# --- idempotence (préparation de la facturation) -------------------------------------------


def test_idempotent_retry_is_served_once_and_billed_once(tmp_path, monkeypatch):
    resolver = SlowResolver(delay=0)
    client, headers = make_client(tmp_path, monkeypatch, resolver)
    idem = {**headers, "Idempotency-Key": "commande-1"}
    first = ask(client, idem)
    retry = ask(client, idem)
    assert first.json() == retry.json() and retry.headers.get("Idempotent-Replayed") == "true"
    assert resolver.calls == 1
    assert len(client.get("/internal/requests", headers=ADMIN).json()) == 1
    assert [k["used"] for k in client.get("/internal/keys", headers=ADMIN).json() if k["label"] == "moteur"] == [1]
    # Même clé, autre demande : refus explicite.
    assert ask(client, idem, "Une tout autre question ?").status_code == 422


def test_transient_failure_is_not_frozen_by_idempotency(tmp_path, monkeypatch):
    resolver = SlowResolver(delay=0, fail_with=ProviderError("panne"))
    client, headers = make_client(tmp_path, monkeypatch, resolver)
    idem = {**headers, "Idempotency-Key": "essai-2"}
    assert ask(client, idem).json()["reason"] == "provider_error"
    resolver.fail_with = None
    second = ask(client, idem).json()
    assert second["status"] == "answered" and resolver.calls == 2


def test_idempotency_pending_and_anonymous_scope(tmp_path, monkeypatch):
    client, headers = make_client(tmp_path, monkeypatch, SlowResolver(delay=0))
    store = client.app.state.store
    body = {"question": "x y z", "domain": None, "context": None}
    fingerprint = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    store.idempotency_begin(headers["X-API-Key"], "en-cours", fingerprint, time.time(), 3600)
    busy = client.post("/v1/answer", json={"question": "x y z"}, headers={**headers, "Idempotency-Key": "en-cours"})
    assert busy.status_code == 409 and busy.headers["Retry-After"] == "2"
    # Sans clé d'API, la même Idempotency-Key venant de deux adresses reste indépendante.
    a = ask(client, {"Idempotency-Key": "k", "X-Forwarded-For": "203.0.113.1"}, "Question A ?")
    b = ask(client, {"Idempotency-Key": "k", "X-Forwarded-For": "203.0.113.2"}, "Question B ?")
    assert a.status_code == b.status_code == 200 and a.json()["question"] != b.json()["question"]


# --- moteur OpenRouter (réponses simulées, aucun appel réseau) ------------------------------


def _openrouter(handler):
    from app.resolver import OpenRouterResolver

    return OpenRouterResolver("sk-or-test", http=httpx.Client(transport=httpx.MockTransport(handler)))


def _completion(content, annotations=(), cost=0.0123, finish="stop"):
    message = {"role": "assistant", "content": content, "annotations": list(annotations)}
    return {"choices": [{"message": message, "finish_reason": finish}], "usage": {"cost": cost}}


def test_openrouter_answer_uses_citations_and_real_cost():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers["authorization"]
        citation = {
            "type": "url_citation",
            "url_citation": {"url": "https://travail-emploi.gouv.fr/q", "title": "Qualiopi"},
        }
        text = 'Voici la réponse. {"answer": "7 critères.", "domain": "formation", "confidence": 0.85, "sources": []}'
        return httpx.Response(200, json=_completion(text, [citation]))

    resolution = _openrouter(handler).resolve("Combien de critères Qualiopi ?", "formation")
    assert resolution.answer == "7 critères." and resolution.domain == "formation"
    assert resolution.sources == [{"url": "https://travail-emploi.gouv.fr/q", "title": "Qualiopi"}]
    assert resolution.cost_eur == pytest.approx(0.0123 * config.USD_TO_EUR)
    assert seen["auth"] == "Bearer sk-or-test"
    assert seen["body"]["model"] == config.OPENROUTER_MODEL and seen["body"]["plugins"][0]["id"] == "web"


def test_openrouter_without_source_abstains():
    text = '{"answer": "oui", "domain": "general", "confidence": 0.9, "sources": []}'
    resolution = _openrouter(lambda r: httpx.Response(200, json=_completion(text))).resolve("Q ?", None)
    assert resolution.answer is None and resolution.reason == "no_source"


@pytest.mark.parametrize("status", [402, 429, 500])
def test_openrouter_http_errors_are_provider_errors(status):
    with pytest.raises(ProviderError):
        _openrouter(lambda r: httpx.Response(status, json={"error": {"message": "x"}})).resolve("Q ?", None)


def test_openrouter_timeout_is_classified():
    def handler(request):
        raise httpx.ReadTimeout("lent", request=request)

    with pytest.raises(ProviderTimeout):
        _openrouter(handler).resolve("Q ?", None)


def test_default_resolver_prefers_anthropic_then_openrouter(monkeypatch):
    from app.main import default_resolver
    from app.resolver import OpenRouterResolver

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert isinstance(default_resolver(), NullResolver)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-x")
    assert isinstance(default_resolver(), OpenRouterResolver)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    assert isinstance(default_resolver(), ClaudeResolver)
