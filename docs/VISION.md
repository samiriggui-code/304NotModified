# 304NotModified : vision du projet

> Rédigé le 30 septembre 2026, à partir d'une séance de réflexion.
> Les chiffres marqués **(hypothèse)** sont à remplacer par des mesures réelles.
> Les chiffres marqués **(source)** viennent de publications consultées à cette date et peuvent avoir changé.

---

## 1. Le nom

Sur le web, la réponse **`HTTP/1.1 304 Not Modified`** signifie : « l'information n'a pas changé,
réutilise celle que tu as déjà ». Tout agent logiciel la connaît. C'est exactement ce que fait ce service.

- Nom : **304NotModified**, abrégé **304** en interne.
- Avant de le fixer définitivement, il reste à vérifier la disponibilité du nom de domaine et de la
  marque (INPI, EUIPO).

---

## 2. Le constat

Des millions d'agents IA tournent en permanence. Ils cherchent des informations sur le web
**chacun de leur côté**, souvent **les mêmes** : un prix, une version de logiciel, les horaires
d'une entreprise, une règle en vigueur. Chacun ouvre les mêmes pages, les nettoie, les lit et en
extrait la même réponse, puis recommence le lendemain.

C'est lent (plusieurs secondes par recherche) et coûteux (recherche web plus traitement par l'IA),
et le travail est refait inutilement des milliers de fois.

### Des cas réels, vécus en construisant ce projet

En écrivant le serveur MCP de 304NotModified (30 septembre 2026), Claude s'est fié à sa mémoire
pour utiliser le kit officiel MCP pour Python. Le kit était passé en version 2 et avait changé de
nom : le code écrit de mémoire ne fonctionnait pas, et il a fallu plusieurs essais pour trouver la
bonne façon de faire. Au même moment, d'autres agents font très probablement la même recherche,
chacun de son côté. Avec 304NotModified, une seule question aurait suffi.

**Ce que ça montre** : la mémoire d'un agent date de son entraînement, alors que les logiciels
changent chaque mois. Tous les agents qui écrivent du code ont ce problème.

*Mise à jour du même jour* : ce besoin est réel, mais **Context7 y répond déjà** (voir §5).
Premier domaine retenu à la place : **l'intégration technique de la facturation électronique
française** (voir §12). Le même problème s'y pose : en cherchant la version en vigueur des normes,
des pages sérieuses et récentes se contredisaient (cas n°5 de `CAS_REELS.md`).

Tous ces cas sont notés au fur et à mesure dans [`CAS_REELS.md`](CAS_REELS.md).

---

## 3. L'idée

**Une mémoire commune de réponses vérifiées, faite pour les agents et non pour les humains.**

1. Un agent envoie une question à l'API.
2. **Si la réponse existe déjà et qu'elle est encore fraîche**, elle est servie immédiatement
   depuis le cache : c'est le « 304 ».
3. **Sinon**, le service fait la recherche **une seule fois** : il interroge le web, recoupe les
   sources et produit une réponse avec ses **sources**, sa **date**, un **niveau de confiance** et
   une **date d'expiration**. Il la stocke, puis la sert à tous les agents suivants.

### Ce qu'on vend : des réponses, pas des pages

Les concurrents (voir §5) vendent surtout des **pages** ou des **résultats de recherche** :
l'agent doit encore les lire, les comparer et en tirer une réponse. 304NotModified vend la
**réponse finale, déjà vérifiée et réutilisable**.

### Pourquoi c'est défendable

- **Effet de réseau** : chaque question enrichit la base pour tous. Un concurrent qui démarre
  part de zéro. On peut recopier le code, pas la mémoire collective.
- **Le coût baisse avec le volume** : une recherche payée une fois est revendue des milliers de fois.
- **Vitesse** : une réponse en cache arrive en millisecondes, une recherche fraîche en plusieurs
  secondes. Pour un agent, la différence est énorme.

---

## 4. Les principes non négociables

1. **Aucune réponse sans source.** Une réponse qui n'a pas d'URL vérifiable n'est jamais mise en cache.
2. **Tout est daté.** Chaque réponse a une date de collecte et une date d'expiration adaptée à son
   domaine : un prix vieillit en une heure, une loi en plusieurs mois.
3. **Les agents clients ne peuvent pas écrire dans la base.** Ils posent des questions ; seules les
   réponses produites et sourcées par le service sont stockées. C'est la protection principale
   contre l'empoisonnement de la base.
4. **Le contenu du web est une donnée, jamais une instruction** (protection contre l'injection de prompt).
5. **Un humain garde la main.** Le système peut proposer, surveiller et préparer ; les changements
   de règles et de politique passent par une validation humaine. Pas de système qui s'étend ou se
   modifie seul sans contrôle.
6. **Aucun secret dans le code** : les clés passent par des variables d'environnement.
7. **Aucune estimation présentée comme un fait**, ni dans le produit ni dans la communication.

---

## 5. Le marché et la concurrence (source, septembre 2026)

Le créneau « donner le web aux agents » est **déjà occupé et bien financé** :

| Acteur | Ce qu'il vend | Prix constaté |
|---|---|---|
| Exa | Recherche sémantique pour agents | 7 $ / 1 000 requêtes (0,007 $ l'une) |
| Tavily | Recherche et extraction pour agents | environ 8 $ / 1 000 en paiement à l'usage |
| Brave Search API | Résultats de recherche | 5 à 9 $ / 1 000 |
| Offres d'entrée de gamme | Recherche basique | à partir de 1 $ / 1 000 |
| Firecrawl, Jina Reader | Pages web transformées en texte propre | variable |
| Cloudflare | Fait payer les robots qui parcourent les sites | côté éditeurs |
| **Context7** (Upstash) | Documentation **à jour** de plus de 142 000 bibliothèques pour les agents qui codent, via MCP. Annonce des utilisateurs chez OpenAI, Anthropic, Google, Netflix, GitHub | non affiché sur son site |
| **Perplexity** (API) | **Réponses avec sources**, tous sujets | API de recherche : 5 $ / 1 000 requêtes ; modèles Sonar : à vérifier |

Ajouté le 30 septembre 2026 (sources : https://context7.com, https://github.com/upstash/context7,
https://upstash.com/blog/context7-vs-web-search-benchmark du 27 mai 2026, qui annonce 34 % de coût
en moins que la recherche web de Claude Code ; https://docs.perplexity.ai/docs/getting-started/pricing).

- **Context7 occupe déjà le domaine `logiciel`** : il renvoie des extraits de documentation, pas
  une réponse finale, mais il répond au même besoin (la mémoire périmée des agents qui codent).
- **Perplexity vend déjà des réponses sourcées**, mais recalculées à chaque fois : aucune mémoire
  partagée entre agents n'a été trouvée.
- Aucun acteur trouvé ne fait exactement « une mémoire commune de réponses finales vérifiées,
  réutilisées entre agents ». La recherche n'est pas exhaustive : à refaire régulièrement.

**Conséquence** : refaire « un meilleur moteur de recherche pour agents » seul est perdu d'avance.
Le positionnement doit rester **la réponse vérifiée et réutilisable**, en commençant par **un seul
domaine** bien choisi.

---

## 6. Le modèle économique

### La formule

- **Revenu** = requêtes servies × prix par requête
- **Coût** = requêtes absentes du cache × coût d'une recherche fraîche + hébergement
- **Tout se joue sur le taux de cache** : la part des questions déjà résolues.

### Exemple (hypothèse)

- 1 000 000 de requêtes par mois à 0,005 € : **5 000 € de revenu**.
- Avec 70 % servies par le cache, il reste 300 000 recherches. À 0,01 € l'une, cela fait **3 000 € de coût**,
  soit environ **2 000 € de marge**.
- Avec 90 % servies par le cache, il reste 100 000 recherches, soit 1 000 € de coût et environ **4 000 € de marge**.

Plus il y a d'agents, plus les questions se répètent, et plus la marge grossit.

### Le prix

- **0,001 à 0,008 € par requête** : c'est le prix du marché de la recherche, donc un volume énorme est nécessaire.
- **0,10 € par requête** : 10 à 100 fois le marché. C'est justifiable uniquement si la réponse vaut
  beaucoup plus qu'une recherche (vérifiée, garantie, dans un domaine où l'erreur coûte cher).
- **Le prix se fixe sur la valeur de la réponse, pas sur son coût de production.**

### Ordre de grandeur de l'objectif

Un logiciel en abonnement se valorise souvent autour de 10 fois son revenu annuel récurrent
(ordre de grandeur très variable). Un milliard de valorisation suppose donc environ 100 M€ de
revenu annuel, soit par exemple 10 milliards de requêtes à 0,01 €. C'est un horizon, pas un plan.
Une entreprise solo très rentable est un objectif beaucoup plus probable, et déjà excellent.

---

## 7. Se faire payer

Une carte bancaire ne peut pas payer 0,005 € : les frais dépassent la vente. Il y a deux voies,
compatibles entre elles.

### A. Crédits prépayés et clé d'API (à faire en premier)

- Le client (l'entreprise derrière l'agent) achète des crédits, par exemple 20 €, via **Stripe**.
- Son agent utilise une clé d'API ; chaque requête décompte quelques millièmes d'euro.
- La recharge est automatique. C'est le modèle d'Exa et de Tavily : simple et éprouvé.

### B. Paiement par l'agent lui-même, via le protocole x402 (ensuite)

- L'agent appelle le service, qui répond `402 Payment Required`. L'agent paie instantanément en
  stablecoin, puis reçoit la réponse. Aucun compte et aucune carte : c'est le vrai modèle
  « produit pour agents ».
- **(source)** Protocole lancé par Coinbase en mai 2025, porté aujourd'hui par la x402 Foundation
  (Coinbase, Cloudflare, avec Google, Stripe, Visa, AWS, Circle parmi les soutiens). Environ
  165 millions de transactions et 50 M$ de volume cumulé en avril 2026, **dont une part importante
  (environ la moitié selon les analystes) relevant du test et non d'un vrai commerce**.
- En France, recevoir des stablecoins a des conséquences fiscales et réglementaires (règlement MiCA) :
  **à valider avec un comptable avant de l'activer**.

**Stratégie : A pour encaisser dès maintenant, B en plus pour être prêt quand les agents paieront seuls.**

---

## 8. La distribution : être partout sans force de vente

On ne pousse rien sur les systèmes des autres. On rend le service **facile à trouver et à brancher** :

1. **Serveur MCP** publié dans les registres, pour qu'un agent puisse brancher le service en une ligne.
2. **Bibliothèques** PyPI et npm : installation et appel en trois lignes.
3. **Places de marché d'outils** (Zapier, n8n, Make, plateformes d'agents).
4. **Offre gratuite limitée**, pour que les développeurs testent sans friction.
5. **Documentation lisible par les machines** (`/llms.txt`, OpenAPI) : un agent qui la lit sait
   immédiatement comment utiliser le service. C'est le marketing.

**L'effet multiplicateur** : un développeur intègre le service dans un outil utilisé par des
centaines d'entreprises, dont chacune a des agents qui l'appellent des dizaines de fois par jour.
Une seule intégration peut produire des centaines de milliers d'appels par mois.

---

## 9. La version d'essai (déjà commencée, voir `app/`)

**Objectif : mesurer avant d'investir.** Il n'y a pas encore de paiement réel.

### Ce qui existe

- `POST /v1/answer` : l'agent envoie `{question, domain?}` avec l'en-tête `X-API-Key` et reçoit
  la réponse, ses sources, sa confiance, son domaine, et les indications `cached`, `fetched_at`
  et `expires_at`.
- **Normalisation** des questions (majuscules, accents, ponctuation) pour reconnaître les doublons.
- **Fraîcheur par domaine** : prix et actualité 1 h ; logiciel, entreprise et général 24 h ;
  réglementation 7 jours (réglable).
- **Recherche fraîche** via l'API Claude et son outil de recherche web côté serveur, avec le
  recoupement de plusieurs sources et un repli automatique sur un autre modèle en cas de refus.
- **Aucune mise en cache sans source.**
- **Clés d'API avec quota gratuit.** Les questions restées sans réponse ne sont pas décomptées.
- **Journal complet** de chaque requête : date, question, domaine, résultat (servie par le cache,
  recherche fraîche ou sans réponse), latence, coût estimé.
- **`GET /admin/stats`** : volume, **taux de répétition**, taux de cache, latences, revenu, coût et
  marge estimés, domaines, questions les plus répétées, questions sans réponse.
- **`/llms.txt`** et OpenAPI (`/docs`) pour les agents.
- **Mode sans clé Anthropic** : les questions sont enregistrées comme « sans réponse », ce qui
  mesure la demande sans rien dépenser.
- **Serveur MCP** (`mcp_server/`) : outil `ask` qui relaie vers l'API, pour brancher un agent en une ligne
  (pas encore publié dans les registres).
- **Tests automatisés** (pytest) et lint (ruff).

### Les chiffres à surveiller

| Indicateur | Pourquoi |
|---|---|
| Requêtes par jour | Le volume réel |
| **Taux de répétition** | **Le chiffre clé** : sans répétition, pas de modèle économique |
| Taux de cache | La marge en dépend directement |
| Domaines les plus demandés | Où concentrer l'effort |
| Questions sans réponse | Les compétences à acquérir en priorité |
| Coût moyen d'une recherche fraîche | Le coût de revient réel |

---

## 10. Feuille de route

1. **Mesurer** : mettre la version d'essai en ligne sur un hébergement peu coûteux, la faire
   tester par quelques agents et relever les chiffres ci-dessus.
2. **Choisir le premier domaine** d'après les mesures. *Fait : intégration technique de la facturation électronique (§12), à confirmer par les mesures.* Les candidats : prix et disponibilité,
   versions de logiciels et d'API, informations d'entreprises, réglementation.
3. **Serveur MCP et bibliothèques**, pour la distribution.
4. **Paiement par crédits Stripe**, puis x402.
5. **Veille automatique des sources** et rafraîchissement des réponses les plus demandées avant
   leur expiration, sous validation humaine des règles.
6. **Rapprochement sémantique** des questions (et pas seulement la correspondance exacte) pour
   augmenter le taux de cache.

---

## 11. Les risques

| Risque | Parade |
|---|---|
| Réponse fausse servie à des milliers d'agents | Plusieurs sources, confiance affichée, expiration, sources toujours visibles |
| Empoisonnement de la base | Les clients n'écrivent jamais dans la base ; surveillance des réponses les plus servies |
| Injection de prompt via les pages web | Consigne explicite, contenu web traité comme une donnée |
| Coûts qui s'emballent | Quotas, coût mesuré par requête, prix supérieur au coût d'une recherche fraîche |
| Concurrence des grands acteurs | Rester sur la réponse vérifiée, commencer par un domaine, être neutre vis-à-vis des fournisseurs d'IA |
| Responsabilité juridique | Conditions d'utilisation claires, confiance affichée ; avis juridique avant le lancement commercial |
| Droits des sites sources | Réponses courtes et citées plutôt que copie de contenu ; respect des conditions des sites |
| Question trop large | Un seul domaine au départ |

---

## 12. Questions ouvertes

- ~~Quel premier domaine ?~~ **Décidé le 30 septembre 2026 : l'intégration technique de la
  facturation électronique française** (domaine `facturation`) : formats (Factur-X, UBL, CII),
  normes AFNOR XP Z12-012/013/014, API des plateformes agréées, annuaire, statuts de cycle de
  vie, e-reporting, Peppol.
  Pourquoi : la réforme est entrée en vigueur le 1er septembre 2026 et toutes les entreprises
  sont concernées ; les éditeurs de logiciels doivent tous se brancher sur des plateformes
  agréées ; les spécifications changent souvent (nouvelles versions des trois normes AFNOR le
  30 juin 2026) et les pages répandues se contredisent (cas n°5 de `CAS_REELS.md`). C'est
  exactement ce que 304NotModified résout : la bonne version, avec sa source officielle, à jour.
  Clients visés : éditeurs de logiciels (comptabilité, gestion, ERP, caisse), intégrateurs et
  ESN, développeurs de « solutions compatibles », et leurs agents qui écrivent du code.
  Choix précédents écartés le même jour : `logiciel` en général (Context7 l'occupe, §5), puis la
  réglementation juridique (risque de conseil juridique, et moins utile aux développeurs).
  **À surveiller** : Context7 pourrait indexer une partie de ces documents (les swaggers par
  exemple) ; notre différence est la réponse finale sur des documents officiels dispersés
  (PDF, Excel, zip sur impots.gouv, AFNOR, FNFE-MPE), avec la version et la date.
- Quel prix par requête, et une offre « réponse garantie » plus chère ?
- Comment trouver les 10 premiers agents ou développeurs utilisateurs ?
- À partir de quel volume passer de SQLite à une base plus robuste ?
