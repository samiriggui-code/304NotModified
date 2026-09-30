# Context7 : ce qui a été repris dans le moteur de 304NotModified

Analyse du dépôt public [upstash/context7](https://github.com/upstash/context7) au commit
`83e972e8b0fa2fb9dde78c451358d4209a9c0236` (29 septembre 2026), licence MIT © Upstash, Inc.

## Frontière public / privé (vérifiée)

Le dépôt public contient : le serveur MCP (`packages/mcp`), un SDK HTTP TypeScript (`packages/sdk`),
une CLI (`packages/cli`), des intégrations (`tools-ai-sdk`, `opencode`, `pi`). Le README le confirme :
l'API, le moteur d'extraction et le moteur de collecte sont privés. Le serveur MCP ne fait qu'appeler
`GET /v2/libs/search` et `GET /v2/context` sur leur API (`packages/mcp/src/lib/api.ts`) : aucune
recherche, aucun cache, aucune vérification de source, aucune déduplication n'est visible
publiquement. Rien de leur moteur ne peut donc être repris ; seuls des mécanismes de bordure le
peuvent.

## Tableau

| Élément (fichier Context7) | Décision | Raison |
|---|---|---|
| `aliasArgs` : alias d'arguments hallucinés (`mcp/src/index.ts`) | **Porté** (`app/aliases.py`) | Les agents envoient `query` au lieu de `question` : sans alias, l'appel échoue avant d'arriver au moteur. Réécrit avec `AliasChoices` de pydantic, sans code copié ; le schéma publié ne change pas. |
| Délai maximal explicite par appel amont (`API_TIMEOUT_MS`, `mcp/src/lib/api.ts`) | **Adapté** (`PROVIDER_TIMEOUT_SECONDS`, 90 s) | Notre client Anthropic attendait 600 s par défaut (SDK 1.9.0), bien au-delà des 120 s du client MCP. |
| Relances limitées aux GET, jamais les POST (`sdk/src/http/index.ts`, `retry.ts`) | **Adapté** (`max_retries=0` sur l'appel payant) | Le SDK Anthropic relançait seul jusqu'à 2 fois (408, 409, 429, 5xx, coupure) : une recherche payante pouvait être facturée trois fois. La relance est désormais décidée par l'agent, guidée par `retryable`. |
| Issue classée `success` / `not_found` / `error` (`recordToolCallOutcome`) | **Adapté** (`reason`, `retryable`, `retry_after`) | Une absence de réponse doit être expliquée : nos causes sont propres à notre moteur (source absente, confiance, fournisseur, délai…). |
| `trust proxy` : adresse client lue de droite à gauche, proxys privés seulement (`mcp/src/index.ts`) | **Porté** (`client_address` dans `app/main.py`) | Nous lisions la première adresse de `X-Forwarded-For`, falsifiable pour contourner la limite sans clé. |
| Garde d'erreur du corps JSON (`mcp-body-error-handler.ts`) | Écarté | FastAPI et le kit MCP Python renvoient déjà des erreurs propres (422 / JSON-RPC). |
| Serveur sans état, `keepAliveMs: 0` (`createMcpHandler`) | Déjà en place | Notre MCP distant est déjà sans état et en réponses JSON (`stateless_http=True`, `json_response=True`). |
| Arrêt propre (`process-shutdown.ts`) | Écarté | uvicorn et systemd gèrent l'arrêt ; rien à gagner. |
| Télémétrie OpenTelemetry, OAuth/Clerk, JWT, chiffrement d'en-têtes, CLI, `ctx7 setup` | Écarté | Propres à leur service commercial ; aucune dépendance, clé, marque ou télémétrie importée. |
| Notions de bibliothèque et de version | Écarté | Notre moteur répond à des questions factuelles multidomaines : pas de transposition. |

## Correctifs propres à 304 (rien à reprendre chez Context7)

- **Déduplication des recherches en cours** (`app/engine.py`) : même clé normalisée = une seule
  recherche ; les autres requêtes attendent puis relisent le cache. Deux questions seulement proches
  ne sont jamais fusionnées.
- **Limite de recherches payantes simultanées** avec attente bornée : au-delà, réponse immédiate
  `busy` et délai conseillé, plutôt qu'une file sans fin.
- **Idempotence** (`Idempotency-Key`) : une relance reçoit la même réponse sans nouvelle recherche ni
  nouveau décompte ; une cause passagère n'est pas figée ; même clé et autre demande = 422 ; demande
  identique en cours = 409.
- Le contexte de l'agent (`context`) n'est jamais envoyé au moteur de recherche : seule la question,
  publique, sert à produire une réponse mutualisée.

## Mesures (environnement contrôlé, fournisseur simulé : 0,3 s et 0,02 € fictifs par recherche)

| Scénario | Avant (14db132) | Après |
|---|---|---|
| 40 agents simultanés, même question (4 écritures) | 40 recherches, 0,80 € | 1 recherche, 0,02 € |
| 40 agents simultanés, 40 questions différentes | 40 recherches, 40 simultanées, 1,1 s | 40 recherches, 4 simultanées, 3,2 s |

Ce sont des mesures d'un scénario simulé, pas une estimation du trafic réel.

## Limites restantes

- La clé de cache ne distingue ni territoire, ni langue, ni période : deux questions identiques
  mot pour mot partagent la même réponse. Ajouter ces dimensions demande de les recevoir (champ
  facultatif) ou de les déduire, puis de les inclure dans la clé.
- La déduplication et la limite de concurrence vivent dans un seul processus : suffisant avec un seul
  service uvicorn, à revoir si l'API passe sur plusieurs processus ou machines.
- Les compteurs sans clé et d'inscription sont en mémoire (remis à zéro au redémarrage).
- Le MCP ne transmet pas d'`Idempotency-Key` : un outil MCP relancé par le client repasse par le cache
  (sans coût de recherche si la première tentative a abouti) mais est décompté à nouveau.
- Pas de rafraîchissement anticipé des réponses les plus demandées avant expiration.

## Décisions encore nécessaires pour la facturation aux agents

1. Unité facturée : réponse livrée (`billable: true`), avec ou sans distinction cache / recherche.
2. Prix, devise, et traitement des retours négatifs (remboursement, crédit ?).
3. Moyen de paiement : crédits prépayés sur clé d'API, puis paiement par l'agent (par exemple x402).
   Aucun protocole n'est choisi ici ; à décider séparément, après lecture de la documentation
   officielle à jour.
4. Séparation autorisation / livraison : l'idempotence et `billable` permettent déjà de ne débiter
   qu'une livraison effective ; il restera à stocker une autorisation préalable (montant maximal,
   durée) avant la recherche.
