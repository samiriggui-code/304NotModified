import { NextRequest, NextResponse } from 'next/server';
import { SESSION_COOKIE } from '@/lib/session';

// Redirige vers /signin tant qu'aucune session n'existe.
// La validité du jeton est vérifiée par l'API à chaque appel (403 → purge du cookie).
// nextUrl.pathname ne contient pas le basePath (/admin) ; clone() le conserve dans les redirections.
export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const hasSession = request.cookies.has(SESSION_COOKIE);

  if (pathname === '/signin') {
    if (!hasSession) return NextResponse.next();
    const home = request.nextUrl.clone();
    home.pathname = '/';
    home.search = '';
    return NextResponse.redirect(home);
  }

  if (!hasSession) {
    const signin = request.nextUrl.clone();
    signin.pathname = '/signin';
    signin.search = `?callbackUrl=${encodeURIComponent(`${pathname}${search}`)}`;
    return NextResponse.redirect(signin);
  }

  return NextResponse.next();
}

export const config = {
  // « / » est listé à part : avec un basePath (/admin), le motif général ne couvre pas la racine.
  matcher: ['/', '/((?!api/|_next/|media/|favicon.ico|icon.svg).*)'],
};
