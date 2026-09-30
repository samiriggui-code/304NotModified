"""Réglages de la version d'essai. Tout est surchargeable par variable d'environnement."""

import os

# Durée de fraîcheur d'une réponse selon son domaine, en secondes.
# Une réponse expirée n'est plus servie : la question suivante relance une recherche.
DOMAIN_TTL_SECONDS = {
    "prix": 3600,  # prix, disponibilité, stocks
    "actualite": 3600,  # événements récents
    "logiciel": 86400,  # versions, API, bibliothèques
    "entreprise": 86400,  # coordonnées, horaires, activité d'une entreprise
    "reglementation": 7 * 86400,  # lois, normes, référentiels
    "general": 86400,
}
DEFAULT_DOMAIN = "general"

# Consignes de recherche propres à un domaine, ajoutées à la consigne générale du chercheur.
# Premier domaine choisi : « reglementation » (entreprises, France puis UE), en commençant par la
# facturation électronique (voir docs/VISION.md, §12).
DOMAIN_GUIDANCE = {
    "reglementation": (
        "Questions sur une obligation réglementaire, fiscale ou sociale des entreprises (France, Union européenne) :\n"
        "- Appuie-toi d'abord sur les sources officielles : Légifrance, EUR-Lex, Journal officiel,\n"
        "  impots.gouv.fr, BOFiP, economie.gouv.fr, entreprendre.service-public.fr, service-public.fr,\n"
        "  URSSAF, CNIL, sites de la Commission européenne. Un article de presse, d'éditeur de logiciel\n"
        "  ou de cabinet peut aider à trouver le texte, mais ne suffit pas seul : dans ce cas, baisse\n"
        "  nettement la confiance.\n"
        "- Donne les dates d'application exactes et précise qui est concerné (taille d'entreprise,\n"
        "  secteur, régime de TVA…).\n"
        "- Vérifie qu'aucun report ou modification récente n'a changé la règle (loi de finances,\n"
        "  ordonnance, omnibus européen…) et signale-le s'il y en a un. Un texte adopté mais pas encore\n"
        "  publié au Journal officiel doit être signalé comme tel.\n"
        "- Réponds en information générale : ne donne pas de conseil personnalisé sur un cas particulier."
    ),
    "logiciel": (
        "Questions sur un logiciel, une bibliothèque, une API ou un outil informatique :\n"
        "- Cherche d'abord les sources officielles du projet : documentation officielle, notes de version\n"
        "  (changelog, release notes), guides de migration, page du paquet sur le registre officiel\n"
        "  (PyPI, npm, crates.io…), dépôt officiel du projet. Un blog, un forum ou un tutoriel ne suffit\n"
        "  pas seul : s'il est ta seule source, baisse nettement la confiance.\n"
        "- Indique toujours le numéro de version concerné et, si tu la trouves, sa date de sortie.\n"
        "- Signale les changements incompatibles (fonction ou classe renommée, supprimée, paramètre\n"
        "  modifié) et la façon actuelle de faire.\n"
        "- Si la réponse dépend de la version, dis pour quelle version elle est valable."
    ),
}

DB_PATH = os.environ.get("NM304_DB", "304notmodified.sqlite3")
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")

# Quota gratuit par clé (requêtes). Les questions restées sans réponse ne sont pas décomptées.
FREE_QUOTA = int(os.environ.get("FREE_QUOTA", "1000"))

# Prix de vente théorique, utilisé uniquement pour estimer le revenu dans /v1/stats.
PRICE_PER_REQUEST_EUR = float(os.environ.get("PRICE_PER_REQUEST_EUR", "0.005"))

# Modèle et coûts servant à estimer le coût d'une recherche fraîche.
# Tarifs à vérifier sur la page de prix d'Anthropic avant tout calcul sérieux.
MODEL = os.environ.get("NM304_MODEL", "claude-opus-5-5")
EFFORT = os.environ.get("NM304_EFFORT", "medium")
INPUT_USD_PER_MTOK = float(os.environ.get("INPUT_USD_PER_MTOK", "4"))
OUTPUT_USD_PER_MTOK = float(os.environ.get("OUTPUT_USD_PER_MTOK", "20"))
WEB_SEARCH_USD_PER_1000 = float(os.environ.get("WEB_SEARCH_USD_PER_1000", "10"))
USD_TO_EUR = float(os.environ.get("USD_TO_EUR", "0.92"))

MAX_QUESTION_CHARS = 500
