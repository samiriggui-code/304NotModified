from types import SimpleNamespace as NS

from app import config
from app.normalize import normalize_question, question_key
from app.resolver import ClaudeResolver, _parse_final_json


def usage(inp=1000, out=500, searches=2):
    return NS(
        input_tokens=inp,
        output_tokens=out,
        cache_creation_input_tokens=0,
        server_tool_use=NS(web_search_requests=searches),
    )


def message(content, stop_reason="end_turn"):
    return NS(content=content, stop_reason=stop_reason, usage=usage())


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.beta = NS(messages=NS(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        return self.responses.pop(0)


FINAL = '{"answer": "3.13", "domain": "logiciel", "confidence": 0.8, "sources": [{"url": "https://python.org", "title": "Python"}]}'


def test_parses_answer_and_merges_citations():
    text = NS(
        type="text",
        text="Voici. " + FINAL,
        citations=[NS(url="https://docs.python.org", title="Docs"), NS(url="https://python.org", title="Python")],
    )
    client = FakeClient([message([text])])
    result = ClaudeResolver(client).resolve("Dernière version de Python ?", None)

    assert result.answer == "3.13"
    assert result.domain == "logiciel"
    assert [s["url"] for s in result.sources] == ["https://python.org", "https://docs.python.org"]
    assert result.cost_eur > 0
    request = client.requests[0]
    assert request["tools"][0]["type"] == "web_search_20260209"
    assert request["fallbacks"] == "default"


def test_continues_after_pause_turn():
    paused = message([NS(type="text", text="Je cherche…", citations=None)], stop_reason="pause_turn")
    done = message([NS(type="text", text=FINAL, citations=None)])
    client = FakeClient([paused, done])
    result = ClaudeResolver(client).resolve("q", None)

    assert result.answer == "3.13"
    assert len(client.requests) == 2
    assert client.requests[1]["messages"][-1]["role"] == "assistant"


def test_refusal_and_sourceless_answers_are_not_cached():
    refused = ClaudeResolver(FakeClient([message([], stop_reason="refusal")])).resolve("q", None)
    no_source = '{"answer": "oui", "domain": "general", "confidence": 1, "sources": []}'
    unsourced = ClaudeResolver(FakeClient([message([NS(type="text", text=no_source, citations=None)])])).resolve(
        "q", None
    )

    assert refused.answer is None
    assert unsourced.answer is None


def test_domain_hint_wins_and_unknown_domain_falls_back():
    text = NS(type="text", text=FINAL.replace("logiciel", "astrologie"), citations=None)
    assert ClaudeResolver(FakeClient([message([text])])).resolve("q", None).domain == config.DEFAULT_DOMAIN
    text = NS(type="text", text=FINAL, citations=None)
    assert ClaudeResolver(FakeClient([message([text])])).resolve("q", "prix").domain == "prix"


def test_parse_final_json_takes_last_object():
    assert _parse_final_json('avant {"x": 1} puis ' + FINAL)["answer"] == "3.13"
    assert _parse_final_json("pas de json") is None


def test_normalization():
    assert normalize_question("  Quelle   est la RÉPONSE ?! ") == "quelle est la reponse"
    assert question_key("Café ?") == question_key("cafe")


def test_software_guidance_is_sent_to_the_researcher():
    client = FakeClient([message([NS(type="text", text=FINAL, citations=None)])])
    ClaudeResolver(client).resolve("Comment créer un serveur MCP en Python ?", "logiciel")

    system = client.requests[0]["system"]
    assert "notes de version" in system and "guides de migration" in system


def test_regulation_guidance_points_to_official_sources():
    client = FakeClient([message([NS(type="text", text=FINAL, citations=None)])])
    ClaudeResolver(client).resolve("Une PME doit-elle émettre des factures électroniques ?", "reglementation")

    system = client.requests[0]["system"]
    assert "Légifrance" in system and "impots.gouv.fr" in system
    assert "conseil personnalisé" in system


def test_einvoicing_guidance_asks_for_spec_versions():
    client = FakeClient([message([NS(type="text", text=FINAL, citations=None)])])
    ClaudeResolver(client).resolve("Quelle version de la norme XP Z12-013 ?", "facturation")

    system = client.requests[0]["system"]
    assert "XP Z12-013" in system and "numéro de version" in system
