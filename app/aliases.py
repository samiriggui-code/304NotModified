"""Noms d'arguments que les agents emploient souvent à la place des noms officiels.

Acceptés en entrée (API HTTP et outil MCP « ask »), jamais affichés dans le schéma : le contrat
publié reste question / domain / context. Mécanisme repris de la fonction « aliasArgs » du serveur
MCP de Context7 (packages/mcp/src/index.ts, commit 83e972e8b0fa2fb9dde78c451358d4209a9c0236,
licence MIT, © Upstash, Inc.), réécrit avec les alias de pydantic : aucun code copié.
"""

from pydantic import AliasChoices

QUESTION_ALIASES = AliasChoices("question", "query", "q")
DOMAIN_ALIASES = AliasChoices("domain", "category", "topic")
CONTEXT_ALIASES = AliasChoices("context", "task")
