// Client de l'API 304NotModified, via le proxy Next /api/backend (cookie de session → Bearer).
// Usage : api.get<Stats>('stats?days=7')  →  GET {API_URL}/internal/stats?days=7
import { toAbsoluteUrl } from '@/lib/helpers';

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(toAbsoluteUrl(`/api/backend/${path}`), {
      cache: 'no-store',
      ...init,
      headers: {
        ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError(0, 'Connexion impossible : vérifiez le réseau.');
  }

  // Session absente ou expirée : retour à la connexion.
  if ((response.status === 401 || response.status === 403) && typeof window !== 'undefined') {
    const here = window.location.pathname.slice(toAbsoluteUrl('').length) + window.location.search;
    window.location.href = toAbsoluteUrl(`/signin?callbackUrl=${encodeURIComponent(here || '/')}`);
  }

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail;
    const message = Array.isArray(detail)
      ? detail.map((d: { msg?: string }) => d.msg).join(' ; ')
      : typeof detail === 'string'
        ? detail
        : `Erreur ${response.status}`;
    throw new ApiError(response.status, message);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string) => apiFetch<T>(path),
  post: <T>(path: string, body: unknown = {}) =>
    apiFetch<T>(path, { method: 'POST', body: JSON.stringify(body) }),
};
