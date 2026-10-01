"""Faits reliés à leurs sources (idée de Parallel) et période de validité des faits (idée de HiveMind)."""

import json
import time
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import create_app
from app.resolver import Resolution, _resolution_from_text
from app.store import Store

LEGI = "https://www.legifrance.gouv.fr/jorf/id/X"
BLOG = "https://blog.exemple.fr/article"


def day(offset_days: int) -> str:
    return (datetime.now(UTC) + timedelta(days=offset_days)).date().isoformat()


def final(**extra) -> str:
    base = {
        "answer": "33 indicateurs",
        "domain": "formation",
        "confidence": 0.9,
        "sources": [{"url": LEGI, "title": "Décret"}, {"url": BLOG, "title": "Blog"}],
    }
    return json.dumps({**base, **extra})


def test_claims_keep_only_urls_retained_as_sources():
    r = _resolution_from_text(
        final(
            claims=[
                {"text": "Le référentiel compte 33 indicateurs.", "sources": [LEGI, "https://inventee.fr"]},
                {"text": "Fait sans source retenue.", "sources": ["https://inventee.fr"]},
                {"text": "  ", "sources": [LEGI]},
                "pas un objet",
                {"text": "Applicable au 1er novembre 2026.", "sources": [LEGI, LEGI, BLOG]},
            ]
        ),
        [],
        "formation",
        0.0,
    )
    assert r.claims == [
        {"text": "Le référentiel compte 33 indicateurs.", "sources": [LEGI]},
        {"text": "Applicable au 1er novembre 2026.", "sources": [LEGI, BLOG]},
    ]


def test_answer_without_claims_is_still_valid():
    r = _resolution_from_text(final(), [], "formation", 0.0)
    assert r.answer and r.claims == [] and r.valid_from is None and r.valid_until is None


def test_validity_dates_are_checked_never_invented():
    r = _resolution_from_text(final(valid_from="2026-11-01", valid_until="pas une date"), [], "formation", 0.0)
    assert (r.valid_from, r.valid_until) == ("2026-11-01", None)


class Fixed:
    def __init__(self, resolution):
        self.resolution = resolution
        self.calls = 0

    def resolve(self, question, domain_hint):
        self.calls += 1
        return self.resolution


def ask(tmp_path, resolution):
    client = TestClient(create_app(Store(str(tmp_path / "t.sqlite3")), Fixed(resolution)))
    return client.post("/v1/answer", json={"question": "Quel référentiel ?", "domain": "formation"}).json()


def answer(**kw) -> Resolution:
    return Resolution("33 indicateurs", "formation", 0.9, [{"url": LEGI, "title": "Décret"}], 0.01, **kw)


def test_claims_and_validity_are_returned_and_kept_in_memory(tmp_path):
    store = Store(str(tmp_path / "t.sqlite3"))
    engine = Fixed(answer(claims=[{"text": "33 indicateurs.", "sources": [LEGI]}], valid_from=day(-30)))
    client = TestClient(create_app(store, engine))
    first = client.post("/v1/answer", json={"question": "Quel référentiel ?", "domain": "formation"}).json()
    again = client.post("/v1/answer", json={"question": "Quel référentiel ?", "domain": "formation"}).json()
    assert again["cached"] is True and engine.calls == 1
    for body in (first, again):
        assert body["claims"] == [{"text": "33 indicateurs.", "sources": [LEGI]}]
        assert body["valid_from"] == day(-30) and body["valid_until"] is None and body["in_force"] is True


def test_rule_not_yet_in_force_is_researched_on_its_start_date(tmp_path):
    start = day(1)  # demain : avant la fin de la durée de garde du domaine (1 jour + quelques heures)
    body = ask(tmp_path, answer(valid_from=start))
    assert body["in_force"] is False
    start_ts = datetime.fromisoformat(start).replace(tzinfo=UTC).timestamp()
    assert body["expires_at"] == start_ts  # recherchée à nouveau le jour de l'entrée en vigueur


def test_value_ending_soon_is_not_served_after_its_end(tmp_path):
    end = day(1)
    body = ask(tmp_path, answer(valid_until=end))
    assert body["in_force"] is True
    assert body["expires_at"] <= datetime.fromisoformat(end).replace(tzinfo=UTC).timestamp()


def test_far_dates_keep_the_domain_freshness(tmp_path):
    body = ask(tmp_path, answer(valid_from=day(400), valid_until=day(800)))
    assert body["expires_at"] - body["fetched_at"] == 86400  # durée du domaine « formation »
    assert body["in_force"] is False


def test_without_dates_in_force_is_unknown(tmp_path):
    body = ask(tmp_path, answer())
    assert body["expires_at"] - body["fetched_at"] == 86400 and body["in_force"] is None


def test_rule_already_ended_is_reported_not_in_force(tmp_path):
    body = ask(tmp_path, answer(valid_until=day(-1)))
    assert body["in_force"] is False and body["expires_at"] > time.time()
