"""Connexion du propriétaire au tableau de bord : e-mail + mot de passe, jeton de session signé.

- Le mot de passe n'est jamais stocké : seulement son empreinte scrypt (ADMIN_PASSWORD_HASH),
  produite par `python -m app.cli hash-password`.
- Le jeton de session est signé (HMAC-SHA256 avec SESSION_SECRET) et expire : aucune table de
  sessions à gérer. Changer SESSION_SECRET déconnecte tout le monde.
- Après plusieurs échecs, la connexion est bloquée un moment (protection contre les essais en rafale).
"""

import base64
import hashlib
import hmac
import json
import secrets
import threading
import time

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1
SESSION_TTL_SECONDS = 12 * 3600
MAX_FAILURES = 5
LOCK_SECONDS = 15 * 60


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        computed = hashlib.scrypt(password.encode(), salt=_unb64(salt), n=int(n), r=int(r), p=int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(computed, _unb64(digest))


def make_session_token(email: str, secret: str, ttl: int = SESSION_TTL_SECONDS) -> str:
    payload = _b64(json.dumps({"sub": email, "exp": int(time.time()) + ttl}).encode())
    signature = _b64(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{signature}"


def read_session_token(token: str, secret: str) -> str | None:
    """Renvoie l'e-mail du jeton s'il est authentique et non expiré, sinon None."""
    if not secret or "." not in token:
        return None
    payload, signature = token.rsplit(".", 1)
    expected = _b64(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        data = json.loads(_unb64(payload))
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict) or data.get("exp", 0) < time.time():
        return None
    return data.get("sub")


class LoginThrottle:
    """Compte les échecs par clé (adresse IP) et bloque après MAX_FAILURES pendant LOCK_SECONDS."""

    def __init__(self):
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def locked_for(self, key: str) -> int:
        with self._lock:
            recent = [t for t in self._failures.get(key, []) if t > time.time() - LOCK_SECONDS]
            self._failures[key] = recent
            if len(recent) < MAX_FAILURES:
                return 0
            return int(recent[-MAX_FAILURES] + LOCK_SECONDS - time.time()) + 1

    def failure(self, key: str) -> None:
        with self._lock:
            self._failures.setdefault(key, []).append(time.time())

    def success(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
