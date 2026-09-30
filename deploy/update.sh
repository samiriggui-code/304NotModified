#!/usr/bin/env bash
# Met à jour 304NotModified sur le VPS avec la dernière version de la branche main.
# Utilisation, en root sur le VPS :  bash /opt/304notmodified/deploy/update.sh
set -euo pipefail

APP_USER="nm304"
APP_DIR="/opt/304notmodified"

[ "$(id -u)" -eq 0 ] || { echo "Lancez ce script en root (sudo)." >&2; exit 1; }

sudo -u "$APP_USER" git -C "$APP_DIR" pull --ff-only
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"
systemctl restart 304notmodified
sleep 2
systemctl --no-pager --lines=0 status 304notmodified
curl -fsS http://127.0.0.1:8304/health && echo && echo "Mise à jour terminée."
