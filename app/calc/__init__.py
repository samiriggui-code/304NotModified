"""Calculs sur les données fournies par l'agent (Ichimoku × volume relatif, régime, taille de position).

Repris à l'identique du moteur IchiVol du même propriétaire (dépôt IchiVol, ichivol-app/engine :
app/indicators/ichimoku.py, rvol.py, atr.py, adx.py, app/strategy_lab/regime.py, app/paper/risk.py),
sans ses fournisseurs de données. 304 ne fournit aucune donnée de marché : l'agent envoie ses propres
bougies, 304 vend le calcul et la méthode. Les conditions de Binance (données sous licence non
commerciale, indicateurs dérivés compris) et de CoinGecko interdisent de revendre des indicateurs
calculés sur leurs données : voir docs/CAS_REELS.md, cas 15 et 16.

Règle de toutes ces fonctions : la valeur à la bougie i ne dépend que des bougies 0..i (aucun regard
vers le futur), vérifié par troncature dans tests/test_calc.py. Ce sont des calculs, jamais des conseils
d'achat ou de vente.
"""

METHOD_VERSION = "ichivol-2026-10-01"
DISCLAIMER = (
    "Calcul déterministe sur les bougies fournies, selon la méthode publiée ci-dessus. "
    "Ce n'est pas un conseil en investissement ni une recommandation d'acheter ou de vendre."
)
