"""Fichiers de découverte publics : robots.txt, sitemap.xml, preuve de propriété pour le registre MCP."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app import config
from app.main import REGISTRY_AUTH_FILE, create_app
from app.resolver import NullResolver
from app.store import Store

ROOT = Path(__file__).resolve().parent.parent


def client(tmp_path):
    return TestClient(create_app(Store(str(tmp_path / "t.sqlite3")), NullResolver()))


def test_robots_welcome_crawlers_and_point_to_the_sitemap(tmp_path):
    text = client(tmp_path).get("/robots.txt").text
    assert "User-agent: *\nAllow: /" in text and "Disallow: /admin" in text
    assert f"Sitemap: {config.PUBLIC_URL}/sitemap.xml" in text


def test_sitemap_lists_the_public_pages(tmp_path):
    response = client(tmp_path).get("/sitemap.xml")
    assert response.headers["content-type"].startswith("application/xml")
    assert f"<loc>{config.PUBLIC_URL}/llms.txt</loc>" in response.text


def test_registry_proof_is_a_public_key_only(tmp_path):
    body = client(tmp_path).get("/.well-known/mcp-registry-auth").text.strip()
    assert body == REGISTRY_AUTH_FILE.read_text(encoding="utf-8").strip()
    assert body.startswith("v=MCPv1; k=ed25519; p=") and "PRIVATE" not in body


def test_server_json_matches_the_public_service():
    server = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    assert server["name"] == "com.304notfound/304notmodified"  # domaine 304notfound.com à l'envers
    assert server["remotes"][0]["url"] == f"{config.PUBLIC_URL}/mcp"
    assert len(server["description"]) <= 100  # limite du registre officiel
