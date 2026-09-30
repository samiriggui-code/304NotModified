/** @type {import('next').NextConfig} */
const nextConfig = {
  // Le tableau de bord est servi sous https://304notmodified.com/admin (Caddy : /admin* → Next).
  // Lu au moment du build : NEXT_PUBLIC_BASE_PATH=/admin npm run build
  basePath: process.env.NEXT_PUBLIC_BASE_PATH || '',

  // Sortie autonome : node .next/standalone/server.js, sans node_modules sur le serveur.
  output: 'standalone',

  devIndicators: { position: 'bottom-right' },

  // Pas d'en-tête « X-Powered-By: Next.js ».
  poweredByHeader: false,
};

export default nextConfig;
