# Parallel, GPTCache, HiveMind, x402 : ce qu'ils apportent à 304NotModified

> Analyse du 30 septembre 2026, complément de l'analyse de Context7. Toutes les informations ont été
> lues ce jour-là dans les sources officielles citées (dépôts GitHub, spécifications, pages de prix
> et conditions). Les estimations sont signalées comme telles.

## En bref

| Projet | Fonction | Verdict pour 304 |
|---|---|---|
| **Parallel** | Service payant de recherche web pour agents | **Pas de fournisseur pour la base commune** : ses conditions interdisent de mettre ses résultats en cache et de les partager. Utile comme **modèle de contrat de réponse** et comme **référence de qualité** ponctuelle. |
| **GPTCache** | Bibliothèque de cache sémantique pour LLM | **Ne pas l'intégrer.** Reprendre une **règle** : réutiliser seulement si chaque condition est vérifiée, et refuser en cas de doute. |
| **HiveMind** | Démonstration de mémoire partagée entre agents | **Ne pas reprendre le code** (démonstration, parties non raccordées). Reprendre des **modèles de données** : contributions en attente, validité dans le temps, retour par exécution. |
| **x402** | Protocole de paiement par HTTP (et MCP) | **La bonne piste pour les achats par agents.** Deux mécanismes à préparer dès maintenant, sans paiement : **idempotence** et **« rien n'est encaissé sans réponse »**. |

Ce que 304 fait déjà bien et qu'aucun des quatre ne remplace : cache par question normalisée,
fraîcheur par domaine, **aucune réponse gardée sans source**, versions de réponses conservées,
retours des agents notés à part, journal complet.

---

## 1. Parallel : la recherche vendue aux agents

Sources : https://docs.parallel.ai, https://parallel.ai/pricing, https://parallel.ai/blog/responses-api,
https://parallel.ai/customer-terms.

### Ce qu'il est

Une suite d'API commerciales : **Search** (extraits de pages avec citations), **Extract** (page en
markdown), **Task** (recherche en plusieurs étapes, synchrone ou asynchrone jusqu'à 2 h, résultat
texte ou JSON), **FindAll** et **Entity Search** (entités), **Monitor** (surveillance programmée
d'une question, de 1 h à 30 j), **Responses** (réponse synthétisée compatible OpenAI, trois niveaux
d'effort). Le moteur n'est **pas** open source ; seuls les SDK (`parallel-web`, Python et npm) et
un livre de recettes sont publics.

### Tarifs publiés (vérifiés le 30/09/2026)

| Service | Prix pour 1 000 requêtes |
|---|---|
| Search | 1 à 5 $ selon le mode |
| Task | de 5 $ (lite) à 2 400 $ (ultra8x) |
| Responses | 10 $ (low), 50 $ (medium), 250 $ (high) |
| Gratuit | 5 000 requêtes par mois |

### Le point bloquant : leurs conditions

`parallel.ai/customer-terms` (sans date affichée) :

- **§2(b)** : un résultat « shall not be copied, cached, stored, or made available to other End
  Customers or other third parties » ;
- **§2(c)** : interdiction d'utiliser les résultats pour « create databases, data brokerage, data
  selling/reselling businesses, or related products or services ».

C'est exactement le modèle de 304 (une réponse trouvée une fois, gardée, resservie à d'autres
agents). **Brancher Parallel derrière la base commune violerait ces conditions.** Un usage comme
« fournisseur de secours » ne serait possible qu'en relais non mis en cache, ce qui détruit
l'économie du service (on paie chaque requête, sans réutilisation). Un accord commercial
spécifique serait le seul moyen de lever ce point.

### Ce qui est utile quand même : leur contrat de réponse

Le plus intéressant est la structure `basis` de l'API Task : pour **chaque champ** de la réponse,
les `citations` (URL et `excerpts`, les passages exacts), un `reasoning` et une `confidence` à trois
niveaux (`high` : plusieurs sources faisant autorité et cohérentes ; `medium` ; `low` : sources
faibles ou contradictoires). Pistes pour 304, **à évaluer, pas à faire tout de suite** :

1. relier chaque source à la phrase qu'elle justifie (passage cité), pas seulement lister des URL ;
2. donner, en plus du nombre entre 0 et 1, un niveau lisible expliqué (« une seule source »,
   « sources contradictoires ») ;
3. plusieurs niveaux de service (rapide depuis la mémoire / recherche nouvelle / recherche
   approfondie), qui sont aussi des niveaux de prix.

### Comme référence de qualité

Les 5 000 requêtes gratuites permettent de passer les questions de `docs/QUESTIONS_TEST.md`
(28 questions) dans les deux services et de comparer réponse, sources, fraîcheur, latence et coût.
Les résultats de Parallel servent alors **uniquement à la comparaison** et ne doivent **jamais**
entrer dans la base de réponses (§2(b)). À faire seulement après les premières vraies recherches
de 304, et avec ton accord (création de compte).

---

## 2. GPTCache : réutiliser sans se tromper

Sources : https://github.com/zilliztech/GPTCache (licence MIT), PyPI `gptcache`, PR #701 et #702.

### État réel

- Dernière version publiée sur PyPI : **0.1.44, le 1er août 2024** (plus de deux ans). Le dépôt
  reste actif : des modifications ont été fusionnées le 22 septembre 2026, mais elles n'ont pas
  été publiées.
- Composants : calcul d'embeddings, stockage vectoriel (`manager`), évaluation de similarité
  (`similarity_evaluation` : correspondance exacte, distance, réordonnanceur SBERT, Cohere, ONNX,
  JEV…), adaptateurs pour les SDK des LLM, serveur.

### Le résultat qui compte : leur propre banc d'essai

La PR #702 (22/09/2026) mesure, sur 1 536 cas, si une réponse en cache peut être réutilisée pour
une nouvelle question :

- le **réordonnanceur fourni par défaut** (`cross-encoder/quora-distilroberta-base`, seuil 0,80)
  réutilise 880 fois, dont **508 réutilisations fausses : 42,2 % de précision** ;
- leur nouvelle évaluation **JEV** descend à 10 réutilisations fausses (97,3 % de précision), au
  prix de 4 points de rappel.

Autrement dit : **la ressemblance des mots ou du sens ne suffit pas**. C'est ta crainte, chiffrée.

### Ce qu'est JEV, et ce qu'on peut en reprendre

`gptcache/similarity_evaluation/jev.py` n'est pas un algorithme local : c'est un **appel au service
payant d'un tiers** (TypeSafe AI, `api.typesafe.ai`). Ce qui est reprenable, c'est la **règle** :

- cinq questions indépendantes : même tâche, même contexte, format compatible, fraîcheur, aucun
  contexte manquant ;
- **la note retenue est la plus basse** : toutes les conditions doivent passer ;
- **en cas d'erreur, la note est 0** : on ne réutilise pas.

### Adaptation à 304 (pour le jour où l'on ajoute un rapprochement de questions)

Les dimensions de 304 sont plus concrètes et **se vérifient sans LLM** pour la plupart :
domaine, territoire (France, UE, pays), date ou période demandée (« en 2025 », « au 1er novembre »),
profil ou condition explicite (micro-entreprise, particulier…), langue, fraîcheur des sources,
version des connaissances (référentiel Qualiopi, norme). Proposition :

1. **Aujourd'hui, ne rien changer au cache** : la correspondance exacte après normalisation est
   simple et ne se trompe pas. Le taux de répétition réel n'est pas encore mesuré (aucune vraie
   recherche faite).
2. Quand les mesures le justifient : chercher des **questions candidates** proches (recherche plein
   texte SQLite FTS5, déjà incluse dans Python, **aucune dépendance**), puis ne **réutiliser que
   leurs sources** pour une nouvelle recherche plus courte. On économise de la recherche sans
   jamais servir une réponse à une question différente.
3. Servir directement une réponse proche seulement après un **jeu de cas étiquetés** propre à 304
   (vrais doublons / fausses ressemblances), avec la règle « toutes les dimensions, sinon non ».

### Verdict

**Ne pas intégrer GPTCache** : la bibliothèque publiée date de 2024, son évaluation par défaut se
trompe une fois sur deux sur leur propre banc d'essai, et la version fiable dépend d'une API payante.
Le cache actuel de 304 est plus simple et correct.

---

## 3. HiveMind (AmirK-S) : partager des connaissances entre agents

Sources : https://github.com/AmirK-S/HiveMind (licence MIT, version 0.1.0 du 6 septembre 2026,
1 étoile). À ne pas confondre avec les autres projets du même nom.

### État réel, d'après son propre README

« A demonstration pinned to a date, not a product » : pas d'instance hébergée, pas d'utilisateurs,
pas de maintenance. Pile lourde : PostgreSQL + pgvector, Redis, modèles DeBERTa (injection),
Presidio + GLiNER (données personnelles), téléchargés au démarrage.

**Raccordé et fonctionnel** : 7 outils MCP (contribuer, chercher, lister, supprimer, publier, signaler
un résultat, gérer les rôles), recherche plein texte + vecteurs, isolation par organisation et par
agent (portée par le jeton, jamais par les arguments), détection d'injection, retrait de données
personnelles.

**Présent dans le code mais NON raccordé** (le README le dit) : la 3e étape de dédoublonnage (par LLM)
et la **résolution des contradictions** (l'index MinHash n'est jamais rempli) ; l'agrégation des
signaux de qualité et les webhooks (aucun worker lancé). Le retrait de données personnelles masque
aussi à tort des noms de produits (« Prometheus », « Grafana »).

### Modèles de données utiles pour 304

1. **Deux tables** : contributions **en attente** et connaissances **approuvées**. Une contribution
   d'agent n'entre jamais directement dans ce qui est servi : c'est déjà la règle de 304
   (« les agents n'écrivent jamais dans la base de réponses »), et c'est la bonne forme si un jour
   on ouvre les contributions.
2. **Empreinte du contenu** (`content_hash`) pour repérer les doublons exacts sans LLM.
3. **Validité dans le temps** (migration 006) : `valid_at`, `invalid_at`, `expired_at`, c'est-à-dire
   la période où le fait est vrai, distincte de la date où l'enregistrement expire. Très utile pour
   304 : « taux du Livret A **à partir du** 1er août », « référentiel Qualiopi **applicable au**
   1er novembre 2026 ». Aujourd'hui, 304 ne connaît que la date de recherche et la date d'expiration.
4. **Signal de résultat par exécution** (`report_outcome`, une fois par `run_id`) : « résolu » /
   « n'a pas aidé ». 304 a déjà un retour par requête ; il manque surtout des motifs plus fins
   (ci-dessous).
5. **Publication explicite** (`is_public`) : ce qu'une requête contient ne devient pas public par
   défaut. À garder en tête si 304 accueille un jour des connaissances privées de clients.

### Retours des agents : motifs à ajouter

Aujourd'hui : `wrong`, `outdated`, `incomplete`, `bad_source`, `other`. À ajouter :
**`off_topic`** (réponse hors sujet : erreur de rapprochement ou de domaine) et **`contradiction`**
(l'agent a une source qui dit autre chose). Chaque retour reste un **signal à examiner, jamais une
preuve** : il ne modifie aucune réponse publiée.

### Verdict

**Ne pas reprendre le code**, et **ne pas ouvrir les contributions publiques maintenant** : 304 produit
lui-même ses connaissances, ce qui garantit leur provenance. Reprendre les idées 1, 3 et les motifs
de retour.

---

## 4. x402 : faire payer les agents

Sources : https://github.com/x402-foundation/x402 (spécification v2, `specs/transports-v2/http.md`
et `mcp.md`, `specs/extensions/payment_identifier.md` et `extension-offer-and-receipt.md`),
PyPI `x402`, https://docs.cdp.coinbase.com/x402/seller/facilitator.

### Attention : le dépôt a déménagé

`github.com/coinbase/x402` (cité dans la mission) n'est plus la référence : c'est une copie, alignée
pour la dernière fois le 21 avril 2026 (« bump main to match foundation repo »). Le projet vit dans
**`x402-foundation/x402`**, avec des versions publiées jusqu'au 29 septembre 2026. SDK Python :
paquet **`x402` 2.25.0**, marqué « Alpha », extras `fastapi`, `evm`… Le dépôt est sous licence
**Apache-2.0**, alors que les métadonnées du paquet Python indiquent **MIT** : à clarifier avant
de reprendre du code.

### Le déroulement (v2, flux par défaut `authorization`)

1. L'agent appelle `/v1/answer` sans paiement → **402** avec l'en-tête `PAYMENT-REQUIRED`
   (JSON en base64 : `accepts` = schéma, réseau, montant, actif, destinataire, délai).
2. L'agent, dans les limites fixées par son opérateur, signe une autorisation et rejoue l'appel avec
   l'en-tête `PAYMENT-SIGNATURE`.
3. Le serveur fait **vérifier** l'autorisation par un « facilitateur » (`/verify`, lecture seule).
4. Le serveur **exécute** le service.
5. Le serveur fait **encaisser** (`/settle`) **seulement après**, puis répond avec `PAYMENT-RESPONSE`.

Sur MCP : même logique, résultat d'outil `isError: true` avec la demande de paiement, paiement dans
`_meta["x402/payment"]`, reçu dans `_meta["x402/payment-response"]`. Si l'encaissement échoue après
exécution, **le serveur ne doit pas livrer le contenu**.

### Réponses aux questions de la mission

| Question | Réponse d'après la spécification |
|---|---|
| Quand commence la recherche coûteuse ? | Après la vérification (étape 3) : l'autorisation est valide avant qu'on dépense. |
| Que facture-t-on sans réponse fiable ? | **Rien** : on n'appelle pas `/settle`. C'est déjà la règle de 304 (« les questions sans réponse ne sont pas décomptées »). Le coût de la recherche ratée reste à la charge de 304 et doit entrer dans le prix moyen. |
| Paiement réussi, livraison échouée ? | L'ordre « livrer après encaissement » protège l'agent de payer pour rien, pas l'inverse : si la réponse se perd après l'encaissement, l'agent doit pouvoir la **récupérer** sans repayer (voir idempotence). |
| Double facturation lors d'un retry ? | Extension **`payment-identifier`** : l'agent envoie un identifiant (16 à 128 caractères) et le réutilise en cas de nouvel essai. Même identifiant et même requête → **même réponse, pas de nouvel encaissement** ; même identifiant, requête différente → **409**. La protection de base (nonce EIP-3009 à usage unique) empêche aussi le rejeu d'une même signature. |
| Récupérer un résultat déjà payé ? | Rejouer la requête avec le même identifiant. 304 garde déjà chaque réponse servie (`answer_versions`, `request_id`). |
| Fournisseur de recherche en panne ? | Vérifié, non encaissé → rien n'est dû. Le code `settlement_pending` (transaction partie, confirmation inconnue) doit être **rapproché** avant tout nouvel essai. |
| Réseaux et facilitateurs ? | Facilitateur Coinbase (CDP) : Base, Polygon, Arbitrum, World, Solana, et leurs réseaux de test (Base Sepolia, Solana Devnet). D'autres facilitateurs existent (ex. xpay). Clé CDP requise. |
| Frais sur les petits paiements ? | CDP : vérification gratuite ; 1 000 encaissements par mois gratuits, puis **0,001 $** l'encaissement ; frais de réseau pris en charge par le facilitateur. À comparer à un prix envisagé de 0,005 € : les frais représentent environ 20 % au-delà de la franchise (**estimation**). Le schéma `batch-settlement` (regroupement) est à étudier pour cette raison. |

Ce que x402 ne fait pas : il ne juge pas la qualité de la réponse et n'arbitre pas les litiges.
L'extension **offer-and-receipt** (offre et reçu signés par le serveur) fournit une preuve de la
transaction utile en cas de litige ; sa forme n'est pas encore stable.

### Proposition d'intégration dans 304 (sans paiement réel)

Le moteur reste indépendant du paiement. Une couche fine devant `/v1/answer` :

1. **Dès maintenant, sans paiement** : prendre en charge une clé d'idempotence sur `/v1/answer`
   (en-tête `Idempotency-Key`, mêmes règles que `payment-identifier` : longueur 16 à 128, même
   requête → même réponse sans nouveau décompte, requête différente → 409, clé liée au compte).
   C'est utile tout de suite (quotas, crédits Stripe) et c'est le prérequis de x402.
2. **Plus tard, en environnement de test identifié** (Base Sepolia, facilitateur CDP en test) : module
   `app/payment.py` avec le SDK officiel `x402[fastapi]`, activé par une variable d'environnement,
   **désactivé par défaut**. Flux `authorization` : vérifier → répondre depuis la mémoire ou chercher
   → encaisser **seulement si la réponse est « answered »**.
3. **Avant toute mise en production** : avis d'un comptable (stablecoins, règlement MiCA, TVA :
   déjà signalé dans `VISION.md` §7), choix du prix d'après les coûts mesurés, et ton accord.

**Distribution** : la spécification prévoit un annuaire des services payants (« Bazaar »,
`/discovery/search`). Y figurer serait un canal pour être trouvé par des agents qui paient :
à regarder au moment de l'étape 2.

---

## 5. Comment les quatre se complètent dans le moteur de 304

Aucun nouveau service ni nouvelle dépendance n'est nécessaire aujourd'hui. Place de chaque idée
dans la chaîne existante :

| Étape du moteur | Existe | Idée retenue |
|---|---|---|
| Réception de la demande | oui | **Idempotence** (x402) |
| Qualification (domaine…) | indice de domaine | Plus tard : territoire, période, profil explicites |
| Connaissance compatible | clé exacte normalisée | Plus tard : candidats FTS5, règle « toutes les conditions » (GPTCache) |
| Contrôle de validité | expiration par domaine | Plus tard : période de validité du fait (HiveMind) |
| Recherche + vérification | Claude + recherche web, sources obligatoires | Citations reliées aux affirmations (Parallel `basis`) |
| Réponse et provenance | réponse, sources, dates, confiance | Niveau de confiance expliqué (Parallel) |
| Mesure du coût et du résultat | journal complet | Voir §6 |
| Conservation publique | versions gardées | Contributions d'agents : non pour l'instant |
| Facturation | quotas | x402 en test, puis production après validation |

## 6. Ce qu'il faut mesurer

| Mesure | Déjà disponible | À ajouter |
|---|---|---|
| Nombre de requêtes | oui | – |
| Réponses utiles | retours `useful` | motifs `off_topic`, `contradiction` |
| Taux d'abstention et causes | taux oui | **causes** (en cours dans l'autre session : `reason`) |
| Réutilisation exacte | taux de cache, taux de répétition | – |
| Réutilisation sémantique | – | seulement quand elle existera |
| Erreurs de réutilisation détectées | – | retours `off_topic`/`wrong` sur des réponses servies depuis la mémoire |
| Recherches externes évitées | = réponses servies depuis la mémoire | afficher aussi le coût évité (coût moyen d'une recherche × réponses depuis la mémoire, **estimation**) |
| Latence | moyenne par résultat | **médiane et 95e centile** |
| Coût par demande et par réponse utile | coût total | **coût par réponse** et **par réponse jugée utile** |
| Coût de rafraîchissement | – | séparer les recherches qui remplacent une réponse expirée |
| Retour des clients techniques | – | clés actives sur au moins deux jours différents |
| Revenu et marge | estimés | réels quand un paiement existera |

Un taux de cache élevé n'est un succès que si les retours ne signalent pas de réponses fausses ou
périmées. Du trafic gratuit ne prouve pas une demande payante.

## 7. Classement

**Utile immédiatement** (interne, sans dépendance, sans coût) :
1. Idempotence sur `/v1/answer` (prérequis x402 et crédits).
2. Motifs de retour `off_topic` et `contradiction`.
3. Médiane et 95e centile de latence ; coût par réponse et par réponse utile ; clients qui reviennent.

**Utile après validation** :
4. Couche x402 en réseau de test, désactivée par défaut (après avis comptable pour la production).
5. Période de validité des faits (`valid_from`), à côté de la date d'expiration.
6. Réutilisation des **sources** de questions proches (FTS5), mesurée sur un jeu étiqueté.

**Intéressant à étudier** :
7. Citations reliées aux affirmations et niveau de confiance expliqué (modèle `basis` de Parallel).
8. Offre et reçu signés (x402) pour les litiges ; annuaire Bazaar pour la distribution.
9. Comparaison ponctuelle avec Parallel sur les 28 questions de test (résultats jamais gardés).

**Inutile ou trop coûteux aujourd'hui** :
10. GPTCache comme dépendance ; JEV (API payante d'un tiers).
11. Le code de HiveMind (pile lourde, démonstration, parties non raccordées).
12. Parallel comme fournisseur de la base commune (interdit par ses conditions).
13. Contributions publiques des agents.

## 8. Licences et reprises

Aucun code n'a été copié. Seules des **idées et règles** ont été reprises, avec leur source :
règle « toutes les conditions, note la plus basse, refus en cas d'erreur » (GPTCache, MIT) ; modèle
contributions en attente / validité dans le temps / signal par exécution (HiveMind, MIT) ; règles
de l'extension `payment-identifier` (x402, Apache-2.0). Si du code x402 est repris un jour : lever
l'écart de licence (dépôt Apache-2.0, paquet Python déclaré MIT) et conserver les mentions `NOTICE`.

## 9. Prochaine étape la plus utile

**Faire les premières vraies recherches.** Tant qu'aucune question n'a été résolue pour de vrai
(aucune clé Anthropic utilisée, `HANDOFF.md` §5), le taux de répétition, le coût par réponse et la
qualité des sources restent inconnus, et aucune décision de cache sémantique ou de prix n'est
fondée. Concrètement : fixer une limite de dépense, passer les 28 questions de
`docs/QUESTIONS_TEST.md`, relire les réponses et les sources. En parallèle, sans dépense :
idempotence, motifs de retour et mesures du §6. Ils seront prêts quand le trafic arrivera.
