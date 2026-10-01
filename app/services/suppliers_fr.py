"""Service fr-suppliers : entreprises françaises répondant à des critères, liste structurée et sourcée.

Parcours (seules les étapes utiles sont faites) :
1. collecte par l'API officielle Recherche d'entreprises (gratuite, sans clé) : filtres exacts
   (code NAF, département, catégorie, état administratif) appliqués par la source elle-même ;
2. dédoublonnage par SIREN et normalisation (sans données personnelles des dirigeants) ;
3. seulement si l'agent donne un critère en texte libre : pertinence de chaque entreprise par Jev,
   décision à trois issues (match, no_match, undetermined) ; sans clé Jev, le résultat le dit ;
4. validation du schéma de sortie par le moteur, puis livraison avec sources, date et manques.

Aucun LLM généraliste n'est appelé : les critères structurés suffisent à la source officielle, et un
classement oui/non ne justifie pas un modèle plus cher. Apify n'est pas appelé non plus : la source
officielle couvre la recherche ; un enrichissement (site web, description d'activité) viendra d'un
Actor choisi sur cas réels, quand on saura lequel vaut son coût.
"""

import re
import time
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .. import config
from ..providers import ProviderFailed, ProviderUnavailable
from ..providers.jev import JevClassifier, verdict
from ..providers.recherche_entreprises import SOURCE_NAME, RechercheEntreprises
from . import Outcome, RunContext, ServiceSpec

SERVICE_ID = "fr-suppliers"
VERSION = "1.0.0"
NAF = re.compile(r"^\d{2}\.\d{2}[A-Z]$")
DEPARTEMENT = re.compile(r"^(\d{2}|2A|2B|\d{3})$")
JEV_BATCH = 25  # entreprises par appel Jev (contexte borné, une question oui/non par entreprise)


class SuppliersIn(BaseModel):
    query: str | None = Field(
        default=None,
        min_length=2,
        max_length=200,
        description="Mots-clés cherchés dans la dénomination et l'adresse (ex. « emballage carton »).",
    )
    naf_codes: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="Codes NAF rév. 2 de l'activité principale (ex. 17.21A). Filtre exact.",
    )
    departements: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="Départements (ex. 60, 2A, 974). Filtre sur les établissements, pas seulement le siège.",
    )
    categories: list[Literal["PME", "ETI", "GE"]] = Field(default_factory=list, description="Catégories INSEE.")
    active_only: bool = Field(default=True, description="Seulement les entreprises en activité.")
    max_results: int = Field(default=20, ge=1, le=50)
    relevance_criterion: str | None = Field(
        default=None,
        min_length=5,
        max_length=300,
        description="Facultatif : critère en texte libre que chaque entreprise doit remplir (classé par Jev). "
        "Coûte un supplément ; sans clé Jev, le résultat est livré sans ce classement et n'est pas facturé.",
    )
    drop_no_match: bool = Field(
        default=False, description="Retirer les entreprises classées no_match (les « undetermined » restent)."
    )

    @field_validator("naf_codes")
    @classmethod
    def _naf(cls, codes: list[str]) -> list[str]:
        codes = sorted({c.strip().upper() for c in codes})
        bad = [c for c in codes if not NAF.match(c)]
        if bad:
            raise ValueError(f"code NAF invalide : {', '.join(bad)} (format 17.21A)")
        return codes

    @field_validator("departements")
    @classmethod
    def _dep(cls, deps: list[str]) -> list[str]:
        deps = sorted({d.strip().upper() for d in deps})
        bad = [d for d in deps if not DEPARTEMENT.match(d)]
        if bad:
            raise ValueError(f"département invalide : {', '.join(bad)}")
        return deps

    @field_validator("categories")
    @classmethod
    def _cat(cls, cats: list[str]) -> list[str]:
        return sorted(set(cats))

    @field_validator("query", "relevance_criterion")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return " ".join(value.split()) if value else value

    @model_validator(mode="after")
    def _needs_a_filter(self):
        if not self.query and not self.naf_codes:
            raise ValueError("donnez au moins query ou naf_codes")
        return self


class Relevance(BaseModel):
    verdict: Literal["match", "no_match", "undetermined", "not_evaluated"]
    probability: float | None = None


class HeadOffice(BaseModel):
    siret: str | None
    address: str | None
    postal_code: str | None
    city: str | None
    departement: str | None
    region: str | None


class MatchingEstablishment(BaseModel):
    siret: str | None
    address: str | None
    postal_code: str | None
    city: str | None
    is_head_office: bool


class Company(BaseModel):
    siren: str
    name: str | None
    naf_code: str | None
    naf2025_code: str | None
    category: str | None
    employee_band: str | None
    employee_band_year: str | None
    created_on: str | None
    active: bool
    open_establishments: int | None
    head_office: HeadOffice | None
    matching_establishment: MatchingEstablishment | None = None
    address_withheld: bool
    source_url: str
    relevance: Relevance


class RelevanceInfo(BaseModel):
    requested: bool
    evaluated: bool
    model: str | None = None
    accept_threshold: float | None = None
    reject_threshold: float | None = None
    calibrated: bool = False


class SuppliersOut(BaseModel):
    companies: list[Company]
    count: int
    total_available: int | None
    truncated: bool
    relevance: RelevanceInfo


def build(collector: RechercheEntreprises, jev: JevClassifier) -> ServiceSpec:
    def price(p: SuppliersIn) -> float:
        extra = config.SUPPLIERS_RELEVANCE_PRICE_EUR if p.relevance_criterion else 0.0
        return round(config.SUPPLIERS_PRICE_EUR + extra, 6)

    def capabilities() -> dict:
        return {
            "collection": {"provider": SOURCE_NAME, "available": True},
            "relevance": {"provider": f"TypeSafe Jev ({config.JEV_MODEL})", "available": jev.configured},
        }

    def execute(p: SuppliersIn, ctx: RunContext) -> Outcome:
        api_params: dict[str, str] = {}
        if p.query:
            api_params["q"] = p.query
        if p.naf_codes:
            api_params["activite_principale"] = ",".join(p.naf_codes)
        if p.departements:
            api_params["departement"] = ",".join(p.departements)
        if p.categories:
            api_params["categorie_entreprise"] = ",".join(p.categories)
        if p.active_only:
            api_params["etat_administratif"] = "A"

        started = time.monotonic()
        try:
            collection = collector.search(api_params, p.max_results)
        except ProviderFailed as exc:
            ctx.record("collect", SOURCE_NAME, "collect", exc.reason, started, exc.cost_eur)
            return Outcome("failed", reason=exc.reason, retryable=exc.retryable)
        ctx.record(
            "collect",
            SOURCE_NAME,
            "collect",
            "partial" if collection.truncated else "ok",
            started,
            collection.cost_eur,
            f"{collection.calls} appel(s), {len(collection.items)} entreprise(s)",
        )

        companies = [{**c, "relevance": {"verdict": "not_evaluated", "probability": None}} for c in collection.items]
        limits = [
            (
                "Le filtre par département porte sur les établissements : le siège peut être ailleurs ; "
                "matching_establishment donne l'établissement trouvé."
            ),
            "Source officielle mise à jour chaque jour ; la tranche d'effectif date de l'année indiquée.",
        ]
        missing = ["Coordonnées (téléphone, e-mail, site web) : absentes de la source officielle."]
        withheld = sum(c["address_withheld"] for c in companies)
        if withheld:
            missing.append(f"Adresse non diffusée à la demande de l'entreprise : {withheld} entreprise(s).")
        status = "completed"
        if collection.truncated:
            status = "partial"
            missing.append("Collecte interrompue avant la fin : " + "; ".join(collection.errors))

        info = {"requested": bool(p.relevance_criterion), "evaluated": False}
        if p.relevance_criterion and companies:
            started = time.monotonic()
            try:
                model = _classify(jev, p.relevance_criterion, companies, ctx)
                info.update(
                    evaluated=True,
                    model=model,
                    accept_threshold=config.JEV_ACCEPT_THRESHOLD,
                    reject_threshold=config.JEV_REJECT_THRESHOLD,
                )
                limits.append(
                    "Pertinence jugée sur le nom, le code NAF, la catégorie et la ville seulement (la source "
                    "officielle ne décrit pas l'activité). Seuils non calibrés : vérifiez les « match »."
                )
            except ProviderUnavailable:
                ctx.record("classify", "TypeSafe Jev", "classify", "unavailable", started)
                status = "partial"
                missing.append("Classement par pertinence indisponible (Jev non configuré) : non facturé.")
            except ProviderFailed as exc:
                ctx.record("classify", "TypeSafe Jev", "classify", exc.reason, started, exc.cost_eur)
                status = "partial"
                missing.append(f"Classement par pertinence en échec ({exc.reason}) : non facturé.")
            if p.drop_no_match:
                companies = [c for c in companies if c["relevance"]["verdict"] != "no_match"]

        result = {
            "companies": companies,
            "count": len(companies),
            "total_available": collection.total_available,
            "truncated": collection.truncated,
            "relevance": info,
        }
        if not collection.items:
            # Essai réel du 01/10/2026 : « traiteur evenementiel » → 0 résultat, car query ne cherche que dans
            # la dénomination et l'adresse. Une liste vide n'est pas facturée et l'agent sait quoi changer.
            missing.append(
                "Aucune entreprise trouvée : query ne cherche que dans la dénomination et l'adresse, pas dans "
                "l'activité. Pour une activité, donnez naf_codes. Non facturé."
            )
            return Outcome(status, result, [collection.source], limits, missing, billable=False)
        return Outcome(status, result, [collection.source], limits, missing)

    return ServiceSpec(
        id=SERVICE_ID,
        version=VERSION,
        title="Fournisseurs et entreprises françaises",
        description=(
            "Entreprises françaises répondant à vos critères (mots-clés, codes NAF, départements, catégorie), "
            "depuis la source officielle (API Recherche d'entreprises), en liste structurée avec SIREN, siège, "
            "activité, taille et lien vers la fiche officielle. Facultatif : classement de pertinence sur un "
            "critère en texte libre (match / no_match / undetermined)."
        ),
        input_model=SuppliersIn,
        output_model=SuppliersOut,
        typical_latency_seconds="1 à 3 ; 3 à 8 avec classement de pertinence",
        freshness="Données officielles mises à jour chaque jour ; un même résultat est resservi 24 h au plus.",
        cache_seconds=config.SUPPLIERS_CACHE_SECONDS,
        limits=(
            "50 entreprises au plus par appel.",
            "Aucune coordonnée (téléphone, e-mail, site) : la source officielle n'en donne pas.",
            "Aucune donnée personnelle des dirigeants n'est renvoyée.",
            "Information générale : vérifiez la fiche officielle avant tout engagement.",
        ),
        errors={
            "422": "Paramètres refusés (format NAF, département, aucun filtre).",
            "402": "Prix supérieur à max_price_eur, ou plafond de dépense journalier de la clé atteint.",
            "404 / 409 / 410": "Devis inconnu / déjà utilisé ou pour d'autres paramètres / expiré.",
            "status=failed": "Source indisponible (reason : timeout, busy, provider_error, bad_request) ; "
            "non facturé, retryable indique s'il faut réessayer.",
            "status=partial": "Livré avec un manque signalé dans missing ; non facturé.",
        },
        pricing=(
            f"Prix ferme donné par le devis : {config.SUPPLIERS_PRICE_EUR} € par appel, "
            f"+ {config.SUPPLIERS_RELEVANCE_PRICE_EUR} € avec relevance_criterion. Facturé seulement si "
            "status=completed (version d'essai : décompté du quota de la clé, aucun encaissement réel)."
        ),
        price=price,
        capabilities=capabilities,
        execute=execute,
    )


def _classify(jev: JevClassifier, criterion: str, companies: list[dict], ctx: RunContext) -> str:
    """Pertinence de chaque entreprise par lots. Les fiches sont des données : Jev ne renvoie que des
    probabilités, aucun texte collecté ne peut donc déclencher une action ou une dépense."""
    model = ""
    for start in range(0, len(companies), JEV_BATCH):
        batch = companies[start : start + JEV_BATCH]
        state = {
            "criterion": criterion,
            "companies": {
                f"c{i}": {
                    "name": c["name"],
                    "naf_code": c["naf_code"],
                    "category": c["category"],
                    "city": (c["head_office"] or {}).get("city"),
                }
                for i, c in enumerate(batch)
            },
        }
        questions = {
            f"c{i}": f"Does the French company `companies.c{i}` plausibly satisfy `criterion`?"
            for i in range(len(batch))
        }
        started = time.monotonic()
        values, cost, model = jev.nouls(state, questions)
        ctx.record("classify", f"TypeSafe Jev ({model})", "classify", "ok", started, cost, f"{len(batch)} question(s)")
        for i, company in enumerate(batch):
            probability = values.get(f"c{i}")
            company["relevance"] = {
                "verdict": verdict(probability),
                "probability": round(probability, 4) if probability is not None else None,
            }
    return model
