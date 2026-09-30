#!/usr/bin/env bash
# Installe (ou réinstalle) 304NotModified sur un VPS Debian/Ubuntu, avec HTTPS automatique.
#
# Utilisation, en root sur le VPS :
#     bash install.sh 304notmodified.com
#
# Le script peut être relancé sans risque : il ne refait que ce qui manque.
# Il ne touche pas au pare-feu s'il est inactif, et ne remplace jamais une configuration Caddy
# qu'il n'a pas écrite lui-même.
set -euo pipefail

DOMAIN="${1:-}"
REPO="git@github.com:samiriggui-code/304NotModified.git"
APP_USER="nm304"
APP_DIR="/opt/304notmodified"
DATA_DIR="/var/lib/304notmodified"
ENV_FILE="/etc/304notmodified.env"
DEPLOY_KEY="/home/$APP_USER/.ssh/id_ed25519"
MARKER="# Géré par 304NotModified (deploy/install.sh)"

say() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
stop() { printf '\n\033[1;31mArrêt : %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || stop "lancez ce script en root (sudo bash install.sh $DOMAIN)."
[ -n "$DOMAIN" ] || stop "indiquez le nom de domaine, par exemple : bash install.sh 304notmodified.com"
# shellcheck disable=SC1091
[ -r /etc/os-release ] && . /etc/os-release
case "${ID:-}" in debian|ubuntu) ;; *) stop "ce script est prévu pour Debian ou Ubuntu (système trouvé : ${ID:-inconnu})." ;; esac

say "1/8 Logiciels nécessaires (Python, git, Caddy pour le HTTPS)"
apt-get update -qq
apt-get install -y -qq python3 python3-venv git curl openssl dnsutils ca-certificates >/dev/null
if ! command -v caddy >/dev/null; then
  apt-get install -y -qq caddy >/dev/null || stop "Caddy introuvable dans les paquets de ce système. Voir https://caddyserver.com/docs/install"
fi
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' || stop "Python 3.10 ou plus récent est nécessaire."

say "2/8 Le nom de domaine pointe-t-il bien sur ce serveur ?"
SERVER_IP="$(curl -4 -fsS --max-time 10 https://api.ipify.org || true)"
DOMAIN_IP="$(dig +short A "$DOMAIN" | tail -n1)"
echo "   IP de ce serveur : ${SERVER_IP:-inconnue} ; $DOMAIN pointe vers : ${DOMAIN_IP:-rien}"
if [ -z "$DOMAIN_IP" ] || { [ -n "$SERVER_IP" ] && [ "$DOMAIN_IP" != "$SERVER_IP" ]; }; then
  stop "$DOMAIN ne pointe pas (encore) vers ce serveur. Vérifiez l'enregistrement A chez votre registrar ; la propagation peut prendre jusqu'à quelques heures."
fi

say "3/8 Ports 80 et 443 libres pour Caddy ?"
if ss -ltnp 2>/dev/null | grep -E ':(80|443)\s' | grep -vq caddy; then
  ss -ltnp | grep -E ':(80|443)\s' || true
  stop "un autre programme (nginx, apache…) occupe déjà le port 80 ou 443. Il faut l'arrêter ou l'adapter : demandez de l'aide avant de continuer."
fi

say "4/8 Utilisateur système et dossiers"
id "$APP_USER" >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin "$APP_USER"
install -d -o "$APP_USER" -g "$APP_USER" -m 750 "$DATA_DIR"

say "5/8 Accès en lecture au dépôt GitHub privé (clé de déploiement)"
if [ ! -f "$DEPLOY_KEY" ]; then
  sudo -u "$APP_USER" mkdir -p -m 700 "/home/$APP_USER/.ssh"
  sudo -u "$APP_USER" ssh-keygen -q -t ed25519 -N "" -C "304notmodified-vps" -f "$DEPLOY_KEY"
fi
sudo -u "$APP_USER" sh -c "ssh-keyscan -t ed25519 github.com >> ~/.ssh/known_hosts 2>/dev/null; sort -u -o ~/.ssh/known_hosts ~/.ssh/known_hosts"
if ! sudo -u "$APP_USER" git ls-remote "$REPO" >/dev/null 2>&1; then
  cat <<EOF

   Le serveur n'a pas encore le droit de lire le dépôt. À faire une seule fois :
   1. Ouvrez https://github.com/samiriggui-code/304NotModified/settings/keys/new
   2. Title : VPS 304notmodified
   3. Key : collez la ligne ci-dessous (elle est publique, sans danger)
   4. Laissez « Allow write access » DÉCOCHÉ, puis « Add key »
   5. Relancez : bash install.sh $DOMAIN

$(cat "$DEPLOY_KEY.pub")
EOF
  exit 0
fi

say "6/8 Code et dépendances"
if [ -d "$APP_DIR/.git" ]; then
  sudo -u "$APP_USER" git -C "$APP_DIR" pull --ff-only -q
else
  install -d -o "$APP_USER" -g "$APP_USER" "$APP_DIR"
  sudo -u "$APP_USER" git clone -q "$REPO" "$APP_DIR"
fi
sudo -u "$APP_USER" python3 -m venv "$APP_DIR/.venv"
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install -q --upgrade pip
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

say "7/8 Réglages secrets et service permanent"
NEW_TOKEN=""
if [ ! -f "$ENV_FILE" ]; then
  NEW_TOKEN="$(openssl rand -hex 32)"
  cat > "$ENV_FILE" <<EOF
# Réglages de 304NotModified. Fichier secret : ne jamais le copier dans git.
ADMIN_TOKEN=$NEW_TOKEN
# Vide = aucune recherche payante : les questions sont seulement enregistrées (mesure de la demande).
ANTHROPIC_API_KEY=
NM304_DB=$DATA_DIR/304notmodified.sqlite3
FREE_QUOTA=1000
PRICE_PER_REQUEST_EUR=0.005
EOF
fi
chown root:"$APP_USER" "$ENV_FILE"
chmod 640 "$ENV_FILE"

cat > /etc/systemd/system/304notmodified.service <<EOF
$MARKER
[Unit]
Description=304NotModified
After=network-online.target
Wants=network-online.target

[Service]
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$APP_DIR/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8304 --proxy-headers
Restart=always
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$DATA_DIR

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable -q 304notmodified
systemctl restart 304notmodified

say "8/8 HTTPS avec Caddy"
CADDYFILE=/etc/caddy/Caddyfile
# On n'écrase que le fichier d'exemple livré avec Caddy, ou celui écrit par ce script.
if [ -f "$CADDYFILE" ] && ! grep -q "$MARKER" "$CADDYFILE" \
  && ! grep -q "The Caddyfile is an easy way to configure your Caddy web server" "$CADDYFILE"; then
  stop "$CADDYFILE contient déjà une configuration personnalisée : je ne l'écrase pas. Demandez de l'aide pour fusionner."
fi
cat > "$CADDYFILE" <<EOF
$MARKER
$DOMAIN {
	encode gzip
	reverse_proxy 127.0.0.1:8304
}

www.$DOMAIN {
	redir https://$DOMAIN{uri} permanent
}
EOF
caddy validate --config "$CADDYFILE" --adapter caddyfile >/dev/null
systemctl enable -q caddy
systemctl reload caddy 2>/dev/null || systemctl restart caddy

if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then
  ufw allow OpenSSH >/dev/null; ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null
  echo "   Pare-feu : ports SSH, 80 et 443 ouverts."
fi

say "Vérification"
for _ in $(seq 1 30); do
  curl -fsS --max-time 5 "https://$DOMAIN/health" >/dev/null 2>&1 && break
  sleep 2
done
if curl -fsS --max-time 5 "https://$DOMAIN/health"; then
  echo
  echo "   En ligne : https://$DOMAIN"
  echo "   Tableau de bord : https://$DOMAIN/admin"
else
  echo "   Le service ne répond pas encore en HTTPS. Diagnostic :"
  echo "   journalctl -u 304notmodified -n 50 ; journalctl -u caddy -n 50"
fi

if [ -n "$NEW_TOKEN" ]; then
  cat <<EOF

   ================================================================
   MOT DE PASSE DU TABLEAU DE BORD (jeton administrateur) :

   $NEW_TOKEN

   Copiez-le dans votre gestionnaire de mots de passe MAINTENANT.
   Il est aussi dans $ENV_FILE (lisible par root uniquement).
   ================================================================
EOF
fi
