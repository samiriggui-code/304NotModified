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

## 3. Tarifs et règles d'achat d'un nom de domaine en `.ai`

- **Date** : 30 septembre 2026
- **Domaine** : `prix`
- **Question** : « Combien coûte un nom de domaine en `.ai` et quelles sont les conditions d'achat ? »
- **Ce qui s'est passé** : au moment de réserver le nom du projet, il a fallu chercher sur le web :
  la mémoire de Claude ne connaissait pas la hausse de prix de 2026. L'accès direct aux registres
  (RDAP) était bloqué depuis l'environnement, donc la disponibilité du nom n'a pas pu être vérifiée.
- **Source de la bonne réponse** : page de prix de Namecheap
  (https://www.namecheap.com/domains/registration/cctld/ai/) et article de Nominus
  (https://www.nominus.com/blog/ai-domains-for-tech-startups-and-ai-brands).
- **Réponse attendue de 304** : « Achat de 2 ans minimum. Chez Namecheap : 179,96 $ pour 2 ans,
  renouvellement 229,96 $ pour 2 ans. Hausse de 14 % du prix de gros par le registre au 5 mars
  2026. » Avec les sources et la date ; à rafraîchir souvent (domaine `prix`).

## 4. AI Act : report des obligations sur l'IA à haut risque

- **Date** : 30 septembre 2026
- **Domaine** : `reglementation`
- **Question** : « À partir de quand s'appliquent les obligations de l'AI Act pour les systèmes d'IA
  à haut risque ? »
- **Ce qui s'est passé** : la mémoire de Claude indiquait le **2 août 2026**, la date prévue à
  l'origine par le règlement. Vérification faite, l'« omnibus numérique » (proposé le 19 novembre
  2025) a reporté ces obligations au **2 décembre 2027** (annexe III) et au **2 août 2028**
  (annexe I). Un agent qui répond de mémoire donne donc une date fausse, sur un sujet où l'erreur
  peut coûter cher à une entreprise.
- **Source de la bonne réponse** : Commission européenne, AI Act Service Desk
  (https://ai-act-service-desk.ec.europa.eu/en/ai-act/timeline/timeline-implementation-eu-ai-act),
  analyses de Gibson Dunn et Winston Taylor. À vérifier au Journal officiel de l'UE : le nouveau
  calendrier ne s'applique qu'une fois l'omnibus publié.
- **Réponse attendue de 304** : « Haut risque : 2 décembre 2027 (annexe III) et 2 août 2028
  (annexe I), après le report voté dans l'omnibus numérique. Les obligations de transparence
  (article 50) s'appliquent depuis le 2 août 2026, avec un délai au 2 décembre 2026 pour le
  marquage des contenus des systèmes déjà sur le marché. » Avec les sources et la date.

## 5. Facturation électronique : versions des normes et chiffres contradictoires

- **Date** : 30 septembre 2026
- **Domaine** : `facturation`
- **Question** : « Quelle est la version en vigueur de la norme AFNOR XP Z12-013 (API entre les
  logiciels et les plateformes agréées), et combien y a-t-il de plateformes agréées ? »
- **Ce qui s'est passé** : en cherchant, trois pages sérieuses donnaient des informations
  différentes. Un guide publié le 17 juin 2026 présente la version du **26 février 2026** comme
  « en vigueur », alors que la FNFE-MPE annonce de **nouvelles versions des trois normes au
  30 juin 2026** (XP Z12-014 en 1.4.0). Pour le nombre de plateformes agréées : **136** (108
  définitives et 28 sous réserve, selon l'AIFE), **134** fin mai 2026 (même guide), **107** (page
  d'un éditeur). Un développeur ou un agent qui lit la mauvaise page code sur une version dépassée.
- **Source de la bonne réponse** : https://www.impots.gouv.fr/specifications-externes-b2b (versions
  applicables), https://fnfe-mpe.org/ressources/ (publication du 30 juin 2026),
  https://aife.economie.gouv.fr/nos-applications/facturation-electronique-b2b/ et la liste
  officielle https://www.impots.gouv.fr/je-consulte-la-liste-des-plateformes-agreees.
  Version exacte et nombre de plateformes à relire directement sur ces pages : pas encore fait.
- **Réponse attendue de 304** : la version applicable selon impots.gouv.fr, avec sa date, le
  lien vers les swaggers officiels, et le nombre de plateformes lu sur la liste officielle du jour,
  en signalant que des pages répandues citent des versions ou des chiffres dépassés.
