import pytest
from fastapi.testclient import TestClient

from app import admin_auth, config
from app.main import create_app
from app.store import Store

PASSWORD = "un-mot-de-passe-solide"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "")
    monkeypatch.setattr(config, "ADMIN_EMAIL", "moi@exemple.fr")
    monkeypatch.setattr(config, "ADMIN_PASSWORD_HASH", admin_auth.hash_password(PASSWORD))
    monkeypatch.setattr(config, "SESSION_SECRET", "secret-de-test")
    return TestClient(create_app(Store(str(tmp_path / "a.sqlite3"))))


def login(client, email="moi@exemple.fr", password=PASSWORD, ip="1.2.3.4"):
    return client.post(
        "/internal/auth/login", json={"email": email, "password": password}, headers={"X-Forwarded-For": ip}
    )


def test_login_gives_a_session_that_opens_internal_routes(client):
    response = login(client, email="  MOI@exemple.fr ")
    assert response.status_code == 200
    token = response.json()["access_token"]
    bearer = {"Authorization": f"Bearer {token}"}

    assert client.get("/internal/auth/me", headers=bearer).json() == {"email": "moi@exemple.fr"}
    assert client.get("/internal/stats", headers=bearer).status_code == 200
    assert client.get("/internal/stats").status_code == 403


def test_wrong_credentials_are_refused_then_locked(client):
    assert login(client, password="faux").status_code == 401
    assert login(client, email="autre@exemple.fr").status_code == 401
    for _ in range(admin_auth.MAX_FAILURES - 2):
        login(client, password="faux")
    # Bloqué même avec le bon mot de passe, pour cette adresse seulement.
    assert login(client).status_code == 429
    assert login(client, ip="5.6.7.8").status_code == 200


def test_forged_or_expired_tokens_are_refused(client):
    token = login(client).json()["access_token"]
    payload, _signature = token.rsplit(".", 1)
    forged = admin_auth.make_session_token("moi@exemple.fr", "autre-secret")
    expired = admin_auth.make_session_token("moi@exemple.fr", "secret-de-test", ttl=-1)
    other_user = admin_auth.make_session_token("pirate@exemple.fr", "secret-de-test")
    for bad in (forged, expired, other_user, payload + ".x", "n'importe quoi"):
        assert client.get("/internal/auth/me", headers={"Authorization": f"Bearer {bad}"}).status_code == 403


def test_login_refused_when_not_configured(client, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_PASSWORD_HASH", "")
    assert login(client).status_code == 503


def test_password_hash_roundtrip():
    stored = admin_auth.hash_password("abc")
    assert admin_auth.verify_password("abc", stored)
    assert not admin_auth.verify_password("abd", stored)
    assert not admin_auth.verify_password("abc", "pas-une-empreinte")
