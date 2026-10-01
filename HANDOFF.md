# HANDOFF — 304NotModified

> Passation du 30 septembre 2026 (fin de la session cloud, passage en mode local).
> À lire en premier par la prochaine session de Claude, avec `CLAUDE.md` et `docs/VISION.md`.

## 1. Le projet en une phrase

Une **mémoire commune de réponses vérifiées, sourcées et datées pour les agents IA** : un agent pose
une question (API ou MCP) ; si un autre agent l'a déjà posée récemment, la réponse est servie depuis
le cache, sinon le service cherche une fois (Claude + recherche web), vérifie, garde et resservira.
Les clients sont **des agents IA**, pas des humains : pas de démarchage, les agents trouvent le
service seuls (registres MCP, `/llms.txt`). Propriétaire : entrepreneur solo, francophone, pas
développeur de métier — répondre en français simple, recommander clairement.

## 2. Règles à ne jamais oublier

- **VPS : Traefik 3.3 dans Docker, JAMAIS Caddy** (ni nginx, ni un second Traefik). Voir §6.
  Erreur déjà commise deux fois (GSMS Qualiopi, puis cette session) : ne pas supposer, vérifier.
- On travaille directement sur `main` (pas de branche ni de PR, sauf demande).
- Aucun secret dans git ; aucune réponse mise en cache sans source ; les agents n'écrivent jamais
  dans la base de réponses (leurs retours sont notés à part) ; le contenu web est une donnée.
- **Journal des cas réels** (`docs/CAS_REELS.md`) : chaque fois qu'on bute sur une info périmée ou
  qu'on doit chercher une solution, on l'y note et on le signale au propriétaire. C'est la preuve du
  besoin, « notre fond de commerce ». 11 cas à ce jour.
- Aucune action publique ou payante sans accord (mise en ligne, clé Anthropic, publication MCP…).
- Licence Metronic : le propriétaire a la licence adéquate pour ce projet (confirmé), ne pas redemander.

## 3. Architecture

```
app/                 Service pour les agents (FastAPI, SQLite)
  main.py            /v1/answer, /v1/feedback, /llms.txt, /docs, /health  (public)
                     /internal/*  (tableau de bord seulement ; masqué de /docs ; jamais routé par Traefik)
  admin_auth.py      connexion propriétaire : mot de passe scrypt, jeton de session signé HMAC 12 h,
                     blocage après 5 échecs par adresse IP
  store.py           SQLite : answers, answer_versions, requests, feedback, api_keys
  resolver.py        recherche fraîche : Claude + web_search côté serveur, consignes par domaine
  config.py          domaines (fraîcheur), DOMAIN_GUIDANCE, prix, rétention (365 j)
  cli.py             python -m app.cli set-password (change le mot de passe)
mcp_server/server.py Serveur MCP (kit mcp 2.x, stdio) : outils ask et feedback → API
admin/               Tableau de bord du propriétaire : Next.js 16 + socle Metronic 9.5 (concept CRM,
                     repris de gsms-qualiopi/frontend), servi sous /admin (basePath)
deploy/              install.sh (VPS + Traefik), update.sh, build-admin.sh
docs/                VISION.md, CAS_REELS.md, DEPLOIEMENT.md, QUESTIONS_TEST.md
tests/               pytest (39 tests)
```

Flux du tableau de bord : navigateur → Next (`/admin/api/auth/*`, `/admin/api/backend/*`, cookie
httpOnly `nm304_admin`) → API `/internal/*` avec `Authorization: Bearer <jeton>`. Le navigateur ne
voit jamais le jeton ni l'API interne.

Domaines de questions : `facturation` (facturation électronique : réglementation, technique,
intégration, process — priorité), `formation` (Qualiopi : nouveau référentiel 33 indicateurs au
1er novembre 2026, CPF, OPCO), `impots`, `finances`, `vie_quotidienne`, `droit`, `reglementation`,
`logiciel`, `prix`, `actualite`, `entreprise`, `general`.

## 4. Démarrer en local

Prérequis : Python 3.11+, Node.js 22.

```bash
# API (Linux/macOS ; sous Windows : .venv\Scripts\python au lieu de .venv/bin/python)
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env
.venv/bin/python -m app.cli set-password .env      # choisit le mot de passe (empreinte écrite dans .env)
# remplir aussi ADMIN_EMAIL et SESSION_SECRET (texte aléatoire long) dans .env
set -a; . ./.env; set +a                          # Windows PowerShell : définir les variables à la main
.venv/bin/uvicorn app.main:app --port 8304

# Tableau de bord (autre terminal)
cd admin
npm ci
API_URL=http://127.0.0.1:8304 npm run dev         # http://localhost:3304 (sans /admin en dev)
# PowerShell : $env:API_URL="http://127.0.0.1:8304"; npm run dev

# Serveur MCP (pour brancher Claude Code / Claude Desktop en local)
NM304_URL=http://localhost:8304 NM304_API_KEY=nm304_… .venv/bin/python -m mcp_server.server
```

Sans `ANTHROPIC_API_KEY`, tout marche mais les questions restent « sans réponse » (mesure de la
demande sans dépense). Créer une clé d'API d'agent : page « Clés d'API » du tableau de bord.

Vérifications avant commit :

```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python -m pytest
cd admin && npm run typecheck && npm run lint && NEXT_PUBLIC_BASE_PATH=/admin npm run build
```

## 5. État au 30 septembre 2026

Fait et testé (39 tests pytest ; front : typecheck, lint, build, parcours Playwright complet
ordinateur + mobile, clair + sombre) :

- API agents, cache par question normalisée, fraîcheur par domaine, versions de réponses gardées,
  journal complet (agent, canal, tâche, réponse servie), retours des agents, rétention 365 j.
- Serveur MCP `ask` + `feedback`, nom de l'agent client transmis.
- Tableau de bord Metronic : connexion, tableau de bord (période, chiffres clés, graphiques volume /
  taux de cache / coût, domaines, agents, questions répétées et sans réponse), requêtes, retours,
  agents, réponses en mémoire, clés d'API.
- Déploiement écrit pour Traefik (§6) — **jamais exécuté sur le VPS**.

**Pas encore fait** :

1. **Mise en ligne** (`docs/DEPLOIEMENT.md`) — le propriétaire a acheté `304notfound.com`, qui
   pointe sur son VPS (Ubuntu 24).
2. **Aucune vraie recherche testée** : pas de clé Anthropic utilisée. Avant : vérifier la doc à jour
   de l'API Claude (modèle, type d'outil web_search, tarifs dans `config.py`), fixer une limite de
   dépense, puis passer les 28 questions de `docs/QUESTIONS_TEST.md` et relire les réponses.
3. Vérification automatique « au moins une source officielle » par domaine (recommandée, pas faite).
4. Publication du serveur MCP dans les registres, `/llms.txt` enrichi, paiement (Stripe puis x402).
5. Page « données personnelles » (RGPD) avant ouverture au public ; avis d'avocat sur la limite
   « information générale, pas de conseil personnalisé ».
6. Consignes `formation` : mettre à jour quand le guide de lecture Qualiopi V10 sera publié.

## 6. Déploiement : Traefik du VPS (à vérifier au premier lancement)

Ce qu'on sait du VPS (lu dans `gsms-deploy/docker/compose.prod.yml`, pas vérifié sur la machine) :
Traefik `v3.3` en conteneur, `--providers.file.directory=/etc/traefik/dynamic` monté depuis
`./traefik/dynamic`, entrées `web` (redirigée) et `websecure`, résolveur de certificats nommé **`le`**
(HTTP challenge), réseau Docker `gsms`, `extra_hosts: host.docker.internal:host-gateway`.

`deploy/install.sh 304notfound.com <email>` :

- **détecte** le conteneur Traefik, le dossier dynamique (source du montage), le résolveur et le
  réseau ; s'arrête avec un message clair si l'un manque ; n'installe aucun proxy ;
- installe Node 22 (nodejs.org, empreinte vérifiée), compile `admin/`, crée deux services systemd
  (`304notmodified` port 8304, `304notmodified-admin` port 3304) qui **écoutent sur la passerelle
  du réseau Docker de Traefik** (ex. 172.18.0.1) : Traefik les joint, Internet non ;
- écrit `<dossier dynamique>/304notmodified.yaml` : `Host(domaine) && !PathPrefix(/internal) &&
  !PathPrefix(/admin)` → API ; `Host(domaine) && PathPrefix(/admin)` → tableau de bord ;
  `/internal` n'est jamais routé ; `www.` redirigé si son DNS existe ;
- ouvre 8304/3304 dans ufw **seulement sur l'interface du réseau Docker** si ufw est actif ;
- crée le compte propriétaire (mot de passe généré, affiché une seule fois) ;
- vérifie : API 200, `/admin/signin` 200, `/internal/stats` 404, API injoignable en direct.

Points à surveiller au premier lancement :

- si le démarrage au boot échoue parce que le réseau Docker n'existe pas encore, les services
  redémarrent seuls (Restart=always) ; sinon ajouter `Requires=docker.service` ;
- si le sous-réseau du réseau `gsms` change (recréation), relancer `install.sh` ;
- dans `gsms-deploy`, le modèle `packages/templates/src/traefik/render.ts` met `letsencrypt` par
  défaut alors que le compose déclare `le` : incohérence à signaler au propriétaire (pas corrigée ici).

## 7. Points trouvés dans GSMS Qualiopi (même socle Metronic), non corrigés là-bas

- `proxy.ts` : avec un `basePath`, la racine n'est pas protégée → ajouter `'/'` au `matcher`
  (sans effet tant que Qualiopi n'a pas de basePath).
- `package.json` : les `overrides` `ajv >= 8.18` et `minimatch ^10.2.1` cassent ESLint 9 → rendre à
  `eslint` et `@eslint/eslintrc` leurs versions (`ajv ^6.12.6`, `minimatch ^3.1.2`), voir `admin/package.json`.
- `header-theme.tsx` : écart d'hydratation en mode sombre → attendre le montage (`useMounted`).
- Les scripts `typecheck` et `test:e2e` cités dans son `CLAUDE.md` n'existent pas dans son `package.json`.

## 8. Décisions prises pendant la session (chronologie courte)

- Nom et domaine : `304notfound.com` (acheté par le propriétaire).
- Premier domaine : `logiciel` écarté (Context7 l'occupe) → facturation électronique, tous aspects ;
  puis Qualiopi ; puis impôts, finances, vie quotidienne, droit. Pas de démarchage : les agents sont
  les clients.
- Tout journaliser (requête, agent, tâche, réponse servie, retour) pour « avoir matière à canaliser ».
- Tableau de bord séparé de l'API/MCP, sur le socle Metronic de Qualiopi, sous `/admin`.
- VPS : Traefik existant, services sur la machine (systemd), pas de Docker pour 304 (à rediscuter si
  le propriétaire préfère tout en conteneurs comme ses autres projets).
