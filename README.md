# 304NotModified

**Une mémoire commune de réponses vérifiées, sourcées et datées, pour les agents IA.**

Un agent pose une question. Si un autre agent a déjà obtenu la réponse récemment, elle est servie
immédiatement depuis le cache ; sinon, le service fait la recherche une seule fois, la vérifie et
la garde pour les suivants.

- Vision complète, marché, modèle économique, risques : [`docs/VISION.md`](docs/VISION.md)
- Mise en ligne sur le VPS : [`docs/DEPLOIEMENT.md`](docs/DEPLOIEMENT.md)
- Journal des cas réels : [`docs/CAS_REELS.md`](docs/CAS_REELS.md)
- Consignes pour Claude : [`CLAUDE.md`](CLAUDE.md)

> **Statut : version d'essai.** Elle sert à mesurer le volume, le taux de répétition des questions
> et les coûts. Il n'y a aucun paiement réel pour l'instant.

## Installer

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env   # puis remplir ADMIN_EMAIL, ADMIN_PASSWORD_HASH, SESSION_SECRET (et ANTHROPIC_API_KEY)
.venv/bin/python -m app.cli hash-password   # produit l'empreinte pour ADMIN_PASSWORD_HASH
```

Sans `ANTHROPIC_API_KEY`, le service tourne quand même : les questions sont enregistrées comme
« sans réponse », ce qui mesure la demande sans rien dépenser.

## Lancer

Deux applications séparées :

```bash
# 1. L'API et le MCP pour les agents (Python)
set -a; . ./.env; set +a
.venv/bin/uvicorn app.main:app --port 8304

# 2. Le tableau de bord du propriétaire (Next.js, socle Metronic), dans un autre terminal
cd admin && npm ci && API_URL=http://127.0.0.1:8304 npm run dev    # http://localhost:3304
```

En production, le tableau de bord est servi sous `/admin` (voir [`docs/DEPLOIEMENT.md`](docs/DEPLOIEMENT.md)).

## Utiliser

Créer une clé d'API : depuis le tableau de bord (page « Clés d'API »), ou en script avec le jeton
fixe facultatif `ADMIN_TOKEN` :

```bash
curl -X POST localhost:8304/internal/keys \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"label": "premier-testeur", "quota": 1000}'
```

Poser une question (côté agent) :

```bash
curl -X POST localhost:8304/v1/answer \
  -H "X-API-Key: nm304_..." -H "Content-Type: application/json" \
  -d '{"question": "Quelle est la dernière version stable de Python ?", "domain": "logiciel"}'
```

Réponse :

```json
{
  "status": "answered",
  "answer": "…",
  "domain": "logiciel",
  "confidence": 0.9,
  "sources": [{"url": "https://…", "title": "…"}],
  "cached": true,
  "fetched_at": 1790000000.0,
  "expires_at": 1790086400.0
}
```

### Tableau de bord (application séparée, `admin/`)

Réservé au propriétaire : connexion par e-mail et mot de passe, construit sur le socle Metronic
(mise en page CRM) repris de GSMS Qualiopi. Pages :

- **Tableau de bord** : filtre de période (24 h, 7, 30, 90 jours, tout), chiffres clés (requêtes,
  taux de répétition, taux de cache, marge, retours utiles), volume de requêtes par heure ou par
  jour (cache, recherche, sans réponse), taux de cache, coût des recherches, domaines et agents
  les plus actifs, questions répétées et sans réponse ;
- **Requêtes** : chaque question, son agent, son canal, et en détail la tâche de l'agent et la
  réponse exacte servie ;
- **Retours des agents**, **Agents**, **Réponses en mémoire** (avec sources), **Clés d'API**.

Le navigateur ne parle qu'au serveur du tableau de bord, qui garde la session dans un cookie
`httpOnly` et relaie vers les routes `/internal/*` de l'API. Ces routes ne sont pas exposées sur
Internet (Traefik ne les route pas) et n'apparaissent pas dans `/docs`. Le texte venant du web est affiché
comme du texte ; seuls les liens http(s) sont cliquables.

Données en JSON (avec `Authorization: Bearer <jeton>`) : `/internal/stats?days=N`,
`/internal/timeseries?days=N&bucket=hour|day`, `/internal/requests`, `/internal/answers`,
`/internal/feedback`, `/internal/keys`.

Champs facultatifs : `context` (la tâche en cours de l'agent) et l'en-tête `X-Client` (nom de
l'agent). Chaque réponse porte un `request_id`, que l'agent renvoie pour dire si elle l'a aidé :

```bash
curl -X POST localhost:8304/v1/feedback \
  -H "X-API-Key: nm304_..." -H "Content-Type: application/json" \
  -d '{"request_id": "req_...", "useful": false, "issue": "outdated", "comment": "date dépassée"}'
```

Tout est enregistré (question, contexte, agent, réponse exacte servie, retour) pour savoir quoi
améliorer. Un retour est noté à part : il ne modifie jamais une réponse. Le journal est effacé
après `LOG_RETENTION_DAYS` jours (365 par défaut).

Documentation pour les agents : `/llms.txt` et `/docs` (OpenAPI).

## Brancher un agent par MCP

Le serveur MCP (`mcp_server/`) donne aux agents deux outils : `ask` (question, domaine et
contexte facultatifs) et `feedback` (dire si la réponse a servi). Il transmet le nom de l'agent.
Il ne fait que relayer vers `POST /v1/answer` avec la clé de l'agent : aucun accès direct à la base.

Configuration type d'un client MCP (Claude Desktop, Claude Code, etc.) :

```json
{
  "mcpServers": {
    "304notmodified": {
      "command": "/chemin/vers/304NotModified/.venv/bin/python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/chemin/vers/304NotModified",
      "env": {"NM304_URL": "http://localhost:8304", "NM304_API_KEY": "nm304_..."}
    }
  }
}
```

Avec Claude Code : `claude mcp add 304notmodified -e NM304_URL=http://localhost:8304
-e NM304_API_KEY=nm304_... -- .venv/bin/python -m mcp_server.server` (depuis le dossier du projet).

## Domaines et fraîcheur

| Domaine | Fraîcheur par défaut |
|---|---|
| `prix`, `actualite` | 1 heure |
| `logiciel`, `entreprise`, `facturation`, `formation`, `impots`, `finances`, `vie_quotidienne`, `general` | 24 heures |
| `reglementation`, `droit` | 7 jours |

Ces durées se règlent dans `app/config.py`.

**Premier domaine : `facturation`**, la facturation électronique française sous tous ses
aspects : réglementation (qui, quand, obligations), technique (formats, normes AFNOR, versions),
intégration (API des plateformes agréées, annuaire, Peppol) et process (statuts, rejets, avoirs,
e-reporting, archivage). Le chercheur s'appuie d'abord sur les sources officielles (impots.gouv.fr,
BOFiP, Légifrance, AIFE, AFNOR, FNFE-MPE, EN 16931, OpenPeppol), donne toujours les dates et
versions, signale les contradictions et reste sur de l'information générale
(`DOMAIN_GUIDANCE` dans `app/config.py`).

**Deuxième domaine : `formation`**, la formation professionnelle : Qualiopi (nouveau référentiel
au 1er novembre 2026), CPF et EDOF, OPCO, RNCP et Répertoire spécifique, avec les mêmes règles.

**Aussi : `impots`, `finances`, `vie_quotidienne`, `droit`**, chacun avec ses sources officielles
(impots.gouv.fr, Banque de France, service-public.fr, Légifrance…). Les clients sont des agents IA :
le service couvre large, toujours sur sources officielles et en information générale.

Des questions de référence pour tester le service : [`docs/QUESTIONS_TEST.md`](docs/QUESTIONS_TEST.md).

## Vérifier avant chaque commit

```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python -m pytest
cd admin && npm run typecheck && npm run lint && NEXT_PUBLIC_BASE_PATH=/admin npm run build
```

## Structure

```
app/
  main.py        API (FastAPI) : routes des agents (/v1) et routes internes (/internal)
  admin_auth.py  Connexion du propriétaire : mot de passe (scrypt), sessions signées
  cli.py         python -m app.cli hash-password
  store.py       SQLite : cache, journal des requêtes, clés d'API
  resolver.py    Recherche fraîche via Claude + recherche web
  normalize.py   Normalisation des questions
  config.py      Réglages (durées, quotas, prix, tarifs)
mcp_server/
  server.py      Serveur MCP : outils `ask` et `feedback` qui relaient vers l'API
admin/           Tableau de bord du propriétaire (Next.js, socle Metronic), servi sous /admin
tests/           Tests automatisés
docs/VISION.md   Vision, marché, modèle économique, feuille de route
deploy/          Scripts d'installation et de mise à jour du VPS
docs/DEPLOIEMENT.md  Mise en ligne pas à pas
docs/CAS_REELS.md  Journal des cas réels : les problèmes que le service doit résoudre
```
