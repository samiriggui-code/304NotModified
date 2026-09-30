# Questions de référence : facturation électronique (tous aspects)

> À poser au service (domaine `facturation`) une fois la clé Anthropic activée, pour juger la
> qualité des réponses avant de démarcher des clients. Chaque réponse doit être relue par un
> humain et comparée au document officiel.
> Pour chaque question, noter : réponse juste ou fausse, sources citées (officielles ou non),
> dates et versions données, confiance, coût, durée.

## Réglementation

1. Depuis quand une entreprise française doit-elle pouvoir recevoir des factures électroniques ?
2. À partir de quand une PME doit-elle émettre ses factures au format électronique ?
3. Une micro-entreprise en franchise de TVA est-elle concernée ?
4. Quelles nouvelles mentions obligatoires doivent figurer sur les factures ?
5. Quelles sanctions en cas de non-respect de l'obligation ?
6. Les factures B2C et les factures de fournisseurs étrangers sont-elles concernées ?

## Technique

7. Quels formats de facture structurée sont acceptés (Factur-X, UBL, CII) et avec quels profils ?
8. Quelle est la version en vigueur des normes AFNOR XP Z12-012, 013 et 014, et leur date ?
   (piège connu : des pages récentes citent encore la version de février 2026 ; voir `CAS_REELS.md`, cas n°5)
9. Quelle est la dernière version des spécifications externes de la DGFiP ?

## Intégration

10. Quels flux couvre l'API XP Z12-013, et quelle authentification impose-t-elle ?
11. Où télécharger les swaggers officiels de l'API XP Z12-013 ?
12. Comment interroger l'annuaire pour trouver la plateforme d'un destinataire à partir de son SIREN ?
13. Les échanges entre plateformes agréées passent-ils par Peppol ?
14. Combien y a-t-il de plateformes agréées, et où trouver la liste officielle ?
    (piège connu : les chiffres varient selon les sources)
15. Quelle est la différence entre une plateforme agréée et une solution compatible ?

## Process

16. Quels sont les statuts de cycle de vie obligatoires, et qui déclenche chacun ?
17. Comment traiter une facture rejetée ou en litige : avoir, nouvelle facture, statut ?
18. Quelles données transmettre en e-reporting, et à quelle fréquence ?
19. Combien de temps et sous quelle forme archiver les factures électroniques ?
20. Comment changer de plateforme agréée sans interrompre la réception des factures ?
