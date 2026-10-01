# Être trouvé par les agents

Les agents ne parcourent pas le web au hasard : ils trouvent leurs outils dans des annuaires. Constat
du 1er octobre 2026 : aucun agent extérieur n'était venu, 304 n'étant inscrit nulle part.

| Canal | État | Comment |
|---|---|---|
| `robots.txt`, `sitemap.xml` | en place | servis par l'API (`app/public.py`) |
| Registre officiel MCP (registry.modelcontextprotocol.io) | publié | `server.json` + `mcp-publisher` (ci-dessous) |
| Annuaires qui lisent le registre officiel (PulseMCP, Glama…) | automatique, sous quelques jours | rien à faire |
| Listes et annuaires à inscription (awesome-mcp-servers, mcp.so, Smithery) | voir le tableau des demandes | une demande par annuaire |
| Annuaire x402 de Coinbase (agents qui paient) | après le paiement x402 | inscription quand un facilitateur encaisse |
| Fiche MCP `/.well-known/…` | **non** : format pas encore normalisé (groupe de travail « Server Card », août 2026) | à ajouter quand la spécification sera publiée |

## Registre officiel MCP

- Nom : `com.304notfound/304notmodified` (espace de noms du domaine, prouvé par fichier HTTP).
- Preuve : `https://304notfound.com/.well-known/mcp-registry-auth` (clé **publique** Ed25519,
  `deploy/mcp-registry-auth`).
- Clé **privée** : uniquement sur le PC du propriétaire,
  `C:\Users\samir\.config\304notmodified\mcp-registry-key.pem`. Jamais dans git. Si elle est perdue :
  en générer une nouvelle et remplacer `deploy/mcp-registry-auth` (procédure : documentation
  « Authentication » du dépôt `modelcontextprotocol/registry`).
- Publier une nouvelle version : augmenter `version` dans `server.json`, puis

```bash
mcp-publisher validate
mcp-publisher login http --domain 304notfound.com --private-key "$(openssl pkey -in <clé privée> -noout -text | grep -A3 priv: | tail -n +2 | tr -d ' :\n')"
mcp-publisher publish
```

(`mcp-publisher` : https://github.com/modelcontextprotocol/registry/releases, v1.8.1 au 01/10/2026.)
