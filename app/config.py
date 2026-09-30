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
    # Facturation électronique (réglementation, technique, intégration, process) : les règles, les
    # spécifications et la liste des plateformes agréées bougent souvent pendant le déploiement.
    "facturation": 86400,
    # Formation professionnelle (Qualiopi, CPF, OPCO…) : nouveau référentiel au 1er novembre 2026.
    "formation": 86400,
    "impots": 86400,  # fiscalité des particuliers et des entreprises (barèmes, dates, démarches)
    "finances": 86400,  # banque, épargne, crédit, assurance (taux réglementés, règles, frais)
    "vie_quotidienne": 86400,  # démarches, aides, droits sociaux, logement, papiers
    "droit": 7 * 86400,  # droit en vigueur (codes, lois, jurisprudence de principe)
    "general": 86400,
}
DEFAULT_DOMAIN = "general"

# Nom lisible et description courte de chaque domaine (tableau de bord, documentation).
DOMAIN_LABELS = {
    "facturation": ("Facturation électronique", "Réglementation, formats, plateformes agréées, Peppol, e-reporting"),
    "formation": ("Formation professionnelle", "Qualiopi, CPF et EDOF, OPCO, RNCP"),
    "impots": ("Impôts", "Impôt sur le revenu, TVA, impôt sur les sociétés, dates et démarches"),
    "finances": ("Finances", "Banque, épargne, crédit, assurance, taux réglementés"),
    "vie_quotidienne": ("Vie quotidienne", "Démarches, aides, droits sociaux, logement, papiers"),
    "droit": ("Droit", "Droit en vigueur : codes, lois, jurisprudence de principe"),
    "reglementation": ("Réglementation", "Lois, normes et référentiels applicables aux entreprises"),
    "logiciel": ("Logiciel", "Versions, API, bibliothèques"),
    "entreprise": ("Entreprises", "Coordonnées, horaires, activité d'une entreprise"),
    "prix": ("Prix", "Prix, disponibilité, stocks"),
    "actualite": ("Actualité", "Événements récents"),
    "general": ("Général", "Questions hors spécialité"),
}

# Consignes de recherche propres à un domaine, ajoutées à la consigne générale du chercheur.
# Spécialités (voir docs/VISION.md, §12) : facturation électronique, formation professionnelle,
# impôts, finances, vie quotidienne, droit, réglementation, logiciel. Les clients sont des agents IA :
# plus le service couvre de sujets avec des sources officielles, plus il leur est utile.
DOMAIN_GUIDANCE = {
    "impots": (
        "Questions sur les impôts en France (particuliers et entreprises) : impôt sur le revenu, TVA,\n"
        "impôt sur les sociétés, taxe foncière, prélèvement à la source, crédits et réductions, dates.\n"
        "- Sources officielles d'abord : impots.gouv.fr, BOFiP, Légifrance (Code général des impôts, loi\n"
        "  de finances), economie.gouv.fr, service-public.fr.\n"
        "- Précise l'année d'imposition ou de revenus concernée, et vérifie la dernière loi de finances."
    ),
    "finances": (
        "Questions sur la banque, l'épargne, le crédit et l'assurance en France : taux réglementés\n"
        "(Livret A, LEP, PEL…), plafonds, règles des produits, frais, droits des clients.\n"
        "- Sources officielles d'abord : Banque de France, service-public.fr, economie.gouv.fr, AMF,\n"
        "  ACPR, Légifrance (Code monétaire et financier, Code des assurances).\n"
        "- Donne la date d'effet de chaque taux ou plafond et la prochaine date de révision si elle est connue.\n"
        "- Aucun conseil d'investissement : uniquement les règles et les chiffres officiels."
    ),
    "vie_quotidienne": (
        "Questions pratiques de la vie quotidienne en France : démarches administratives, papiers\n"
        "d'identité, aides et prestations sociales, logement, travail, famille, transport, santé.\n"
        "- Sources officielles d'abord : service-public.fr, les sites des administrations concernées\n"
        "  (CAF, Assurance maladie, France Travail, ANTS…), Légifrance.\n"
        "- Donne les conditions, montants et dates en vigueur, et le lien de la démarche officielle."
    ),
    "droit": (
        "Questions sur le droit français et européen en vigueur : codes, lois, décrets, règlements,\n"
        "grands principes de jurisprudence.\n"
        "- Sources officielles d'abord : Légifrance (version en vigueur des articles), EUR-Lex,\n"
        "  Conseil constitutionnel, Cour de cassation, Conseil d'État, service-public.fr.\n"
        "- Cite les articles précis et leur version en vigueur ; signale les modifications récentes ou à venir.\n"
        "- Information générale uniquement : ne donne pas de conseil juridique sur un cas particulier."
    ),
    "formation": (
        "Questions sur la formation professionnelle en France : certification Qualiopi (référentiel\n"
        "national qualité, guide de lecture, audits, indicateurs, preuves), CPF et EDOF, OPCO, France\n"
        "Compétences (RNCP, Répertoire spécifique), sous-traitance, obligations des organismes de formation.\n"
        "- Appuie-toi d'abord sur les sources officielles : Légifrance (Code du travail, décrets),\n"
        "  travail-emploi.gouv.fr (référentiel et guide de lecture Qualiopi), France Compétences,\n"
        "  Caisse des Dépôts et moncompteformation.gouv.fr (CPF, EDOF), COFRAC, Centre Inffo.\n"
        "  Un site d'organisme certificateur, de consultant ou d'éditeur peut aider, mais ne suffit pas seul.\n"
        "- Précise toujours la version du référentiel et du guide de lecture concernée, et sa date\n"
        "  d'application. Le décret n° 2026-728 du 1er août 2026 fixe un nouveau référentiel (33 indicateurs)\n"
        "  applicable aux audits à partir du 1er novembre 2026 : beaucoup de pages parlent encore de\n"
        "  l'ancien (32 indicateurs). Vérifie aussi si un nouveau guide de lecture a été publié.\n"
        "- Si les sources se contredisent, dis-le, indique laquelle fait foi et baisse la confiance.\n"
        "- Reste sur de l'information générale : pas de conseil personnalisé sur un cas particulier."
    ),
    "facturation": (
        "Questions sur la facturation électronique française, sous tous ses aspects :\n"
        "réglementation (qui est concerné, dates, obligations, mentions, sanctions), technique (formats\n"
        "Factur-X, UBL, CII, normes, versions), intégration (API des plateformes agréées, annuaire,\n"
        "Peppol, connexion d'un logiciel) et process (parcours d'une facture, statuts de cycle de vie,\n"
        "rejet, litige, avoir, e-reporting, archivage).\n"
        "- Appuie-toi d'abord sur les sources officielles : impots.gouv.fr (spécifications externes B2B,\n"
        "  liste officielle des plateformes agréées, FAQ), BOFiP, Légifrance, economie.gouv.fr, AIFE\n"
        "  (aife.economie.gouv.fr, Chorus Pro), normes AFNOR XP Z12-012 (formats et statuts), XP Z12-013\n"
        "  (API entre logiciels et plateformes) et XP Z12-014 (cas d'usage), FNFE-MPE (Factur-X, annexes,\n"
        "  swaggers), norme européenne EN 16931, OpenPeppol. Un blog d'éditeur, de plateforme ou de\n"
        "  cabinet peut aider à trouver le document, mais ne suffit pas seul : sinon, baisse la confiance.\n"
        "- Donne les dates exactes et qui est concerné pour les obligations ; le numéro de version et la\n"
        "  date de publication pour les documents techniques. Vérifie qu'aucun report, aucune\n"
        "  modification ni aucune version plus récente n'est sortie : beaucoup de pages sont dépassées.\n"
        "- Si les sources se contredisent (dates, versions, chiffres, noms), dis-le, indique laquelle\n"
        "  fait foi et baisse la confiance.\n"
        "- Sois technique et précis (champs, codes, flux, routes d'API, étapes) quand la question le demande.\n"
        "- Reste sur de l'information générale : pas de conseil juridique ou fiscal personnalisé."
    ),
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
# Accès administrateur. ADMIN_TOKEN : jeton fixe pour les scripts (facultatif).
# Tableau de bord : ADMIN_EMAIL + ADMIN_PASSWORD_HASH (python -m app.cli hash-password) ;
# SESSION_SECRET signe les jetons de session (le changer déconnecte tout le monde).
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "").strip().lower()
ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH", "")
SESSION_SECRET = os.environ.get("SESSION_SECRET", "")

# Quota gratuit par clé (requêtes). Les questions restées sans réponse ne sont pas décomptées.
FREE_QUOTA = int(os.environ.get("FREE_QUOTA", "1000"))

# Adresse publique du service (page d'accueil, llms.txt, messages aux agents).
PUBLIC_URL = os.environ.get("PUBLIC_URL", "https://304notfound.com").rstrip("/")

# Accès sans clé : quelques questions par jour et par adresse IP, pour qu'un agent essaie sans démarche.
# 0 = accès sans clé désactivé.
ANON_DAILY_LIMIT = int(os.environ.get("ANON_DAILY_LIMIT", "20"))
ANON_KEY = "anonymous"

# Clé gratuite en libre-service (POST /v1/keys) : quota de la clé, et garde-fous contre les abus.
SELF_SERVICE_QUOTA = int(os.environ.get("SELF_SERVICE_QUOTA", "200"))
SELF_SERVICE_PER_IP_PER_DAY = int(os.environ.get("SELF_SERVICE_PER_IP_PER_DAY", "3"))
SELF_SERVICE_MAX_PER_DAY = int(os.environ.get("SELF_SERVICE_MAX_PER_DAY", "300"))

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

# Moteur de secours par OpenRouter (utilisé quand ANTHROPIC_API_KEY est absente et OPENROUTER_API_KEY
# présente). Modèle et tarifs vérifiés sur openrouter.ai le 30/09/2026 : claude-sonnet-5.5,
# 2 $ / 10 $ par million de jetons, 0,01 $ par recherche web. Le coût réel est lu dans chaque réponse.
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-sonnet-5.5")
OPENROUTER_WEB_MAX_RESULTS = int(os.environ.get("OPENROUTER_WEB_MAX_RESULTS", "5"))

# Moteur : délai maximal d'une recherche chez le fournisseur (sans relance automatique), nombre de
# recherches payantes simultanées, et attente maximale d'une place avant de répondre « busy ».
# Le client MCP attend 120 s : attente + recherche doivent rester en dessous.
PROVIDER_TIMEOUT_SECONDS = float(os.environ.get("PROVIDER_TIMEOUT_SECONDS", "90"))
MAX_CONCURRENT_SEARCHES = int(os.environ.get("MAX_CONCURRENT_SEARCHES", "4"))
SEARCH_QUEUE_TIMEOUT_SECONDS = float(os.environ.get("SEARCH_QUEUE_TIMEOUT_SECONDS", "20"))
# Délai conseillé à l'agent avant de réessayer après une cause passagère (busy, timeout…).
RETRY_AFTER_SECONDS = int(os.environ.get("RETRY_AFTER_SECONDS", "30"))

# Idempotence : durée pendant laquelle une même clé Idempotency-Key renvoie la même réponse.
IDEMPOTENCY_TTL_SECONDS = int(os.environ.get("IDEMPOTENCY_TTL_SECONDS", str(24 * 3600)))

MAX_QUESTION_CHARS = 500

# Motifs qu'un agent peut donner quand une réponse ne l'a pas aidé (API /v1/feedback et outil MCP).
# off_topic : la réponse ne porte pas sur la question posée ; contradiction : l'agent dispose d'une
# source qui dit autre chose. Un motif est un signal à examiner, jamais une preuve : il ne modifie
# aucune réponse (idée de retour par résultat reprise de HiveMind, voir docs/ANALYSE_PARALLEL_GPTCACHE_HIVEMIND_X402.md).
FEEDBACK_ISSUES = ("wrong", "outdated", "incomplete", "bad_source", "off_topic", "contradiction", "other")

# Durée de conservation du journal des requêtes (questions, contextes, retours), en jours.
LOG_RETENTION_DAYS = int(os.environ.get("LOG_RETENTION_DAYS", "365"))
