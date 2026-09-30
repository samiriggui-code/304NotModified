"""Coordination des recherches fraîches : une seule recherche par question à la fois, et un
nombre borné de recherches payantes simultanées.

Correctif propre à 304NotModified (le moteur de Context7 est privé, rien n'est repris ici) :
- déduplication des travaux en cours (« single-flight ») : si dix agents posent la même question
  (même clé normalisée) pendant qu'une recherche tourne, une seule recherche est payée ; les autres
  attendent son résultat puis relisent le cache. La clé est celle du cache : on ne mutualise jamais
  deux questions seulement « proches ».
- limite de concurrence avec attente bornée (backpressure) : au-delà, l'agent reçoit tout de suite
  « busy » et un délai conseillé, plutôt qu'une file qui grossit sans limite.
- une recherche qui échoue n'est pas relancée par les agents qui l'attendaient : ils reçoivent la
  même cause, ce qui évite de multiplier les appels vers un fournisseur en panne.
"""

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from .resolver import ProviderError, ProviderTimeout, Resolution

log = logging.getLogger("304notmodified.engine")


@dataclass
class Outcome:
    resolution: Resolution
    shared: bool  # True : résultat d'une recherche lancée par une autre requête


class _Flight:
    def __init__(self):
        self.done = threading.Event()
        self.resolution: Resolution | None = None


class SearchCoordinator:
    def __init__(self, max_concurrent: int, queue_timeout: float, flight_timeout: float):
        self._slots = threading.BoundedSemaphore(max(1, max_concurrent))
        self._queue_timeout = queue_timeout
        # Un agent qui attend la recherche d'un autre n'attend jamais plus que la recherche elle-même.
        self._flight_timeout = flight_timeout
        self._flights: dict[str, _Flight] = {}
        self._lock = threading.Lock()
        self.searches_started = 0  # pour les tests et le suivi

    def in_flight(self) -> int:
        with self._lock:
            return len(self._flights)

    def resolve(self, key: str, domain: str, search: Callable[[], Resolution]) -> Outcome:
        with self._lock:
            flight = self._flights.get(key)
            leader = flight is None
            if leader:
                flight = self._flights[key] = _Flight()

        if not leader:
            if not flight.done.wait(self._flight_timeout):
                return Outcome(Resolution(None, domain, 0.0, reason="timeout"), shared=True)
            # Le coût a été payé par la requête meneuse : on ne le compte qu'une fois.
            shared = flight.resolution or Resolution(None, domain, 0.0, reason="internal_error")
            return Outcome(
                Resolution(shared.answer, shared.domain, shared.confidence, shared.sources, 0.0, shared.reason), True
            )

        try:
            flight.resolution = self._run(domain, search)
            return Outcome(flight.resolution, shared=False)
        finally:
            with self._lock:
                self._flights.pop(key, None)
            flight.done.set()

    def _run(self, domain: str, search: Callable[[], Resolution]) -> Resolution:
        if not self._slots.acquire(timeout=self._queue_timeout):
            log.warning("recherche refusée : %s recherches déjà en cours", self.in_flight())
            return Resolution(None, domain, 0.0, reason="busy")
        started = time.monotonic()
        try:
            self.searches_started += 1
            resolution = search()
        except ProviderTimeout:
            resolution = Resolution(None, domain, 0.0, reason="timeout")
        except ProviderError as exc:
            log.error("fournisseur en erreur : %s", exc)
            resolution = Resolution(None, domain, 0.0, reason="provider_error")
        except Exception:
            log.exception("échec inattendu de la recherche")
            resolution = Resolution(None, domain, 0.0, reason="internal_error")
        finally:
            self._slots.release()
        if resolution.answer is None and resolution.reason is None:
            resolution.reason = "no_reliable_answer"
        log.info(
            "recherche domaine=%s issue=%s durée_ms=%d coût_eur=%.4f",
            resolution.domain,
            "réponse" if resolution.answer else resolution.reason,
            (time.monotonic() - started) * 1000,
            resolution.cost_eur,
        )
        return resolution
