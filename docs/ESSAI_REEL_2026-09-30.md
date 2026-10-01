# Premier essai réel : les 28 questions de test (30 septembre 2026)

> Les 28 questions de `docs/QUESTIONS_TEST.md` posées à l'API de production sur le VPS, par le vrai
> moteur (cache, journal, mesures), avec un plafond de dépense de 5 € vérifié après chaque question.
> Moteur : **OpenRouter**, modèle `anthropic/claude-sonnet-5.5` avec le plugin web (la clé Anthropic
> du PC n'avait plus de crédit ; sur le VPS, seule la clé OpenRouter est active).
> Coûts : coût réel renvoyé par OpenRouter (`usage.cost`), converti en euros (taux de `config.py`).

## Résultat global

| Mesure | Valeur |
|---|---|
| Questions | 28 |
| Avec réponse sourcée | **28** (aucune abstention) |
| Coût total | **3,14 €** |
| Coût moyen par réponse | 0,112 € (de 0,059 à 0,190 €) |
| Durée moyenne | 17,4 s (de 10,9 à 26,6 s) |
| Réponses avec au moins une source officielle | **19 sur 28** |

Le prix de vente théorique de `config.py` est de 0,005 € par requête : une recherche fraîche coûte
donc environ **22 fois** ce prix. Le modèle économique ne tient que si une réponse est resservie
plusieurs dizaines de fois depuis la mémoire, ce qui confirme que le **taux de répétition** reste le
chiffre clé. Ce calcul est une **estimation** sur un seul essai.

## Les pièges connus

| Question | Piège | Résultat |
|---|---|---|
| 8. Version des normes XP Z12-012/013/014 | des pages citent la version de février 2026 | **Juste** : éditions du 30 juin 2026, celles de février signalées comme annulées |
| 14. Nombre de plateformes agréées | les chiffres varient | **Bien traité** : évolution datée (101 → environ 150 → 164) et liste officielle sur impots.gouv.fr ; confiance 0,6 |
| 21. Indicateurs Qualiopi en décembre 2026 | beaucoup de pages disent 32 | **Juste** : 33 (décret n° 2026-728) ; mais **aucune source officielle** (6 sites de consultants) avec une confiance de 0,88 |
| 24. Dernière version du guide de lecture | la V10 n'existe peut-être pas encore | **Prudent** : V9 du 8 janvier 2024, V10 non publiée, invite à vérifier |

Ces réponses n'ont pas encore été relues une par une par un humain (`QUESTIONS_TEST.md` le demande
avant de démarcher des clients).

## Défaut trouvé et corrigé : les réponses sans source officielle

9 réponses sur 28 ne citaient **aucune source officielle** (Légifrance, impots.gouv.fr, ministère du
Travail…), dont presque tout le domaine `formation` (questions 21 à 24 et 28), avec une confiance
restée élevée (0,82 à 0,90). Les consignes du domaine disent pourtant qu'un site de consultant ou
d'éditeur « ne suffit pas seul ».

Correction (même jour) : liste des sources officielles par domaine de spécialité
(`config.OFFICIAL_SOURCES`). Sans au moins une source officielle, la réponse est **gardée** (elle a
été payée et peut être juste), mais sa confiance est **plafonnée à 0,5**, et le nouveau champ
`official_sources` vaut 0 pour que l'agent le voie. Le plafond s'applique aussi aux réponses déjà en
mémoire.

## Questions par question

| N° | Durée (s) | Coût (€) | Confiance d'origine | Sources |
|---|---|---|---|---|
| 1 | 13,2 | 0,106 | 0,95 | 3 |
| 2 | 12,7 | 0,059 | 0,82 | 6 |
| 3 | 15,7 | 0,092 | 0,82 | 8 |
| 4 | 15,6 | 0,088 | 0,85 | 5 |
| 5 | 21,9 | 0,156 | 0,85 | 8 |
| 6 | 10,9 | 0,059 | 0,80 | 5 |
| 7 | 19,4 | 0,160 | 0,85 | 5 |
| 8 | 18,2 | 0,151 | 0,85 | 7 |
| 9 | 14,1 | 0,145 | 0,90 | 3 |
| 10 | 15,7 | 0,089 | 0,80 | 6 |
| 11 | 21,4 | 0,086 | 0,75 | 4 |
| 12 | 18,1 | 0,095 | 0,55 | 8 |
| 13 | 17,5 | 0,156 | 0,80 | 6 |
| 14 | 13,7 | 0,063 | 0,60 | 6 |
| 15 | 14,9 | 0,090 | 0,85 | 7 |
| 16 | 17,5 | 0,093 | 0,80 | 5 |
| 17 | 26,4 | 0,100 | 0,72 | 8 |
| 18 | 23,7 | 0,102 | 0,80 | 8 |
| 19 | 16,6 | 0,088 | 0,75 | 6 |
| 20 | 21,5 | 0,166 | 0,68 | 8 |
| 21 | 10,9 | 0,060 | 0,88 | 6 |
| 22 | 12,2 | 0,088 | 0,90 | 5 |
| 23 | 12,8 | 0,087 | 0,70 | 7 |
| 24 | 17,1 | 0,157 | 0,70 | 6 |
| 25 | 26,6 | 0,167 | 0,80 | 6 |
| 26 | 16,4 | 0,090 | 0,88 | 5 |
| 27 | 24,6 | 0,190 | 0,85 | 7 |
| 28 | 18,1 | 0,159 | 0,82 | 5 |

Sans source officielle : questions 2, 3, 12, 19, 21, 22, 23, 24 et 28.

## Suites

1. **Relire les 28 réponses** (humain) et noter juste / faux, comme le demande `QUESTIONS_TEST.md`.
2. **Améliorer la recherche du domaine `formation`** pour qu'elle trouve Légifrance et
   travail-emploi.gouv.fr (par exemple, demander explicitement le texte officiel dans la consigne).
3. Vérifier les conditions d'OpenRouter et du fournisseur de recherche de son plugin sur le droit de
   garder et resservir les résultats (voir `ANALYSE_PARALLEL_GPTCACHE_HIVEMIND_X402.md`, §9).
