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
cp .env.example .env   # puis remplir ADMIN_TOKEN (et ANTHROPIC_API_KEY pour les vraies recherches)
```

Sans `ANTHROPIC_API_KEY`, le service tourne quand même : les questions sont enregistrées comme
« sans réponse », ce qui mesure la demande sans rien dépenser.

## Lancer

```bash
set -a; . ./.env; set +a
.venv/bin/uvicorn app.main:app --port 8304
```

## Utiliser

Créer une clé d'API (administrateur) :

```bash
curl -X POST localhost:8304/admin/keys \
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

### Tableau de bord

Ouvrir **`http://localhost:8304/admin`** dans un navigateur et entrer le jeton `ADMIN_TOKEN`.
On y voit en un coup d'œil : les chiffres clés (requêtes, taux de répétition, taux de cache,
revenu, coût et marge estimés), d'où viennent les réponses (cache, recherche, sans réponse), les
questions les plus répétées et celles restées sans réponse, les dernières requêtes, les réponses
en mémoire avec leurs sources, et les clés d'API (avec création d'une nouvelle clé).
La page se rafraîchit toute seule toutes les 30 secondes. Le texte venant du web y est toujours
affiché comme du texte brut, jamais interprété.

Les mêmes données en JSON : `/admin/stats`, `/admin/requests`, `/admin/answers`, `/admin/keys`.

Lire les statistiques : volume, taux de répétition, taux de cache, coût, revenu et marge estimés,
questions sans réponse.

```bash
curl localhost:8304/admin/stats -H "Authorization: Bearer $ADMIN_TOKEN"
```

Documentation pour les agents : `/llms.txt` et `/docs` (OpenAPI).

## Brancher un agent par MCP

Le serveur MCP (`mcp_server/`) donne aux agents un outil `ask` (question, domaine facultatif).
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
| `logiciel`, `entreprise`, `facturation`, `general` | 24 heures |
| `reglementation` | 7 jours |

Ces durées se règlent dans `app/config.py`.

**Premier domaine : `facturation`**, l'intégration technique de la facturation électronique
française (formats, normes AFNOR XP Z12-012/013/014, API des plateformes agréées, annuaire,
statuts, e-reporting, Peppol). Le chercheur s'appuie d'abord sur les documents officiels
(impots.gouv.fr, AIFE, AFNOR, FNFE-MPE, EN 16931, OpenPeppol), donne toujours la version et la date
du document de référence et signale les contradictions (`DOMAIN_GUIDANCE` dans `app/config.py`).
Des questions de référence pour tester le service : [`docs/QUESTIONS_TEST.md`](docs/QUESTIONS_TEST.md).

## Vérifier avant chaque commit

```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python -m pytest
```

## Structure

```
app/
  main.py        API (FastAPI) : réponses, clés, statistiques, llms.txt
  dashboard.html Tableau de bord (/admin)
  store.py       SQLite : cache, journal des requêtes, clés d'API
  resolver.py    Recherche fraîche via Claude + recherche web
  normalize.py   Normalisation des questions
  config.py      Réglages (durées, quotas, prix, tarifs)
mcp_server/
  server.py      Serveur MCP : outil `ask` qui relaie vers l'API
tests/           Tests automatisés
docs/VISION.md   Vision, marché, modèle économique, feuille de route
deploy/          Scripts d'installation et de mise à jour du VPS
docs/DEPLOIEMENT.md  Mise en ligne pas à pas
docs/CAS_REELS.md  Journal des cas réels : les problèmes que le service doit résoudre
```
