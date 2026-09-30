import { NextResponse } from 'next/server';
import { BASE_PATH, SESSION_COOKIE } from '@/lib/session';

export async function POST() {
  const response = NextResponse.json({ ok: true });
  response.cookies.set(SESSION_COOKIE, '', { path: BASE_PATH || '/', maxAge: 0 });
  return response;
}
