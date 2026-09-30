"""Serveur MCP distant (Streamable HTTP), servi sous https://<domaine>/mcp.

Comme la version locale, il ne fait que relayer vers l'API (`POST /v1/answer`, `POST /v1/feedback`) :
aucun accès à la base. Chaque agent présente sa clé dans l'en-tête X-API-Key (ou Authorization:
Bearer) ; sans clé, l'API applique sa limite d'accès sans clé.

Lancement :
    NM304_URL=http://127.0.0.1:8304 uvicorn mcp_server.http:create_http_app --factory --port 8305
"""

import os
from urllib.parse import urlparse

import httpx
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette

from app import config

from .server import DEFAULT_URL, TIMEOUT_SECONDS, create_server


def create_http_app(http: httpx.Client | None = None) -> Starlette:
    http = http or httpx.Client(base_url=os.environ.get("NM304_URL", DEFAULT_URL).rstrip("/"), timeout=TIMEOUT_SECONDS)
    host = urlparse(config.PUBLIC_URL).hostname or "localhost"
    # Protection contre le « DNS rebinding » : seuls le domaine public et la machine elle-même sont acceptés.
    security = TransportSecuritySettings(
        allowed_hosts=[host, f"{host}:*", "127.0.0.1:*", "localhost:*"],
        allowed_origins=[config.PUBLIC_URL, "http://127.0.0.1:*", "http://localhost:*"],
    )
    return create_server(http, remote=True).streamable_http_app(
        streamable_http_path="/mcp",
        # Sans état ni flux : chaque appel d'outil est une requête HTTP simple (derrière un proxy, c'est le plus sûr).
        stateless_http=True,
        json_response=True,
        transport_security=security,
    )
