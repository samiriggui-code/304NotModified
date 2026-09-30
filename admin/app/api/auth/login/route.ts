import { NextRequest, NextResponse } from 'next/server';
import { API_URL, BASE_PATH, SESSION_COOKIE, SESSION_MAX_AGE } from '@/lib/session';

export async function POST(request: NextRequest) {
  const { email, password, rememberMe } = await request.json().catch(() => ({}));

  let upstream: Response;
  try {
    upstream = await fetch(`${API_URL}/internal/auth/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        // Adresse du visiteur (transmise par Traefik) : l'API limite les essais par adresse.
        'X-Forwarded-For': request.headers.get('x-forwarded-for') ?? '',
      },
      body: JSON.stringify({ email, password }),
      cache: 'no-store',
    });
  } catch {
    return NextResponse.json({ detail: "L'API est injoignable." }, { status: 502 });
  }

  const data = await upstream.json().catch(() => ({}));
  if (!upstream.ok) {
    return NextResponse.json({ detail: data.detail ?? 'Connexion impossible.' }, { status: upstream.status });
  }

  const response = NextResponse.json({ user: data.user });
  response.cookies.set(SESSION_COOKIE, data.access_token, {
    httpOnly: true,
    sameSite: 'strict',
    secure: process.env.NODE_ENV === 'production',
    path: BASE_PATH || '/',
    // Sans « se souvenir de moi », cookie de session (supprimé à la fermeture du navigateur).
    ...(rememberMe ? { maxAge: SESSION_MAX_AGE } : {}),
  });
  return response;
}
