# 304NotModified

**Une mémoire commune de réponses vérifiées, sourcées et datées, pour les agents IA.**

Un agent pose une question. Si un autre agent a déjà obtenu la réponse récemment, elle est servie
immédiatement depuis le cache ; sinon, le service fait la recherche une seule fois, la vérifie et
la garde pour les suivants.

- Vision complète, marché, modèle économique, risques : [`docs/VISION.md`](docs/VISION.md)
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

Lire les statistiques : volume, taux de répétition, taux de cache, coût, revenu et marge estimés,
questions sans réponse.

```bash
curl localhost:8304/admin/stats -H "Authorization: Bearer $ADMIN_TOKEN"
```

Documentation pour les agents : `/llms.txt` et `/docs` (OpenAPI).

## Domaines et fraîcheur

| Domaine | Fraîcheur par défaut |
|---|---|
| `prix`, `actualite` | 1 heure |
| `logiciel`, `entreprise`, `general` | 24 heures |
| `reglementation` | 7 jours |

Ces durées se règlent dans `app/config.py`.

## Vérifier avant chaque commit

```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python -m pytest
```

## Structure

```
app/
  main.py        API (FastAPI) : réponses, clés, statistiques, llms.txt
  store.py       SQLite : cache, journal des requêtes, clés d'API
  resolver.py    Recherche fraîche via Claude + recherche web
  normalize.py   Normalisation des questions
  config.py      Réglages (durées, quotas, prix, tarifs)
tests/           Tests automatisés
docs/VISION.md   Vision, marché, modèle économique, feuille de route
```
