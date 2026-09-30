"""Mesures du moteur (latence, coûts, clients qui reviennent, erreurs de réutilisation) et motifs de retour."""

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import create_app
from app.resolver import Resolution
from app.store import Store

ADMIN = {"Authorization": "Bearer test-admin"}


class FakeResolver:
    def resolve(self, question, domain_hint):
        if "inconnu" in question:
            return Resolution(None, domain_hint or "general", 0.0, cost_eur=0.01, reason="no_reliable_answer")
        return Resolution("42", domain_hint or "logiciel", 0.9, [{"url": "https://exemple.org/s", "title": "S"}], 0.02)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "test-admin")
    store = Store(str(tmp_path / "t.sqlite3"))
    client = TestClient(create_app(store, FakeResolver()))
    key = client.post("/internal/keys", json={"label": "test", "quota": 100}, headers=ADMIN).json()["api_key"]
    return client, store, {"X-API-Key": key}


def ask(client, headers, question, **extra):
    return client.post("/v1/answer", json={"question": question, **extra}, headers=headers).json()


def stats(client):
    return client.get("/internal/stats", headers=ADMIN).json()


def test_new_feedback_issues_are_accepted_and_unknown_refused(setup):
    client, _, headers = setup
    for issue in ("off_topic", "contradiction"):
        request_id = ask(client, headers, f"Question {issue}")["request_id"]
        body = {"request_id": request_id, "useful": False, "issue": issue}
        assert client.post("/v1/feedback", json=body, headers=headers).status_code == 200
    request_id = ask(client, headers, "Autre question")["request_id"]
    refused = {"request_id": request_id, "useful": False, "issue": "inventé"}
    assert client.post("/v1/feedback", json=refused, headers=headers).status_code == 422
    assert stats(client)["feedback"]["issues"] == {"off_topic": 1, "contradiction": 1}


def test_llms_txt_lists_every_feedback_issue(setup):
    client, _, _ = setup
    text = client.get("/llms.txt").text
    assert all(issue in text for issue in config.FEEDBACK_ISSUES)


def test_costs_per_answer_per_useful_answer_and_avoided_searches(setup):
    client, _, headers = setup
    first = ask(client, headers, "Même question")  # recherche aboutie : 0,02 €
    for _ in range(3):
        ask(client, headers, "Même question")  # servies depuis la mémoire
    ask(client, headers, "question inconnu")  # recherche sans réponse : 0,01 € perdus
    client.post("/v1/feedback", json={"request_id": first["request_id"], "useful": True}, headers=headers)

    e = stats(client)["economics"]
    assert e["cost_per_answer_eur"] == pytest.approx(0.03 / 4)
    assert e["cost_per_useful_answer_eur"] == pytest.approx(0.03)
    assert e["avg_search_cost_eur"] == pytest.approx(0.02)
    assert e["unanswered_cost_eur"] == pytest.approx(0.01)
    assert e["avoided_searches"] == 3
    assert e["estimated_avoided_cost_eur"] == pytest.approx(0.06)
    assert e["refresh_searches"] == 0


def test_no_useful_feedback_gives_no_cost_per_useful_answer(setup):
    client, _, headers = setup
    ask(client, headers, "Une question")
    assert stats(client)["economics"]["cost_per_useful_answer_eur"] is None


def test_refresh_of_an_expired_answer_is_counted_apart(setup, monkeypatch):
    client, _, headers = setup
    monkeypatch.setitem(config.DOMAIN_TTL_SECONDS, "prix", -1)  # toute réponse « prix » est aussitôt périmée
    ask(client, headers, "Prix du produit", domain="prix")
    ask(client, headers, "Prix du produit", domain="prix")  # la réponse d'origine a expiré : nouvelle recherche

    e = stats(client)["economics"]
    assert e["refresh_searches"] == 1
    assert e["refresh_cost_eur"] == pytest.approx(0.02)


def test_latency_median_and_95th_percentile(setup):
    client, store, headers = setup
    for i in range(20):
        ask(client, headers, f"Question {i}")
    with store._lock:
        for i, request_id in enumerate(r[0] for r in store._db.execute("SELECT id FROM requests ORDER BY id")):
            store._db.execute("UPDATE requests SET latency_ms = ? WHERE id = ?", ((i + 1) * 10, request_id))
        store._db.commit()

    assert stats(client)["latency_ms"] == {"p50": 100, "p95": 190}


def test_latency_is_empty_without_requests(setup):
    client, _, _ = setup
    assert stats(client)["latency_ms"] == {"p50": None, "p95": None}


def test_returning_clients_exclude_the_shared_anonymous_access(setup):
    client, store, headers = setup
    ask(client, headers, "Question du lundi")
    ask(client, headers, "Question du mercredi")
    ask(client, {}, "Question sans clé")
    ask(client, {}, "Autre question sans clé")
    with store._lock:
        # Une requête de chaque accès deux jours plus tôt : la clé et l'accès sans clé « reviennent ».
        store._db.execute("UPDATE requests SET ts = ts - 2 * 86400 WHERE id IN (1, 3)")
        store._db.commit()

    assert stats(client)["clients_activity"] == {"active": 1, "returning": 1}


def test_reuse_errors_count_only_bad_feedback_on_answers_served_from_memory(setup):
    client, _, headers = setup
    fresh = ask(client, headers, "Question partagée")
    reused = ask(client, headers, "Question partagée")
    assert fresh["cached"] is False and reused["cached"] is True
    for request_id in (fresh["request_id"], reused["request_id"]):
        body = {"request_id": request_id, "useful": False, "issue": "outdated"}
        client.post("/v1/feedback", json=body, headers=headers)

    # Seule la réponse resservie depuis la mémoire compte comme erreur de réutilisation.
    assert stats(client)["feedback"]["reuse_errors"] == 1
