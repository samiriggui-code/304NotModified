"""API Recherche d'entreprises (DINUM, data.gouv.fr) : collecte directe, gratuite et sans clé.

Vérifié le 01/10/2026 sur https://recherche-entreprises.api.gouv.fr/docs/ et la fiche data.gouv.fr :
accès ouvert, 7 appels par seconde et par adresse IP au plus (l'administration peut baisser cette
limite), 25 résultats par page au plus. La fiche n'indique pas de licence : à confirmer avant de
revendre ces données (les données Sirene sont publiées sous Licence Ouverte).

Préférée à Apify pour la recherche d'entreprises françaises : source officielle, gratuite, stable.
Les dirigeants (personnes physiques : nom, date de naissance) ne sont jamais repris.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx

from . import ProviderFailed, RateLimiter

API_URL = "https://recherche-entreprises.api.gouv.fr/search"
PAGE_URL = "https://annuaire-entreprises.data.gouv.fr/entreprise/{siren}"
SOURCE_NAME = "API Recherche d'entreprises (DINUM, data.gouv.fr)"
PER_PAGE_MAX = 25


@dataclass
class Collection:
    """Résultat d'une collecte : éléments, provenance, et ce qui manque."""

    items: list[dict]
    source: dict  # name, url, params, collected_at (ISO)
    total_available: int | None = None
    truncated: bool = False  # collecte arrêtée avant la fin (page en échec)
    errors: list[str] = field(default_factory=list)
    cost_eur: float = 0.0
    calls: int = 0


class RechercheEntreprises:
    def __init__(self, http: httpx.Client | None = None, limiter: RateLimiter | None = None, timeout: float = 15.0):
        self._http = http or httpx.Client(
            timeout=timeout, headers={"User-Agent": "304NotModified (+https://304notfound.com)"}
        )
        # Marge sous la limite publiée (7/s) : d'autres services de la machine peuvent l'utiliser aussi.
        self._limiter = limiter or RateLimiter(per_second=5, max_concurrent=2, queue_timeout=10)

    def search(self, params: dict, max_results: int) -> Collection:
        collected_at = datetime.now(UTC).isoformat(timespec="seconds")
        items: dict[str, dict] = {}  # par SIREN : une entreprise n'apparaît qu'une fois
        total: int | None = None
        errors: list[str] = []
        truncated = False
        calls = 0
        page = 1
        while len(items) < max_results:
            query = {
                **params,
                "page": page,
                "per_page": min(PER_PAGE_MAX, max_results),
                "limite_matching_etablissements": 1,
            }
            try:
                data = self._get(query)
                calls += 1
            except ProviderFailed as exc:
                if not items:
                    raise
                # Pages suivantes en échec : on livre ce qui a été collecté, en le signalant.
                errors.append(f"page {page} : {exc.reason}")
                truncated = True
                break
            total = data.get("total_results") if isinstance(data.get("total_results"), int) else total
            results = data.get("results") or []
            for raw in results:
                company = normalize(raw)
                if company and company["siren"] not in items:
                    items[company["siren"]] = company
            if not results or page >= (data.get("total_pages") or page):
                break
            page += 1
        return Collection(
            items=list(items.values())[:max_results],
            source={"name": SOURCE_NAME, "url": API_URL, "params": params, "collected_at": collected_at},
            total_available=total,
            truncated=truncated,
            errors=errors,
            calls=calls,
        )

    def _get(self, query: dict) -> dict:
        with self._limiter.slot():
            try:
                response = self._http.get(API_URL, params=query)
            except httpx.TimeoutException as exc:
                raise ProviderFailed("timeout", type(exc).__name__, retryable=True) from exc
            except httpx.HTTPError as exc:
                raise ProviderFailed("provider_error", type(exc).__name__, retryable=True) from exc
        if response.status_code == 429:
            raise ProviderFailed("busy", "limite de l'API publique atteinte", retryable=True)
        if response.status_code >= 500:
            raise ProviderFailed("provider_error", f"HTTP {response.status_code}", retryable=True)
        if response.status_code != 200:
            # 400 : paramètre refusé par l'API (code NAF ou département invalide, par exemple).
            raise ProviderFailed("bad_request", f"HTTP {response.status_code}", retryable=False)
        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderFailed("provider_error", "réponse illisible", retryable=True) from exc
        if not isinstance(data, dict):
            raise ProviderFailed("provider_error", "réponse inattendue", retryable=True)
        return data


def normalize(raw: dict) -> dict | None:
    """Fiche entreprise réduite à ce qu'un agent peut exploiter, sans données personnelles."""
    if not isinstance(raw, dict) or not raw.get("siren"):
        return None
    siege = raw.get("siege") if isinstance(raw.get("siege"), dict) else {}
    # Diffusion partielle (« P ») : l'entreprise a demandé que son adresse ne soit pas diffusée.
    diffusible = raw.get("statut_diffusion") == "O"
    head_office = None
    if siege and diffusible:
        head_office = {
            "siret": siege.get("siret"),
            "address": siege.get("adresse"),
            "postal_code": siege.get("code_postal"),
            "city": siege.get("libelle_commune"),
            "departement": siege.get("departement"),
            "region": siege.get("region"),
        }
    # Établissement qui correspond aux filtres géographiques : le siège peut être ailleurs (essai réel du
    # 01/10/2026 : carton ondulé dans les Hauts-de-France → sièges à Saint-Mandé et à Pessac).
    matching = raw.get("matching_etablissements")
    match = matching[0] if isinstance(matching, list) and matching and isinstance(matching[0], dict) else None
    matching_establishment = None
    if match and diffusible:
        matching_establishment = {
            "siret": match.get("siret"),
            "address": match.get("adresse"),
            "postal_code": match.get("code_postal"),
            "city": match.get("libelle_commune"),
            "is_head_office": bool(match.get("est_siege")),
        }
    return {
        "siren": str(raw["siren"]),
        "name": raw.get("nom_complet") or raw.get("nom_raison_sociale"),
        "naf_code": raw.get("activite_principale"),
        # L'API renvoie aussi le code dans la nomenclature NAF 2025 (ex. 17.21A → 17.21Y).
        "naf2025_code": raw.get("activite_principale_naf25"),
        "category": raw.get("categorie_entreprise"),
        "employee_band": raw.get("tranche_effectif_salarie"),
        "employee_band_year": raw.get("annee_tranche_effectif_salarie"),
        "created_on": raw.get("date_creation"),
        "active": raw.get("etat_administratif") == "A",
        "open_establishments": raw.get("nombre_etablissements_ouverts"),
        "head_office": head_office,
        "matching_establishment": matching_establishment,
        "address_withheld": not diffusible,
        "source_url": PAGE_URL.format(siren=raw["siren"]),
    }
