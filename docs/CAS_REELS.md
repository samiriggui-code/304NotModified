# Journal des cas réels

> Chaque fois qu'un agent (Claude compris, en construisant ce projet) bute sur une information
> périmée ou doit chercher une solution, on le note ici. C'est la preuve concrète du besoin auquel
> répond 304NotModified, notre fond de commerce, et la liste des questions que le service doit
> savoir résoudre.
>
> Règle : noter des faits vérifiés (versions, messages d'erreur, sources), pas des impressions.

| Champ | Contenu |
|---|---|
| Date | Jour où le problème est arrivé |
| Domaine | `logiciel`, `prix`, `reglementation`… |
| Question | La question qu'on aurait posée à 304NotModified |
| Ce qui s'est passé | Ce que l'agent croyait, ce qui était vrai, ce que ça a coûté (essais, temps) |
| Source de la bonne réponse | Là où on l'a trouvée |
| Réponse attendue de 304 | Ce que le service aurait dû répondre |

---

## 1. Kit MCP pour Python : `FastMCP` renommé en version 2

- **Date** : 30 septembre 2026
- **Domaine** : `logiciel`
- **Question** : « Comment créer un serveur MCP avec la dernière version du kit Python `mcp` ? »
- **Ce qui s'est passé** : en écrivant le serveur MCP de 304NotModified, Claude comptait utiliser
  `from mcp.server.fastmcp import FastMCP`, comme dans sa mémoire. Le paquet installé était en
  version **2.2.0**, où l'import échoue avec le message : *« This is mcp 2.x, where FastMCP was
  renamed to MCPServer (from mcp.server.mcpserver import MCPServer) and other APIs changed »*.
  Il a fallu installer le paquet, lire l'erreur puis fouiller le code du kit pour retrouver la
  nouvelle façon de faire (outil, client de test, gestion des erreurs).
- **Source de la bonne réponse** : le message d'erreur du paquet et le guide de migration officiel
  (https://py.sdk.modelcontextprotocol.io/v2/migration/#fastmcp-renamed-to-mcpserver).
- **Réponse attendue de 304** : « Depuis la version 2 du kit `mcp`, `FastMCP` s'appelle
  `MCPServer` : `from mcp.server.mcpserver import MCPServer`. Pour rester sur l'ancien code,
  fixer `mcp<2`. » Avec la source et la date.

## 2. Kit MCP 2.x : sortie structurée refusée pour un retour `dict`

- **Date** : 30 septembre 2026
- **Domaine** : `logiciel`
- **Question** : « Dans le kit `mcp` 2.x, pourquoi mon outil qui renvoie un `dict` n'a pas de
  `structured_content` ? »
- **Ce qui s'est passé** : l'outil déclaré `-> dict` ne renvoyait que du texte
  (`structured_content` vide). Forcer `structured_output=True` a provoqué l'erreur
  *« return type <class 'dict'> is not serializable for structured output »*. La solution,
  trouvée au troisième essai : annoter le retour `-> dict[str, Any]`. Deux tests ratés avant d'y arriver.
- **Source de la bonne réponse** : essais sur le paquet `mcp` 2.2.0 (code de
  `mcp/server/mcpserver/utilities/func_metadata.py`).
- **Réponse attendue de 304** : « Annotez le type de retour avec des types précis
  (`dict[str, Any]` ou un modèle Pydantic) ; un `dict` nu n'est pas converti en sortie structurée. »
