#!/usr/bin/env bash
# Met à jour 304NotModified sur le VPS avec la dernière version de la branche main :
# code, dépendances Python, compilation du tableau de bord, redémarrage des deux services.
# Les routes Traefik ne changent pas (relancer install.sh pour les réécrire).
# Utilisation, en root sur le VPS :  bash /opt/304notmodified/deploy/update.sh
set -euo pipefail

APP_USER="nm304"
APP_DIR="/opt/304notmodified"
NODE_DIR="/opt/node"

[ "$(id -u)" -eq 0 ] || { echo "Lancez ce script en root (sudo)." >&2; exit 1; }

sudo -u "$APP_USER" git -C "$APP_DIR" pull --ff-only
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"
sudo -u "$APP_USER" env PATH="$NODE_DIR/bin:/usr/local/bin:/usr/bin:/bin" HOME="/home/$APP_USER" \
  bash "$APP_DIR/deploy/build-admin.sh"
systemctl restart 304notmodified 304notmodified-admin
sleep 3
systemctl --no-pager --lines=0 status 304notmodified 304notmodified-admin
# Adresse d'écoute écrite par install.sh (passerelle du réseau Docker de Traefik).
BIND_IP="$(sed -n 's/.*--host \([0-9.]*\).*/\1/p' /etc/systemd/system/304notmodified.service)"
curl -fsS "http://$BIND_IP:8304/health" && echo
curl -fsS -o /dev/null -w "Tableau de bord : %{http_code}\n" "http://$BIND_IP:3304/admin/signin"
echo "Mise à jour terminée."
