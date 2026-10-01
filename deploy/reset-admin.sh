#!/usr/bin/env bash
# Crée (ou recrée) le compte du tableau de bord, sans rien taper : un nouveau mot de passe est
# généré, enregistré (seule son empreinte est gardée), l'API redémarre, et le mot de passe
# s'affiche une seule fois.
#
# Utilisation, en root sur le VPS :
#     bash /opt/304notmodified/deploy/reset-admin.sh                  # garde l'e-mail actuel
#     bash /opt/304notmodified/deploy/reset-admin.sh vous@exemple.fr  # change aussi l'e-mail
set -euo pipefail

APP_DIR="/opt/304notmodified"
ENV_FILE="/etc/304notmodified.env"

[ "$(id -u)" -eq 0 ] || { echo "Lancez ce script en root (sudo)." >&2; exit 1; }
[ -f "$ENV_FILE" ] || { echo "$ENV_FILE introuvable : lancez d'abord deploy/install.sh." >&2; exit 1; }

cd "$APP_DIR"
PASSWORD="$("$APP_DIR/.venv/bin/python" -m app.cli reset-admin "$ENV_FILE" "$@")"
EMAIL="$(sed -n "s/^ADMIN_EMAIL=//p" "$ENV_FILE" | tail -n1 | tr -d "'")"
# Le redémarrage prend le nouveau mot de passe en compte et lève un éventuel blocage après échecs.
systemctl restart 304notmodified

cat <<EOF

   ================================================================
   CONNEXION AU TABLEAU DE BORD : https://304notmodified.com/admin

   E-mail       : $EMAIL
   Mot de passe : $PASSWORD

   Copiez ce mot de passe dans votre gestionnaire MAINTENANT :
   il ne sera plus jamais affiché (seule son empreinte est gardée).
   ================================================================
EOF
