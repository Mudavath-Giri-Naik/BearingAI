import { NextRequest, NextResponse } from 'next/server';
import { COOKIE, REFRESH_COOKIE, tokenExpiration, verifyLocalSession, verifySession } from '@/lib/session';

const api = process.env.API_INTERNAL_URL || 'http://localhost:9000';
const supabaseUrl = process.env.SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL || '';
const anonKey = process.env.SUPABASE_ANON_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || '';
const authMode = (process.env.BEARING_AUTH_MODE || 'local').toLowerCase();
const secureCookies = (req: NextRequest) => req.nextUrl.protocol === 'https:' || req.headers.get('x-forwarded-proto') === 'https';

async function refreshAccessToken(refreshToken: string) {
  if (!supabaseUrl || !anonKey) return null;
  try {
    const response = await fetch(`${supabaseUrl.replace(/\/$/, '')}/auth/v1/token?grant_type=refresh_token`, {
      method: 'POST',
      headers: { apikey: anonKey, 'content-type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
      cache: 'no-store',
      signal: AbortSignal.timeout(10000),
    });
    if (!response.ok) return null;
    const tokens = await response.json();
    if (typeof tokens.access_token !== 'string' || typeof tokens.refresh_token !== 'string') return null;
    return { access: tokens.access_token as string, refresh: tokens.refresh_token as string, expires: Math.max(60, Math.min(Number(tokens.expires_in) || 3600, 3600)) };
  } catch {
    return null;
  }
}

async function handler(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  const tail = path.join('/');
  if (!tail.startsWith('api/v1/') && tail !== 'health') return NextResponse.json({ error: 'Not found' }, { status: 404 });
  const isStudio = tail.startsWith('api/v1/studio/');
  const isPublic = tail === 'health' || tail === 'api/v1/models' || tail === 'api/v1/predict';
  if (!isStudio && !isPublic) return NextResponse.json({ error: 'Not permitted' }, { status: 403 });
  if (req.method === 'GET' && tail === 'api/v1/predict') return NextResponse.json({ error: 'Method not allowed' }, { status: 405 });

  if (isStudio && !['GET', 'HEAD'].includes(req.method)) {
    const origin = req.headers.get('origin');
    if (!origin || origin !== req.nextUrl.origin) return NextResponse.json({ error: 'Invalid origin' }, { status: 403 });
  }

  let accessToken = req.cookies.get(COOKIE)?.value;
  let refreshed: Awaited<ReturnType<typeof refreshAccessToken>> = null;
  if (isStudio && authMode === 'supabase') {
    const exp = accessToken ? tokenExpiration(accessToken) : null;
    const stillValid = !!accessToken && exp !== null && exp > Date.now() + 30000;
    if (!stillValid) {
      const refreshToken = req.cookies.get(REFRESH_COOKIE)?.value;
      refreshed = refreshToken ? await refreshAccessToken(refreshToken) : null;
      accessToken = refreshed?.access;
    }
    if (!accessToken || !verifySession(accessToken)) return NextResponse.json({ error: 'Developer authentication required' }, { status: 401 });
  } else if (isStudio && !verifyLocalSession(accessToken)) {
    return NextResponse.json({ error: 'Developer authentication required' }, { status: 401 });
  }

  const headers = new Headers();
  if (isStudio && authMode === 'supabase') headers.set('authorization', `Bearer ${accessToken}`);
  if (isStudio && authMode === 'local') headers.set('x-admin-key', process.env.BEARING_ADMIN_KEY || '');
  const contentType = req.headers.get('content-type');
  if (contentType) headers.set('content-type', contentType);
  const target = `${api}/${tail}${req.nextUrl.search}`;

  try {
    const upstream = await fetch(target, {
      method: req.method,
      headers,
      body: ['GET', 'HEAD'].includes(req.method) ? undefined : await req.arrayBuffer(),
      cache: 'no-store',
      signal: AbortSignal.timeout(120000),
    });
    const response = new NextResponse(upstream.body, {
      status: upstream.status,
      headers: { 'content-type': upstream.headers.get('content-type') || 'application/json', 'cache-control': 'no-store' },
    });
    if (refreshed) {
      const secure = secureCookies(req);
      response.cookies.set(COOKIE, refreshed.access, { httpOnly: true, secure, sameSite: 'lax', maxAge: refreshed.expires, path: '/' });
      response.cookies.set(REFRESH_COOKIE, refreshed.refresh, { httpOnly: true, secure, sameSite: 'lax', maxAge: 60 * 60 * 24 * 30, path: '/' });
    }
    return response;
  } catch {
    return NextResponse.json({ error: 'Backend unavailable' }, { status: 502 });
  }
}

export { handler as GET, handler as POST };
