import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import create_app
from app.resolver import NullResolver, Resolution
from app.store import Store

ADMIN = {"Authorization": "Bearer test-admin"}


class FakeResolver:
    def __init__(self):
        self.calls = 0

    def resolve(self, question, domain_hint):
        self.calls += 1
        if "inconnu" in question:
            return Resolution(None, domain_hint or "general", 0.0, cost_eur=0.01)
        return Resolution(
            answer="42",
            domain=domain_hint or "logiciel",
            confidence=0.9,
            sources=[{"url": "https://exemple.org/source", "title": "Source"}],
            cost_eur=0.02,
        )


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "test-admin")
    resolver = FakeResolver()
    client = TestClient(create_app(Store(str(tmp_path / "t.sqlite3")), resolver))
    key = client.post("/internal/keys", json={"label": "test", "quota": 3}, headers=ADMIN).json()["api_key"]
    return client, resolver, {"X-API-Key": key}


def test_miss_then_hit_on_equivalent_question(setup):
    client, resolver, headers = setup
    first = client.post("/v1/answer", json={"question": "Quelle est la réponse ?"}, headers=headers).json()
    second = client.post("/v1/answer", json={"question": "  quelle est la REPONSE"}, headers=headers).json()

    assert first["status"] == "answered" and first["cached"] is False
    assert second["answer"] == "42" and second["cached"] is True
    assert second["sources"][0]["url"] == "https://exemple.org/source"
    assert resolver.calls == 1


def test_expired_answer_is_researched(setup, monkeypatch):
    client, resolver, headers = setup
    client.post("/v1/answer", json={"question": "Prix du produit X", "domain": "prix"}, headers=headers)
    monkeypatch.setitem(config.DOMAIN_TTL_SECONDS, "prix", -1)
    client.post("/v1/answer", json={"question": "Prix du produit Y", "domain": "prix"}, headers=headers)
    again = client.post("/v1/answer", json={"question": "Prix du produit Y", "domain": "prix"}, headers=headers).json()

    assert again["cached"] is False
    assert resolver.calls == 3


def test_unanswered_is_logged_and_not_counted(setup):
    client, _, headers = setup
    for _ in range(5):
        body = client.post("/v1/answer", json={"question": "question inconnu"}, headers=headers).json()
        assert body["status"] == "unanswered"

    stats = client.get("/internal/stats", headers=ADMIN).json()
    assert stats["outcomes"] == {"unanswered": 5}
    assert stats["top_unanswered_questions"][0]["requests"] == 5
    # Quota de 3 non entamé : une vraie question passe encore.
    assert client.post("/v1/answer", json={"question": "Autre"}, headers=headers).status_code == 200


def test_quota_and_auth(setup):
    client, _, headers = setup
    assert client.post("/v1/answer", json={"question": "abc"}).status_code == 401
    for i in range(3):
        assert client.post("/v1/answer", json={"question": f"q {i}"}, headers=headers).status_code == 200
    assert client.post("/v1/answer", json={"question": "q 9"}, headers=headers).status_code == 429


def test_admin_requires_token(setup):
    client, _, _ = setup
    assert client.get("/internal/stats").status_code == 403
    assert client.get("/internal/stats", headers={"Authorization": "Bearer faux"}).status_code == 403


def test_stats_measure_repeat_rate_and_margin(setup):
    client, _, headers = setup
    for _ in range(3):
        client.post("/v1/answer", json={"question": "Même question"}, headers=headers)
    stats = client.get("/internal/stats", headers=ADMIN).json()

    assert stats["requests"] == 3
    assert stats["distinct_questions"] == 1
    assert stats["repeat_rate"] == pytest.approx(0.667, abs=0.001)
    assert stats["cache_hit_rate"] == pytest.approx(0.667, abs=0.001)
    assert stats["estimated_cost_eur"] == pytest.approx(0.02)
    assert stats["estimated_revenue_eur"] == pytest.approx(3 * config.PRICE_PER_REQUEST_EUR)


def test_null_resolver_measures_demand(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "test-admin")
    client = TestClient(create_app(Store(str(tmp_path / "n.sqlite3")), NullResolver()))
    key = client.post("/internal/keys", json={"label": "n"}, headers=ADMIN).json()["api_key"]
    body = client.post("/v1/answer", json={"question": "Bonjour ?"}, headers={"X-API-Key": key}).json()
    assert body["status"] == "unanswered"


def test_llms_txt(setup):
    client, _, _ = setup
    assert "POST /v1/answer" in client.get("/llms.txt").text


def test_dashboard_data_requires_admin(setup):
    client, _, _ = setup
    assert client.get("/admin").status_code == 404  # le tableau de bord est une application à part (admin/)
    for path in ("/internal/keys", "/internal/requests", "/internal/answers"):
        assert client.get(path).status_code == 403


def test_dashboard_data(setup):
    client, _, headers = setup
    client.post("/v1/answer", json={"question": "Quelle est la réponse ?"}, headers=headers)
    client.post("/v1/answer", json={"question": "question inconnu"}, headers=headers)

    requests = client.get("/internal/requests", headers=ADMIN).json()
    assert [r["outcome"] for r in requests] == ["unanswered", "miss"]
    assert requests[0]["key_label"] == "test"

    [answer] = client.get("/internal/answers", headers=ADMIN).json()
    assert answer["answer"] == "42" and answer["sources"][0]["url"] == "https://exemple.org/source"

    [key] = client.get("/internal/keys", headers=ADMIN).json()
    assert key["label"] == "test" and key["used"] == 1
    assert key["key"] == headers["X-API-Key"][:12] + "…"  # jamais la clé complète


def test_request_id_context_and_client_are_recorded(setup):
    client, _, headers = setup
    body = client.post(
        "/v1/answer",
        json={"question": "Quelle est la réponse ?", "context": "prépare un devis"},
        headers={**headers, "X-Client": "mon-agent/2.1"},
    ).json()
    assert body["request_id"].startswith("req_")

    [row] = client.get("/internal/requests", headers=ADMIN).json()
    assert row["request_id"] == body["request_id"]
    assert (row["channel"], row["client"], row["context"]) == ("http", "mon-agent/2.1", "prépare un devis")
    assert row["answer"] == "42"


def test_feedback_is_recorded_only_for_own_requests(setup):
    client, _, headers = setup
    request_id = client.post("/v1/answer", json={"question": "Quelle est la réponse ?"}, headers=headers).json()[
        "request_id"
    ]
    other = client.post("/internal/keys", json={"label": "autre"}, headers=ADMIN).json()["api_key"]

    fb = {"request_id": request_id, "useful": False, "issue": "wrong", "comment": "date fausse"}
    assert client.post("/v1/feedback", json=fb, headers={"X-API-Key": other}).status_code == 404
    assert client.post("/v1/feedback", json=fb).status_code == 401
    assert client.post("/v1/feedback", json=fb, headers=headers).status_code == 200

    [item] = client.get("/internal/feedback", headers=ADMIN).json()
    assert item["useful"] is False and item["issue"] == "wrong" and item["answer"] == "42"
    # Un retour ne modifie jamais la réponse en mémoire.
    again = client.post("/v1/answer", json={"question": "Quelle est la réponse ?"}, headers=headers).json()
    assert again["answer"] == "42" and again["cached"] is True
    assert client.get("/internal/stats", headers=ADMIN).json()["feedback"] == {
        "count": 1,
        "useful_rate": 0.0,
        "issues": {"wrong": 1},
    }


def test_refreshed_answer_keeps_what_was_served_before(setup, monkeypatch):
    client, _, headers = setup
    monkeypatch.setitem(config.DOMAIN_TTL_SECONDS, "prix", -1)  # expire tout de suite
    client.post("/v1/answer", json={"question": "Prix du X", "domain": "prix"}, headers=headers)
    resolver_answer = FakeResolver.resolve

    def new_answer(self, question, domain_hint):
        r = resolver_answer(self, question, domain_hint)
        r.answer = "43"
        return r

    monkeypatch.setattr(FakeResolver, "resolve", new_answer)
    client.post("/v1/answer", json={"question": "Prix du X", "domain": "prix"}, headers=headers)

    rows = client.get("/internal/requests", headers=ADMIN).json()
    assert [r["answer"] for r in rows] == ["43", "42"]


def test_old_requests_are_purged(tmp_path):
    store = Store(str(tmp_path / "p.sqlite3"))
    store.log(api_key="k", key="q", question="vieille", domain=None, outcome="hit", latency_ms=1)
    store._db.execute("UPDATE requests SET ts = ts - 400 * 86400")
    store.log(api_key="k", key="q", question="récente", domain=None, outcome="hit", latency_ms=1)
    store.purge_older_than(365)
    assert [r["question"] for r in store.recent_requests(10)] == ["récente"]


def test_timeseries_and_period_filter(setup):
    client, _, headers = setup
    for q in ("Même question", "Même question", "question inconnu"):
        client.post("/v1/answer", json={"question": q}, headers=headers)
    store = client.app.state.store
    store._db.execute("UPDATE requests SET ts = ts - 3 * 86400 WHERE outcome = 'unanswered'")
    store._db.commit()

    week = client.get("/internal/timeseries?days=7&bucket=day", headers=ADMIN).json()
    assert sum(b["hit"] + b["miss"] + b["unanswered"] for b in week) == 3
    assert len(week) == 2  # deux jours différents
    today = client.get("/internal/timeseries?days=1&bucket=hour", headers=ADMIN).json()
    assert sum(b["hit"] + b["miss"] for b in today) == 2 and all(b["unanswered"] == 0 for b in today)

    assert client.get("/internal/stats?days=1", headers=ADMIN).json()["requests"] == 2
    assert client.get("/internal/stats", headers=ADMIN).json()["requests"] == 3
    assert client.get("/internal/timeseries").status_code == 403


def test_internal_routes_are_hidden_from_public_docs(setup):
    client, _, _ = setup
    paths = client.get("/openapi.json").json()["paths"]
    assert "/v1/answer" in paths and "/v1/feedback" in paths
    assert not [p for p in paths if p.startswith("/internal")]
