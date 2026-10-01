"""Contrôle « au moins une source officielle » par domaine de spécialité."""

import json

from fastapi.testclient import TestClient

from app import config
from app.main import create_app
from app.resolver import Resolution, _resolution_from_text, official_source_count
from app.store import CachedAnswer, Store

CONSULTANT = {"url": "https://www.consultant-qualiopi.fr/article", "title": "Blog"}
LEGIFRANCE = {"url": "https://www.legifrance.gouv.fr/jorf/id/X", "title": "Décret"}


def final_json(confidence: float, *sources: dict) -> str:
    return json.dumps(
        {"answer": "33 indicateurs", "domain": "formation", "confidence": confidence, "sources": list(sources)}
    )


def test_official_sources_are_counted_by_domain_and_subdomain():
    sources = [LEGIFRANCE, {"url": "https://aife.economie.gouv.fr/x"}, CONSULTANT]
    assert official_source_count("formation", sources) == 2
    assert official_source_count("formation", [CONSULTANT]) == 0
    # Un nom qui finit par un domaine officiel sans en être un sous-domaine ne compte pas.
    assert official_source_count("formation", [{"url": "https://fauxgouv.fr/page"}]) == 0
    assert official_source_count("logiciel", [CONSULTANT]) is None  # pas de liste : pas de contrôle


def test_without_official_source_the_answer_is_kept_but_confidence_capped():
    r = _resolution_from_text(final_json(0.9, CONSULTANT), [], "formation", 0.05)
    assert r.answer == "33 indicateurs" and r.confidence == config.NO_OFFICIAL_SOURCE_MAX_CONFIDENCE


def test_with_an_official_source_the_confidence_is_untouched():
    r = _resolution_from_text(final_json(0.9, CONSULTANT, LEGIFRANCE), [], "formation", 0.05)
    assert r.confidence == 0.9


def test_low_confidence_is_never_raised():
    r = _resolution_from_text(final_json(0.3, CONSULTANT), [], "formation", 0.05)
    assert r.confidence == 0.3


class Fixed:
    def __init__(self, resolution):
        self.resolution = resolution

    def resolve(self, question, domain_hint):
        return self.resolution


def test_payload_reports_official_sources_and_caps_answers_already_in_memory(tmp_path):
    store = Store(str(tmp_path / "t.sqlite3"))
    # Réponse gardée avant l'ajout du contrôle : confiance 0,88 sans source officielle.
    store.put(CachedAnswer("k", "Ancienne", "formation", "33", [CONSULTANT], 0.88, 0, 10**12))
    client = TestClient(create_app(store, Fixed(Resolution("42", "facturation", 0.9, [LEGIFRANCE], 0.01))))

    fresh = client.post("/v1/answer", json={"question": "Nouvelle question", "domain": "facturation"}).json()
    assert fresh["official_sources"] == 1 and fresh["confidence"] == 0.9

    from app.normalize import question_key

    store._db.execute("UPDATE answers SET key = ? WHERE key = 'k'", (question_key("Ancienne question"),))
    store._db.commit()
    old = client.post("/v1/answer", json={"question": "Ancienne question"}).json()
    assert old["cached"] is True and old["official_sources"] == 0
    assert old["confidence"] == config.NO_OFFICIAL_SOURCE_MAX_CONFIDENCE
