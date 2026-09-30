// Session côté Next : le jeton émis par l'API (POST /internal/auth/login) est stocké dans un cookie
// httpOnly. Le navigateur n'y a jamais accès ; les appels passent par les route handlers Next
// (/api/auth/*, /api/backend/*), qui ajoutent le Bearer et parlent à l'API sur le serveur.

export const SESSION_COOKIE = 'nm304_admin';

// Aligné sur SESSION_TTL_SECONDS de l'API (12 h).
export const SESSION_MAX_AGE = 12 * 60 * 60;

// L'API tourne sur la même machine ; ses routes /internal/* ne sont pas exposées sur Internet.
export const API_URL = process.env.API_URL || 'http://127.0.0.1:8304';

export const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH || '';

export interface SessionUser {
  email: string;
}

// N'accepte qu'un chemin interne, pour éviter les redirections ouvertes.
export function safeCallbackUrl(value: string | null | undefined): string {
  if (!value || !value.startsWith('/') || value.startsWith('//')) return '/';
  return value;
}
