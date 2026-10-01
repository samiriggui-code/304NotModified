"""Catalogue de services pour agents : contrat publié, devis, budget, exécution, contrôle, facturation.

Le moteur (ce module) garde la main sur tout ce qui engage : droits, devis, budget, choix des
fournisseurs, reprises, facturation et traçabilité. Les fournisseurs (`app/providers/`) collectent ou
classent ; ils ne décident jamais d'une dépense ni d'une permission. HTTP et MCP passent par les mêmes
routes, donc par la même logique.
"""

import hashlib
import json
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

# Postes de coût suivis pour chaque exécution (colonnes de service_runs).
COST_KINDS = ("collect", "classify", "llm", "other")


@dataclass
class Outcome:
    """Ce que produit un service. `status` : completed (livré complet), partial (livré avec un manque
    signalé), failed (rien d'exploitable)."""

    status: str
    result: dict | None = None
    sources: list[dict] = field(default_factory=list)
    limits: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    reason: str | None = None
    retryable: bool = False
    # Un résultat complet peut rester gratuit quand il n'apporte rien (liste vide, par exemple).
    billable: bool = True


class RunContext:
    """Journal des étapes d'une exécution : fournisseur, poste de coût, coût réel, durée, issue."""

    def __init__(self):
        self.steps: list[dict] = []

    def record(
        self, name: str, provider: str, kind: str, status: str, started: float, cost_eur: float = 0.0, detail: str = ""
    ) -> None:
        self.steps.append(
            {
                "step": name,
                "provider": provider,
                "kind": kind,
                "status": status,
                "cost_eur": round(cost_eur, 8),
                "latency_ms": int((time.monotonic() - started) * 1000),
                "detail": detail,
            }
        )

    def cost(self, kind: str) -> float:
        return sum(s["cost_eur"] for s in self.steps if s["kind"] == kind)


@dataclass(frozen=True)
class ServiceSpec:
    id: str
    version: str
    title: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    typical_latency_seconds: str
    freshness: str
    cache_seconds: int
    limits: tuple[str, ...]
    errors: dict[str, str]
    pricing: str
    price: Callable[[Any], float]
    capabilities: Callable[[], dict]
    execute: Callable[[Any, RunContext], Outcome]
    mode: str = "sync"

    def describe(self, public_url: str) -> dict:
        """Contrat publié : ce qu'un agent doit savoir avant d'appeler (et de payer)."""
        return {
            "id": self.id,
            "version": self.version,
            "title": self.title,
            "description": self.description,
            "mode": self.mode,
            "endpoints": {
                "quote": f"{public_url}/v1/services/{self.id}/quote",
                "run": f"{public_url}/v1/services/{self.id}/run",
            },
            "input_schema": self.input_model.model_json_schema(),
            "output_schema": self.output_model.model_json_schema(),
            "pricing": self.pricing,
            "typical_latency_seconds": self.typical_latency_seconds,
            "freshness": self.freshness,
            "limits": list(self.limits),
            "errors": self.errors,
            "capabilities": self.capabilities(),
        }


def fingerprint(params: BaseModel) -> str:
    return hashlib.sha256(json.dumps(params.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()


class SingleFlight:
    """Une seule exécution à la fois pour une même demande (mêmes service, version et paramètres) :
    les demandes identiques arrivées entre-temps attendent puis relisent le résultat gardé."""

    def __init__(self):
        self._lock = threading.Lock()
        self._running: dict[str, threading.Event] = {}

    def run(self, key: str, fn: Callable[[], Outcome], wait_timeout: float) -> Outcome | None:
        """Renvoie le résultat si cette requête a mené l'exécution, None si elle a attendu celle d'une autre."""
        with self._lock:
            event = self._running.get(key)
            leader = event is None
            if leader:
                event = self._running[key] = threading.Event()
        if not leader:
            event.wait(wait_timeout)
            return None
        try:
            return fn()
        finally:
            with self._lock:
                self._running.pop(key, None)
            event.set()
