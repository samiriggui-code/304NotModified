#!/usr/bin/env bash
# Installe (ou réinstalle) 304NotModified sur un VPS Debian/Ubuntu, avec HTTPS automatique.
#
# Utilisation, en root sur le VPS :
#     bash install.sh 304notmodified.com vous@exemple.fr
#
# Deux services :
#   - 304notmodified        l'API et le MCP pour les agents (Python, port local 8304)
#   - 304notmodified-admin  le tableau de bord du propriétaire (Next.js, port local 3304), sous /admin
# Caddy sert les deux en HTTPS et bloque /internal/* (réservé au tableau de bord, sur le serveur).
#
# Le script peut être relancé sans risque : il ne refait que ce qui manque.
# Il ne touche pas au pare-feu s'il est inactif, et ne remplace jamais une configuration Caddy
# qu'il n'a pas écrite lui-même.
set -euo pipefail

DOMAIN="${1:-}"
OWNER_EMAIL="${2:-}"
REPO="git@github.com:samiriggui-code/304NotModified.git"
APP_USER="nm304"
APP_DIR="/opt/304notmodified"
DATA_DIR="/var/lib/304notmodified"
ENV_FILE="/etc/304notmodified.env"
DEPLOY_KEY="/home/$APP_USER/.ssh/id_ed25519"
NODE_DIR="/opt/node"
MARKER="# Géré par 304NotModified (deploy/install.sh)"

say() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
stop() { printf '\n\033[1;31mArrêt : %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || stop "lancez ce script en root (sudo bash install.sh $DOMAIN $OWNER_EMAIL)."
[ -n "$DOMAIN" ] || stop "indiquez le nom de domaine, par exemple : bash install.sh 304notmodified.com vous@exemple.fr"
# shellcheck disable=SC1091
[ -r /etc/os-release ] && . /etc/os-release
case "${ID:-}" in debian|ubuntu) ;; *) stop "ce script est prévu pour Debian ou Ubuntu (système trouvé : ${ID:-inconnu})." ;; esac

# Lit une valeur du fichier de réglages (vide si absente).
env_get() { [ -f "$ENV_FILE" ] && sed -n "s/^$1=//p" "$ENV_FILE" | tail -n1 | tr -d "'" || true; }
# Écrit une valeur dans le fichier de réglages (remplace la ligne si elle existe).
env_set() {
  local tmp
  tmp="$(mktemp)"
  { [ -f "$ENV_FILE" ] && grep -v "^$1=" "$ENV_FILE" || true; echo "$1='$2'"; } > "$tmp"
  install -m 640 -o root -g "$APP_USER" "$tmp" "$ENV_FILE"
  rm -f "$tmp"
}

say "1/10 Logiciels nécessaires (Python, git, Caddy pour le HTTPS)"
apt-get update -qq
apt-get install -y -qq python3 python3-venv git curl openssl dnsutils ca-certificates xz-utils >/dev/null
if ! command -v caddy >/dev/null; then
  apt-get install -y -qq caddy >/dev/null || stop "Caddy introuvable dans les paquets de ce système. Voir https://caddyserver.com/docs/install"
fi
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' || stop "Python 3.10 ou plus récent est nécessaire."

say "2/10 Node.js 22 pour le tableau de bord"
node_ok() {
  command -v node >/dev/null \
    && node -e 'const [a,b]=process.versions.node.split(".").map(Number);process.exit(a>20||(a===20&&b>=9)?0:1)'
}
if ! node_ok; then
  case "$(dpkg --print-architecture)" in
    amd64) NODE_ARCH=x64 ;;
    arm64) NODE_ARCH=arm64 ;;
    *) stop "architecture $(dpkg --print-architecture) non prévue pour Node.js." ;;
  esac
  NODE_BASE="https://nodejs.org/dist/latest-v22.x"
  SUMS="$(curl -fsS "$NODE_BASE/SHASUMS256.txt")"
  NODE_FILE="$(echo "$SUMS" | awk '{print $2}' | grep -E "^node-v22\.[0-9.]+-linux-$NODE_ARCH\.tar\.xz$")"
  curl -fsSL -o "/tmp/$NODE_FILE" "$NODE_BASE/$NODE_FILE"
  # Vérifie l'empreinte publiée par nodejs.org avant d'installer.
  (cd /tmp && echo "$SUMS" | grep " $NODE_FILE\$" | sha256sum -c --quiet -) || stop "empreinte de Node.js incorrecte."
  rm -rf "$NODE_DIR" && mkdir -p "$NODE_DIR"
  tar -xJf "/tmp/$NODE_FILE" -C "$NODE_DIR" --strip-components=1
  rm -f "/tmp/$NODE_FILE"
  for bin in node npm npx; do ln -sf "$NODE_DIR/bin/$bin" "/usr/local/bin/$bin"; done
fi
echo "   Node.js $(node --version)"

say "3/10 Le nom de domaine pointe-t-il bien sur ce serveur ?"
SERVER_IP="$(curl -4 -fsS --max-time 10 https://api.ipify.org || true)"
DOMAIN_IP="$(dig +short A "$DOMAIN" | tail -n1)"
echo "   IP de ce serveur : ${SERVER_IP:-inconnue} ; $DOMAIN pointe vers : ${DOMAIN_IP:-rien}"
if [ -z "$DOMAIN_IP" ] || { [ -n "$SERVER_IP" ] && [ "$DOMAIN_IP" != "$SERVER_IP" ]; }; then
  stop "$DOMAIN ne pointe pas (encore) vers ce serveur. Vérifiez l'enregistrement A chez votre registrar ; la propagation peut prendre jusqu'à quelques heures."
fi

say "4/10 Ports 80 et 443 libres pour Caddy ?"
if ss -ltnp 2>/dev/null | grep -E ':(80|443)\s' | grep -vq caddy; then
  ss -ltnp | grep -E ':(80|443)\s' || true
  stop "un autre programme (nginx, apache…) occupe déjà le port 80 ou 443. Il faut l'arrêter ou l'adapter : demandez de l'aide avant de continuer."
fi

say "5/10 Utilisateur système, dossiers et mémoire"
id "$APP_USER" >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin "$APP_USER"
install -d -o "$APP_USER" -g "$APP_USER" -m 750 "$DATA_DIR"
# La compilation du tableau de bord demande de la mémoire : sur un petit VPS sans swap, on en ajoute 2 Go.
MEM_MB="$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)"
if [ "$MEM_MB" -lt 2000 ] && [ "$(swapon --show | wc -l)" -eq 0 ] && [ ! -f /swapfile ]; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap -q /swapfile && swapon /swapfile
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  echo "   Mémoire : ${MEM_MB} Mo ; fichier d'échange de 2 Go ajouté (/swapfile)."
fi

say "6/10 Accès en lecture au dépôt GitHub privé (clé de déploiement)"
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
   5. Relancez : bash install.sh $DOMAIN $OWNER_EMAIL

$(cat "$DEPLOY_KEY.pub")
EOF
  exit 0
fi

say "7/10 Code, dépendances et compilation du tableau de bord (plusieurs minutes)"
if [ -d "$APP_DIR/.git" ]; then
  sudo -u "$APP_USER" git -C "$APP_DIR" pull --ff-only -q
else
  install -d -o "$APP_USER" -g "$APP_USER" "$APP_DIR"
  sudo -u "$APP_USER" git clone -q "$REPO" "$APP_DIR"
fi
sudo -u "$APP_USER" python3 -m venv "$APP_DIR/.venv"
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install -q --upgrade pip
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"
sudo -u "$APP_USER" env PATH="$NODE_DIR/bin:/usr/local/bin:/usr/bin:/bin" HOME="/home/$APP_USER" \
  bash "$APP_DIR/deploy/build-admin.sh"

say "8/10 Réglages secrets et compte du tableau de bord"
touch "$ENV_FILE" && chown root:"$APP_USER" "$ENV_FILE" && chmod 640 "$ENV_FILE"
[ -n "$(env_get NM304_DB)" ] || env_set NM304_DB "$DATA_DIR/304notmodified.sqlite3"
[ -n "$(env_get FREE_QUOTA)" ] || env_set FREE_QUOTA 1000
[ -n "$(env_get PRICE_PER_REQUEST_EUR)" ] || env_set PRICE_PER_REQUEST_EUR 0.005
# Vide = aucune recherche payante : les questions sont seulement enregistrées (mesure de la demande).
grep -q '^ANTHROPIC_API_KEY=' "$ENV_FILE" || env_set ANTHROPIC_API_KEY ""
[ -n "$(env_get SESSION_SECRET)" ] || env_set SESSION_SECRET "$(openssl rand -hex 32)"
if [ -z "$(env_get ADMIN_EMAIL)" ]; then
  [ -n "$OWNER_EMAIL" ] || stop "indiquez votre e-mail de connexion : bash install.sh $DOMAIN vous@exemple.fr"
  env_set ADMIN_EMAIL "$(echo "$OWNER_EMAIL" | tr '[:upper:]' '[:lower:]')"
fi
NEW_PASSWORD=""
if [ -z "$(env_get ADMIN_PASSWORD_HASH)" ]; then
  NEW_PASSWORD="$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-20)"
  HASH="$(printf '%s' "$NEW_PASSWORD" | "$APP_DIR/.venv/bin/python" -c \
    "import sys; sys.path.insert(0, '$APP_DIR'); from app.admin_auth import hash_password; print(hash_password(sys.stdin.read()))")"
  env_set ADMIN_PASSWORD_HASH "$HASH"
fi

say "9/10 Services permanents"
cat > /etc/systemd/system/304notmodified.service <<EOF
$MARKER
[Unit]
Description=304NotModified (API et MCP pour les agents)
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
cat > /etc/systemd/system/304notmodified-admin.service <<EOF
$MARKER
[Unit]
Description=304NotModified (tableau de bord du propriétaire)
After=network-online.target 304notmodified.service
Wants=network-online.target

[Service]
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR/admin/.next/standalone
Environment=NODE_ENV=production PORT=3304 HOSTNAME=127.0.0.1 API_URL=http://127.0.0.1:8304 NEXT_TELEMETRY_DISABLED=1
ExecStart=$NODE_DIR/bin/node server.js
Restart=always
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$APP_DIR/admin/.next/standalone/.next

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable -q 304notmodified 304notmodified-admin
systemctl restart 304notmodified 304notmodified-admin

say "10/10 HTTPS avec Caddy"
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

	# Routes internes : réservées au tableau de bord, qui les appelle sur le serveur. Jamais depuis Internet.
	handle /internal* {
		respond 404
	}

	# Tableau de bord du propriétaire.
	handle /admin* {
		reverse_proxy 127.0.0.1:3304
	}

	# API et MCP pour les agents.
	handle {
		reverse_proxy 127.0.0.1:8304
	}
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
check() { printf '   %-40s %s\n' "$1" "$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$2")"; }
check "API (attendu 200)" "https://$DOMAIN/health"
check "Tableau de bord (attendu 200)" "https://$DOMAIN/admin/signin"
check "Routes internes bloquées (attendu 404)" "https://$DOMAIN/internal/stats"
echo
echo "   API pour les agents : https://$DOMAIN  (documentation : https://$DOMAIN/docs)"
echo "   Tableau de bord     : https://$DOMAIN/admin"
echo "   En cas de souci     : journalctl -u 304notmodified -u 304notmodified-admin -u caddy -n 80"

if [ -n "$NEW_PASSWORD" ]; then
  cat <<EOF

   ================================================================
   CONNEXION AU TABLEAU DE BORD : https://$DOMAIN/admin

   E-mail       : $(env_get ADMIN_EMAIL)
   Mot de passe : $NEW_PASSWORD

   Copiez ce mot de passe dans votre gestionnaire MAINTENANT :
   il ne sera plus jamais affiché (seule son empreinte est gardée).
   ================================================================
EOF
fi
