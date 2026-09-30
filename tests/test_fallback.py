"""Relais entre moteurs : OpenRouter prend la question quand Anthropic refuse (crédit épuisé, panne)."""

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import create_app, default_resolver
from app.resolver import (
    ClaudeResolver,
    FallbackResolver,
    NullResolver,
    OpenRouterResolver,
    ProviderError,
    ProviderTimeout,
    Resolution,
)
from app.store import Store

ANSWER = Resolution("42", "logiciel", 0.9, [{"url": "https://exemple.org/s", "title": "S"}], 0.02)


class Engine:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = 0

    def resolve(self, question, domain_hint):
        self.calls += 1
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def test_refused_provider_hands_over_to_the_next():
    first, second = Engine(ProviderError("crédit épuisé")), Engine(ANSWER)
    assert FallbackResolver(first, second).resolve("q", None) is ANSWER
    assert (first.calls, second.calls) == (1, 1)


def test_timeout_is_not_handed_over():
    first, second = Engine(ProviderTimeout("délai")), Engine(ANSWER)
    with pytest.raises(ProviderTimeout):
        FallbackResolver(first, second).resolve("q", None)
    assert second.calls == 0


def test_an_abstention_is_final_and_not_paid_twice():
    abstention = Resolution(None, "general", 0.0, cost_eur=0.01, reason="no_source")
    first, second = Engine(abstention), Engine(ANSWER)
    assert FallbackResolver(first, second).resolve("q", None) is abstention
    assert second.calls == 0


def test_every_provider_down_is_reported_as_provider_error(tmp_path):
    engines = FallbackResolver(Engine(ProviderError("a")), Engine(ProviderError("b")))
    client = TestClient(create_app(Store(str(tmp_path / "t.sqlite3")), engines))
    body = client.post("/v1/answer", json={"question": "Une question"}).json()
    assert body["status"] == "unanswered" and body["reason"] == "provider_error"


def test_answer_through_the_second_provider_is_cached(tmp_path):
    second = Engine(ANSWER)
    client = TestClient(
        create_app(Store(str(tmp_path / "t.sqlite3")), FallbackResolver(Engine(ProviderError("x")), second))
    )
    first = client.post("/v1/answer", json={"question": "Même question"}).json()
    again = client.post("/v1/answer", json={"question": "Même question"}).json()
    assert first["cached"] is False and again["cached"] is True and second.calls == 1


@pytest.mark.parametrize(
    ("keys", "expected"),
    [
        ({"ANTHROPIC_API_KEY": "a", "OPENROUTER_API_KEY": "o"}, FallbackResolver),
        ({"ANTHROPIC_API_KEY": "a"}, ClaudeResolver),
        ({"OPENROUTER_API_KEY": "o"}, OpenRouterResolver),
        ({}, NullResolver),
    ],
)
def test_default_resolver_follows_the_configured_keys(monkeypatch, keys, expected):
    for name in ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    for name, value in keys.items():
        monkeypatch.setenv(name, value)
    resolver = default_resolver()
    assert isinstance(resolver, expected)
    if expected is FallbackResolver:
        assert [type(r) for r in resolver.resolvers] == [ClaudeResolver, OpenRouterResolver]
    assert config.DEFAULT_DOMAIN  # le module de réglages reste importable sans clé
