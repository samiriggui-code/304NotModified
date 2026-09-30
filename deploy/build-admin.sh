#!/usr/bin/env bash
# Compile le tableau de bord (admin/, Next.js) pour la production, servi sous /admin.
# Appelé par install.sh et update.sh, en tant qu'utilisateur nm304.
set -euo pipefail

cd "$(dirname "$0")/../admin"
export NEXT_TELEMETRY_DISABLED=1
npm ci --no-audit --no-fund --loglevel=error
NEXT_PUBLIC_BASE_PATH=/admin npm run build
# La sortie autonome ne contient pas les fichiers statiques : on les ajoute.
rm -rf .next/standalone/.next/static
cp -r .next/static .next/standalone/.next/static
if [ -d public ]; then
  rm -rf .next/standalone/public
  cp -r public .next/standalone/public
fi
