"""Jev (TypeSafe AI) : décisions courtes et structurées sur du texte, avec probabilités.

Vérifié le 01/10/2026 sur https://docs.typesafe.ai (API reference, Models) :
- POST https://api.typesafe.ai/v1/systemone, en-tête Authorization: Bearer <clé> ;
- corps : state (texte ou JSON), model, questions (noul = oui/non, choice, score) ;
- réponse : answers par question, usage.input_tokens ; seul le texte d'entrée est facturé
  (jev-1.13.0 : 0,042 $ par million de jetons) ;
- erreurs 401, 422, 429 (limite), 529 (surcharge) ;
- l'anglais est la langue où Jev est le plus juste : nos fiches sont en français, à mesurer ;
- un alias (jev-latest) peut changer de modèle : on fixe la version, car les seuils en dépendent.

Les probabilités ne garantissent pas qu'une décision est juste : les seuils sont des réglages à
évaluer sur nos cas réels, et toute valeur entre les deux seuils donne « indéterminé ».
"""

import httpx

from .. import config
from . import ProviderFailed, ProviderUnavailable, RateLimiter

API_URL = "https://api.typesafe.ai/v1/systemone"


class JevClassifier:
    def __init__(self, api_key: str | None, http: httpx.Client | None = None, limiter: RateLimiter | None = None):
        self._api_key = api_key
        # Aucune relance automatique : chaque appel est facturé.
        self._http = http or httpx.Client(timeout=config.JEV_TIMEOUT_SECONDS)
        self._limiter = limiter or RateLimiter(per_second=10, max_concurrent=4, queue_timeout=10)

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def nouls(self, state, questions: dict[str, str]) -> tuple[dict[str, float], float, str]:
        """Pose des questions oui/non sur un même état. Renvoie (probabilités par question, coût en euros,
        version du modèle qui a répondu)."""
        if not self._api_key:
            raise ProviderUnavailable("TYPESAFE_API_KEY absente")
        body = {
            "state": state,
            "model": config.JEV_MODEL,
            "questions": {qid: {"type": "noul", "instructions": text} for qid, text in questions.items()},
        }
        with self._limiter.slot():
            try:
                response = self._http.post(API_URL, json=body, headers={"Authorization": f"Bearer {self._api_key}"})
            except httpx.TimeoutException as exc:
                raise ProviderFailed("timeout", type(exc).__name__, retryable=True) from exc
            except httpx.HTTPError as exc:
                raise ProviderFailed("provider_error", type(exc).__name__, retryable=True) from exc
        if response.status_code in (429, 529):
            raise ProviderFailed("busy", f"Jev HTTP {response.status_code}", retryable=True)
        if response.status_code != 200:
            raise ProviderFailed(
                "provider_error", f"Jev HTTP {response.status_code}", retryable=response.status_code >= 500
            )
        try:
            data = response.json()
            answers = data["answers"]
            tokens = int((data.get("usage") or {}).get("input_tokens") or 0)
        except (ValueError, KeyError, TypeError) as exc:
            raise ProviderFailed("provider_error", "réponse Jev illisible", retryable=True) from exc
        cost = tokens * config.JEV_USD_PER_MTOK / 1e6 * config.USD_TO_EUR
        values: dict[str, float] = {}
        for qid in questions:
            answer = answers.get(qid) if isinstance(answers, dict) else None
            try:
                values[qid] = min(max(float(answer["noul"]), 0.0), 1.0)
            except (TypeError, KeyError, ValueError):
                continue  # question sans réponse exploitable : elle restera « indéterminée »
        return values, cost, str(data.get("model") or config.JEV_MODEL)


def verdict(probability: float | None) -> str:
    """Décision à trois issues, seuils réglables : match, no_match ou undetermined."""
    if probability is None:
        return "undetermined"
    if probability >= config.JEV_ACCEPT_THRESHOLD:
        return "match"
    if probability <= config.JEV_REJECT_THRESHOLD:
        return "no_match"
    return "undetermined"
