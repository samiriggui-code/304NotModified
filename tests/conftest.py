import os

# Empêche la création de l'application globale (et de sa base SQLite) à l'import.
os.environ["NM304_AUTOSTART"] = "0"
