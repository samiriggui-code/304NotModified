# Apify + Jev + Claude / autres LLM dans le moteur de 304

> Travail du 1er octobre 2026. Documentations lues ce jour-là : docs.apify.com (API v2),
> docs.typesafe.ai (API, Models, Legal), recherche-entreprises.api.gouv.fr/docs et la fiche data.gouv.fr.
> Les chiffres **mesurés** et les chiffres **estimés** sont séparés (§7).

## 1. Diagnostic de l'existant

| Brique | Existe | Où |
|---|---|---|
| Services exposés | Questions sourcées (`/v1/answer`), calculs sur les données de l'agent (`/v1/calc/*`), retours (`/v1/feedback`) | `app/main.py`, `app/calc/` |
| HTTP et MCP | API FastAPI ; serveur MCP (stdio et Streamable HTTP) qui **relaie** vers l'API, donc même logique | `mcp_server/` |
| Découverte | `/llms.txt`, `/docs` (OpenAPI), `/v1/domains`, `robots.txt`, `sitemap.xml`, fiche `server.json` du registre MCP | `app/public.py` |
| Identité et droits | Clé d'API (libre-service ou tableau de bord), accès sans clé limité par adresse IP, quota par clé | `app/main.py` |
| Orchestration | Une seule recherche par question à la fois, recherches simultanées bornées, délai maximal, aucune relance automatique, causes d'échec explicites | `app/engine.py` |
| Fournisseurs | Claude (recherche web côté serveur), OpenRouter en secours : **interface déjà interchangeable** (`Resolver`, `FallbackResolver`) | `app/resolver.py` |
| Facturation | Quota décompté seulement si une réponse est livrée ; idempotence (`Idempotency-Key`) ; aucun paiement réel | `app/main.py`, `app/store.py` |
| Journal et coûts | Chaque requête : agent, canal, coût réel, latence, cause ; statistiques et marge estimée | `app/store.py`, `/internal/stats` |

**Ce qui manquait** pour vendre d'autres services que des questions : un **catalogue** avec contrats
publiés, un **devis** ferme, un **budget** par appel et par jour, un **journal des coûts par étape**
(collecte, classement, LLM), et des fournisseurs de collecte et de classement.

## 2. Architecture retenue

```
agent ──HTTP──┐                         ┌── collecte : API directe (Recherche d'entreprises) | Apify
agent ──MCP───┴─> /v1/services/* ──> moteur ──┼── classement : règles en code | Jev (si critère libre)
                  (mêmes routes)        │      └── analyse : Claude / OpenRouter (pas utilisé par ce service)
                                         └── devis, budget, cache, une exécution par demande,
                                             contrôle du schéma, facturation, journal des coûts
```

Le moteur garde tout ce qui engage : droits, devis, budget, choix des fournisseurs, reprises,
contrôle de sortie, facturation. Les fournisseurs collectent ou classent : ils ne décident jamais d'une
dépense ni d'une permission. Jev ne renvoie que des probabilités : un texte collecté ne peut donc ni
donner d'ordre au moteur ni déclencher un achat.

Parcours d'un appel (`app/services/routes.py`) :

1. découverte : `GET /v1/services` (contrat complet : schémas d'entrée et de sortie, prix, délai,
   fraîcheur, limites, erreurs, étapes disponibles) ;
2. devis facultatif : `POST /v1/services/{id}/quote` → prix ferme, 10 min, **une seule utilisation**,
   lié aux paramètres ; il ne consomme rien (prix calculé par règle) ;
3. exécution : `POST /v1/services/{id}/run` : paramètres validés → prix → **budget** (`max_price_eur`,
   plafond de 5 € par clé sur 24 h) → résultat encore frais en mémoire, sinon exécution (une seule à la
   fois pour une même demande) → **contrôle du schéma de sortie** → facturation → journal.

Politique de facturation : facturé **seulement** si `status=completed` et si le résultat apporte
quelque chose. `partial` (manque signalé), `failed` et liste vide : gratuits, et le devis redevient
utilisable. `Idempotency-Key` (MCP : `request_key`) : une relance reçoit le même résultat sans double
facturation.

## 3. Ce qu'apporte chaque composant

| Composant | Rôle | Verdict après examen |
|---|---|---|
| **API directe** (Recherche d'entreprises) | Collecte d'entreprises françaises | **Retenue pour le premier service.** Officielle, gratuite, sans clé, filtres exacts (NAF, département, catégorie), 7 appels/s. Préférée à Apify comme le demande le cahier des charges. |
| **Apify** | Collecte web quand aucune API ne suffit | **Adaptateur prêt** (`app/providers/apify.py`) : plafonds `maxTotalChargeUsd` et `maxItems` à chaque exécution, coût réel lu dans `usageTotalUsd` (compté même si l'exécution échoue), délai borné, aucune relance automatique. **Aucun Actor branché** : le choix se fait sur cas réels (qualité, coût, conditions du site visé sur le droit de garder et resservir). Usage le plus utile repéré : enrichir les entreprises avec leur site web et une description d'activité (voir §8). |
| **Jev** (TypeSafe) | Décisions oui/non, choix, notes, avec probabilités | **Adaptateur prêt et branché** sur un seul cas : pertinence d'une entreprise pour un critère en texte libre. Trois issues : `match`, `no_match`, `undetermined`. **Seuils non calibrés** (0,75 / 0,25). Version fixée (`jev-1.13.0`). Tarif publié : 0,042 $ par million de jetons d'entrée. Anglais = langue où Jev est le plus juste, nos fiches sont en français : à mesurer. |
| **Claude / OpenRouter** | Synthèse, comparaison, cas complexes | **Déjà interchangeables** dans le moteur de questions. Non utilisés par `fr-suppliers` : des critères structurés et un classement oui/non ne justifient pas un modèle plus cher. À brancher pour un futur service d'analyse (comparer des fournisseurs, synthèse sourcée). |
| **Règles en code** | Décisions explicites | Validation des codes NAF et départements, filtres exacts, dédoublonnage par SIREN, retrait des données personnelles, budget, facturation. |

## 4. Premier service : `fr-suppliers` 1.0.0

« Identifie les entreprises françaises répondant à ces critères et renvoie une liste structurée avec
les sources. » Entrée : `query`, `naf_codes`, `departements`, `categories`, `active_only`,
`max_results` (50 au plus), `relevance_criterion` et `drop_no_match` facultatifs. Sortie par
entreprise : SIREN, nom, codes NAF (rév. 2 et 2025), catégorie, tranche d'effectif et son année, date de
création, siège, **établissement trouvé dans la zone**, lien vers la fiche officielle, pertinence.
Avec chaque résultat : `sources` (source, URL, paramètres, date de collecte), `limits`, `missing`.

Données personnelles : les dirigeants (nom, date de naissance) ne sont **jamais** repris ; les
adresses des entreprises en diffusion partielle non plus.

## 5. Modifications et validation

Fichiers nouveaux : `app/services/` (catalogue, orchestration, `fr-suppliers`), `app/providers/`
(Recherche d'entreprises, Jev, Apify, limiteur par fournisseur), `tests/test_services.py`.
Modifiés : `app/main.py` (branchement, `services` dans `/internal/stats`), `app/store.py` (tables
`quotes`, `service_runs`, `service_cache`), `app/config.py`, `app/public.py` (`llms.txt`, plan du site),
`mcp_server/server.py` (outils `list_services`, `quote_service`, `run_service`), `.env.example`.

Validation :

- **157 tests passent** (22 nouveaux), ruff propre. Les 2 échecs de `tests/test_cli.py` sont
  antérieurs et propres à Windows (déjà notés dans `HANDOFF.md`).
- Tests **avec fournisseurs simulés** (aucun appel réseau) : contrat publié, résultat sourcé sans
  données personnelles, mémoire, paramètres refusés avant tout appel, panne non facturée et à
  relancer, collecte interrompue = partiel non facturé, devis ferme / à usage unique / lié aux
  paramètres / expiré / rendu après échec, budget et plafond journalier avant toute dépense, pas de
  double facturation (`Idempotency-Key`), Jev absent / en surcharge / trois issues et coût réel,
  Apify (plafonds, coût réel même en échec), MCP par les mêmes routes.
- **Essai réel** (API officielle, 01/10/2026) : 8 appels, voir §7. Il a fait corriger deux défauts :
  l'établissement trouvé n'était pas montré (sièges hors zone), et une liste vide était facturée.

## 6. Accès manquants

| Accès | Pour quoi | Où le mettre |
|---|---|---|
| `TYPESAFE_API_KEY` | Classement par pertinence (sinon : résultat `partial`, non facturé, et le contrat l'annonce) | `.env` du VPS |
| `APIFY_TOKEN` + choix d'un Actor | Enrichissement web (site, description d'activité) | `.env` du VPS ; Actor à choisir ensemble |
| Avis sur la licence | La fiche data.gouv.fr de l'API n'indique pas de licence ; les données Sirene sont sous Licence Ouverte. À confirmer avant de **vendre** ces données | — |
| Wallet de test (adresse 0x…) | Couche x402 en réseau de test (déjà demandé dans `HANDOFF.md`) | — |

## 7. Coûts : mesurés et estimés

**Mesuré** (essai réel du 01/10/2026, 8 appels à l'API officielle depuis le poste local) :

| Mesure | Valeur |
|---|---|
| Coût de collecte | **0 €** (API publique gratuite) |
| Latence d'un appel complet (collecte + contrôle + journal) | 122 à 319 ms ; 20 à 25 entreprises par appel |
| Latence servie depuis la mémoire | 18 ms |
| Paramètres invalides refusés | 9 ms, aucun appel au fournisseur |
| Coût Jev, coût Apify, coût LLM | **non mesurés** (aucune clé) |

**Estimé** (pas mesuré, à vérifier dès la première clé) :

- Jev : un appel de 25 entreprises ≈ 2 000 à 4 000 jetons d'entrée → ≈ 0,0001 € (tarif publié
  0,042 $/Mtok). Le nombre réel de jetons sera lu dans `usage.input_tokens` et journalisé.
- Prix **provisoires** du service : 0,02 € l'appel, + 0,01 € avec classement. Marge brute presque
  totale tant que la collecte est gratuite ; les vrais postes seront les frais de paiement (x402 :
  0,001 $ par encaissement au-delà de 1 000 par mois chez CDP, d'après l'analyse du 30/09) et les
  appels sans facturation.

Suivi : `GET /internal/stats` → `services` : exécutions, réussite, coûts par poste (collecte,
classement, LLM, autres), revenu, marge, latence moyenne, part servie depuis la mémoire.

## 8. Fiabilité des décisions : comparaison à faire

À faire dès la clé Jev, sur un échantillon étiqueté de 100 à 200 couples (critère, entreprise) tirés
de vrais appels :

| Méthode | Ce qu'on mesure |
|---|---|
| Règles (codes NAF seuls) | justesse, faux positifs, faux négatifs, coût 0 |
| Jev (`jev-1.13.0`) | idem + coût par demande, latence, part « indéterminé » |
| Petit LLM (via OpenRouter) | idem |

Limite déjà connue : la source officielle ne décrit pas l'activité ; Jev ne juge que le nom, le code
NAF, la catégorie et la ville. **C'est là qu'Apify pourrait payer** : récupérer le site et une
description d'activité avant le classement. À n'ajouter que si la comparaison montre un gain.

## 9. Prochaines étapes vers les paiements autonomes

1. **x402 en réseau de test** sur `/v1/services/*/run` : la couche se place à deux endroits déjà
   prévus dans `routes.py`, la **vérification** de l'autorisation avant exécution (là où le budget est
   contrôlé) et l'**encaissement** seulement si `billed` est vrai. Le devis (`quote_id`, expiration,
   prix ferme) sert d'offre ; `Idempotency-Key` correspond à `payment-identifier` (codes à aligner :
   409 et 16 à 128 caractères).
2. **Reçu** : `run_id` + `quote_id` + prix + date existent déjà dans `service_runs` ; y joindre la
   preuve de transaction x402 (extension offer-and-receipt quand elle sera stable).
3. Échec **après** encaissement : l'agent rejoue avec la même clé et récupère le résultat sans repayer.
4. Avant toute mise en production : avis comptable et juridique (USDC, TVA, licence des données), prix
   fixés d'après les coûts mesurés, ton accord.
