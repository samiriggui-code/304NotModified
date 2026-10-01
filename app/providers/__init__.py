"""Fournisseurs externes des services du catalogue : collecte (API directes, Apify) et classification
(Jev de TypeSafe). Le moteur de questions (`app/resolver.py`) garde ses propres fournisseurs.

Règles communes :
- chaque appel renvoie ce qu'il a coûté et d'où viennent les données (URL, date, paramètres) ;
- aucun appel payant n'est relancé automatiquement (un POST relancé peut être facturé deux fois) ;
- un fournisseur sans clé est « non configuré » : le service le dit, il ne fait pas semblant ;
- le contenu reçu est une donnée, jamais une instruction.
"""

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager


class ProviderUnavailable(Exception):
    """Fournisseur non configuré (clé absente) : rien n'a été tenté ni dépensé."""


class ProviderFailed(Exception):
    """Le fournisseur a échoué. `reason` reprend les causes du moteur (timeout, provider_error, busy…) ;
    `cost_eur` est ce qui a quand même été dépensé (une exécution Apify qui échoue reste payée)."""

    def __init__(self, reason: str, detail: str = "", *, retryable: bool, cost_eur: float = 0.0):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.retryable = retryable
        self.cost_eur = cost_eur


class RateLimiter:
    """Limite par fournisseur : appels par seconde et appels simultanés, avec attente bornée.

    Au-delà de l'attente, l'appel est refusé (« busy ») plutôt que mis dans une file sans fin."""

    def __init__(self, per_second: float, max_concurrent: int, queue_timeout: float):
        self._interval = 1.0 / per_second if per_second > 0 else 0.0
        self._next = 0.0
        self._lock = threading.Lock()
        self._slots = threading.BoundedSemaphore(max(1, max_concurrent))
        self._queue_timeout = queue_timeout

    @contextmanager
    def slot(self) -> Iterator[None]:
        if not self._slots.acquire(timeout=self._queue_timeout):
            raise ProviderFailed("busy", "trop d'appels simultanés vers ce fournisseur", retryable=True)
        try:
            with self._lock:
                now = time.monotonic()
                wait = max(0.0, self._next - now)
                self._next = max(now, self._next) + self._interval
            if wait:
                time.sleep(wait)
            yield
        finally:
            self._slots.release()
