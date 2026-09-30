import anyio
import httpx
import pytest
from fastapi.testclient import TestClient
from mcp import Client

from app import config
from app.main import create_app
from app.store import Store
from mcp_server.server import create_server
from tests.test_api import ADMIN, FakeResolver


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "test-admin")
    resolver = FakeResolver()
    http = TestClient(create_app(Store(str(tmp_path / "m.sqlite3")), resolver))
    key = http.post("/internal/keys", json={"label": "mcp", "quota": 2}, headers=ADMIN).json()["api_key"]
    return http, resolver, key


def call(server, name, arguments):
    async def run():
        async with Client(server) as client:
            return await client.call_tool(name, arguments)

    return anyio.run(run)


def test_tool_is_listed_as_read_only(api):
    http, _, key = api

    async def run():
        async with Client(create_server(http, key)) as client:
            return (await client.list_tools()).tools

    tools = {t.name: t for t in anyio.run(run)}
    assert set(tools) == {"ask", "feedback"}
    assert tools["ask"].annotations.read_only_hint is True


def test_ask_goes_through_api_and_cache(api):
    http, resolver, key = api
    server = create_server(http, key)

    first = call(server, "ask", {"question": "Quelle est la réponse ?"})
    second = call(server, "ask", {"question": "quelle est la REPONSE", "domain": "logiciel"})

    assert not first.is_error and first.structured_content["cached"] is False
    assert second.structured_content["cached"] is True
    assert second.structured_content["sources"][0]["url"] == "https://exemple.org/source"
    assert resolver.calls == 1


def test_bad_key_and_quota_are_readable_errors(api):
    http, _, key = api

    bad = call(create_server(http, "nm304_faux"), "ask", {"question": "Bonjour ?"})
    assert bad.is_error and "NM304_API_KEY" in bad.content[0].text

    server = create_server(http, key)
    for i in range(2):
        call(server, "ask", {"question": f"question {i}"})
    over = call(server, "ask", {"question": "question 9"})
    assert over.is_error and "Quota" in over.content[0].text


def test_unreachable_service(api):
    _, _, key = api
    down = httpx.Client(base_url="http://127.0.0.1:9", timeout=1)
    result = call(create_server(down, key), "ask", {"question": "Bonjour ?"})
    assert result.is_error and "injoignable" in result.content[0].text


def test_mcp_request_is_recorded_with_client_context_and_feedback(api):
    http, _, key = api
    server = create_server(http, key)

    result = call(server, "ask", {"question": "Quelle est la réponse ?", "context": "rédige une facture"})
    request_id = result.structured_content["request_id"]
    fb = call(server, "feedback", {"request_id": request_id, "useful": False, "issue": "outdated"})
    assert not fb.is_error and fb.structured_content["status"] == "recorded"

    [row] = http.get("/internal/requests", headers=ADMIN).json()
    assert row["channel"] == "mcp" and row["client"] == "mcp:mcp/0.1.0"  # nom annoncé par le client de test
    assert row["context"] == "rédige une facture"
    assert row["answer"] == "42"
    assert row["feedback_useful"] == 0 and row["feedback_issue"] == "outdated"


def test_feedback_on_unknown_request_is_an_error(api):
    http, _, key = api
    result = call(create_server(http, key), "feedback", {"request_id": "req_inconnu", "useful": True})
    assert result.is_error and "request_id" in result.content[0].text
