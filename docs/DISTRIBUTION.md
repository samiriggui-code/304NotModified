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

## Suivi au 1er octobre 2026 (soir)

- Registre officiel : **version 0.4.0 publiée** (description : questions sourcées + recherche
  d'entreprises françaises avec devis et budget), marquée « latest ».
- Glama : fiche créée automatiquement depuis le registre,
  https://glama.ai/mcp/connectors/com.304notfound/304notmodified, état « Healthy », testée le
  01/10 à 20:29 UTC (c'est le passage OVH vu dans les journaux). Les nouveaux outils y figurent.
- Trafic des premières 24 h : ~230 connexions MCP de robots d'annuaires (initialisation et liste des
  outils), **aucun appel d'outil par un agent extérieur** ; toutes les questions enregistrées venaient
  du propriétaire ou des vérifications.

## Demande à envoyer : awesome-remote-mcp-servers

`punkpeye/awesome-mcp-servers` n'accepte que les serveurs dont le code est public sur GitHub ;
304 (dépôt privé, serveur hébergé) relève de **`punkpeye/awesome-remote-mcp-servers`**. Conditions
(lues le 01/10/2026) : adresse publique qui répond à `initialize`, utilisable par tous, fiche Glama
(badge obligatoire, vérifié par leur CI), **le compte qui ouvre la demande doit avoir mis une étoile au
dépôt**. Entrée à ajouter dans la section « Knowledge & Memory », en tête (ordre alphabétique, le
chiffre passe avant les lettres) :

```markdown
- [304NotModified](https://304notfound.com) `https://304notfound.com/mcp`
  [![304NotModified MCP connector](https://glama.ai/mcp/connectors/com.304notfound/304notmodified/badges/score.svg)](https://glama.ai/mcp/connectors/com.304notfound/304notmodified)
  🔓 - Sourced, dated answers on French/EU rules shared between agents, plus French company search with quotes and budgets.
```

🔓 : utilisable sans clé (quelques questions par jour), clé gratuite facultative.
Titre de la demande : `Add 304NotModified (sourced FR/EU answers + French company search)`.

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
