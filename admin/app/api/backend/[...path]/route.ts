import { NextRequest, NextResponse } from 'next/server';
import { API_URL, BASE_PATH, SESSION_COOKIE } from '@/lib/session';

// Proxy authentifié vers l'API : /api/backend/stats → {API_URL}/internal/stats
// Ajoute le Bearer lu dans le cookie de session. Seules les routes /internal/* sont atteignables.
async function proxy(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  if (path.some((part) => part === '..' || part.includes('/'))) {
    return NextResponse.json({ detail: 'Chemin refusé.' }, { status: 400 });
  }
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  const url = `${API_URL}/internal/${path.map(encodeURIComponent).join('/')}${request.nextUrl.search}`;

  const headers = new Headers();
  const contentType = request.headers.get('content-type');
  if (contentType) headers.set('content-type', contentType);
  if (token) headers.set('authorization', `Bearer ${token}`);

  let upstream: Response;
  try {
    upstream = await fetch(url, {
      method: request.method,
      headers,
      body: ['GET', 'HEAD'].includes(request.method) ? undefined : await request.arrayBuffer(),
      cache: 'no-store',
    });
  } catch {
    return NextResponse.json({ detail: "L'API est injoignable." }, { status: 502 });
  }

  const response = new NextResponse(upstream.body, {
    status: upstream.status,
    headers: { 'content-type': upstream.headers.get('content-type') ?? 'application/json' },
  });
  // Jeton expiré ou invalide : on purge la session. Le cookie doit être effacé avec le même chemin que
  // celui de sa création (le basePath, /admin) : sinon le navigateur le garde, la page de connexion
  // renvoie vers le tableau de bord, qui renvoie vers la connexion… en boucle.
  if (upstream.status === 401 || upstream.status === 403) {
    response.cookies.set(SESSION_COOKIE, '', { path: BASE_PATH || '/', maxAge: 0 });
  }
  return response;
}

export { proxy as GET, proxy as POST };
