"""Apify : collecte web par « Actors » (extraction de pages, annuaires, surveillance).

Vérifié le 01/10/2026 sur https://docs.apify.com/api/v2 :
- POST https://api.apify.com/v2/actors/:actorId/runs (le chemin documenté est désormais /actors/,
  plus /acts/), jeton dans l'en-tête Authorization: Bearer ;
- waitForFinish : 60 s au plus par appel, ensuite on relit l'exécution ;
- maxTotalChargeUsd : plafond de dépense de l'exécution (tous modèles de prix) ; maxItems : plafond
  d'éléments facturés (Actors payés au résultat) ; timeout : durée maximale en secondes ;
- l'objet exécution donne status, defaultDatasetId et usageTotalUsd (coût réel en dollars).

Aucun Actor n'est choisi ici : le choix se fait par tâche, d'après la qualité observée, le coût et
les conditions d'utilisation du site visé (droit de garder et de resservir les données). Une API
directe est préférée quand elle existe (voir recherche_entreprises.py).
"""

import time
from datetime import UTC, datetime

import httpx

from .. import config
from . import ProviderFailed, ProviderUnavailable, RateLimiter
from .recherche_entreprises import Collection

BASE_URL = "https://api.apify.com/v2"
TERMINAL = {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}


class ApifyCollector:
    def __init__(self, token: str | None, http: httpx.Client | None = None, limiter: RateLimiter | None = None):
        self._token = token
        # waitForFinish garde la connexion ouverte jusqu'à 60 s : délai de lecture au-dessus.
        self._http = http or httpx.Client(base_url=BASE_URL, timeout=75)
        self._limiter = limiter or RateLimiter(
            per_second=5, max_concurrent=config.APIFY_MAX_CONCURRENT_RUNS, queue_timeout=10
        )

    @property
    def configured(self) -> bool:
        return bool(self._token)

    def run_actor(
        self, actor_id: str, run_input: dict, *, max_items: int, max_total_charge_usd: float, timeout_secs: int
    ) -> Collection:
        """Lance un Actor, attend sa fin (au plus timeout_secs), lit son jeu de données. Le coût réel est
        compté même si l'exécution échoue."""
        if not self._token:
            raise ProviderUnavailable("APIFY_TOKEN absent")
        collected_at = datetime.now(UTC).isoformat(timespec="seconds")
        params = {
            "waitForFinish": 60,
            "timeout": timeout_secs,
            "maxItems": max_items,
            "maxTotalChargeUsd": max_total_charge_usd,
        }
        with self._limiter.slot():
            run = self._call("POST", f"/actors/{actor_id}/runs", params=params, json=run_input)
            deadline = time.monotonic() + timeout_secs + 30
            while run.get("status") not in TERMINAL and time.monotonic() < deadline:
                run = self._call("GET", f"/actor-runs/{run['id']}", params={"waitForFinish": 60})
        cost = float(run.get("usageTotalUsd") or 0.0) * config.USD_TO_EUR
        if run.get("status") != "SUCCEEDED":
            raise ProviderFailed(
                "timeout" if run.get("status") in ("TIMED-OUT", None, "RUNNING") else "provider_error",
                f"exécution Apify {run.get('status')}",
                retryable=True,
                cost_eur=cost,
            )
        items = self._call(
            "GET", f"/datasets/{run['defaultDatasetId']}/items", params={"clean": "true", "limit": max_items}
        )
        return Collection(
            items=items if isinstance(items, list) else [],
            source={
                "name": f"Apify, Actor {actor_id}",
                "url": f"https://apify.com/{actor_id.replace('~', '/')}",
                "params": run_input,
                "collected_at": collected_at,
                "run_id": run.get("id"),
            },
            cost_eur=cost,
            calls=1,
        )

    def _call(self, method: str, path: str, **kwargs):
        try:
            response = self._http.request(method, path, headers={"Authorization": f"Bearer {self._token}"}, **kwargs)
        except httpx.TimeoutException as exc:
            raise ProviderFailed("timeout", type(exc).__name__, retryable=True) from exc
        except httpx.HTTPError as exc:
            raise ProviderFailed("provider_error", type(exc).__name__, retryable=True) from exc
        if response.status_code == 429:
            raise ProviderFailed("busy", "limite Apify atteinte", retryable=True)
        if response.status_code == 402:
            raise ProviderFailed("provider_error", "crédit Apify épuisé ou plafond atteint", retryable=False)
        if response.status_code >= 400:
            raise ProviderFailed(
                "provider_error", f"Apify HTTP {response.status_code}", retryable=response.status_code >= 500
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderFailed("provider_error", "réponse Apify illisible", retryable=True) from exc
        # Les objets Apify sont enveloppés dans {"data": …} ; les éléments d'un jeu de données non.
        return data["data"] if isinstance(data, dict) and "data" in data else data
