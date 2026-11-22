import { NextRequest, NextResponse } from 'next/server';
import { lookup } from 'node:dns/promises';
import { COOKIE, REFRESH_COOKIE, tokenExpiration, verifyLocalSession, verifySession } from '@/lib/session';

// API_INTERNAL_URL is an origin, for example https://bearingai.onrender.com.
// Keep the fallback for local development, and never log the value itself.
const api = (process.env.API_INTERNAL_URL || 'http://localhost:9000').replace(/\/+$/, '');
const supabaseUrl = process.env.SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL || '';
const anonKey = process.env.SUPABASE_ANON_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || '';
const authMode = (process.env.BEARING_AUTH_MODE || 'local').toLowerCase();
const secureCookies = (req: NextRequest) => req.nextUrl.protocol === 'https:' || req.headers.get('x-forwarded-proto') === 'https';

function safeHost(value: string) {
  try { return new URL(value).host; } catch { return 'invalid-url'; }
}

function errorKind(error: unknown) {
  const e = error as { name?: string; code?: string; message?: string; cause?: { code?: string } };
  const code = e?.code || e?.cause?.code || '';
  if (e?.name === 'TimeoutError' || code === 'ETIMEDOUT' || code === 'UND_ERR_CONNECT_TIMEOUT') return 'timeout';
  if (['ENOTFOUND', 'EAI_AGAIN', 'ENODATA'].includes(code)) return 'dns';
  if (['CERT_HAS_EXPIRED', 'CERT_NOT_YET_VALID', 'UNABLE_TO_VERIFY_LEAF_SIGNATURE', 'DEPTH_ZERO_SELF_SIGNED_CERT', 'ERR_TLS_CERT_ALTNAME_INVALID'].includes(code) || /tls|certificate/i.test(String(e?.message || ''))) return 'tls';
  if (/invalid URL/i.test(String(e?.message || ''))) return 'configuration';
  return 'network';
}

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
  // Temporary, read-only diagnostic for local development. It never returns env values.
  if (tail === '__diagnostic' && process.env.NODE_ENV !== 'production') {
    const started = Date.now();
    let dns: 'ok' | 'failed' | 'skipped' = 'skipped';
    let probe: 'ok' | 'http_error' | 'failed' = 'failed';
    let kind: string | undefined;
    let status: number | undefined;
    try {
      const url = new URL('/health', api);
      await lookup(url.hostname);
      dns = 'ok';
      const response = await fetch(url, { cache: 'no-store', signal: AbortSignal.timeout(5000) });
      status = response.status;
      probe = response.ok ? 'ok' : 'http_error';
    } catch (error) {
      kind = errorKind(error);
      if (kind === 'dns') dns = 'failed';
    }
    console.info('[api-proxy:diagnostic]', JSON.stringify({ configured: !!process.env.API_INTERNAL_URL, host: safeHost(api), dns, probe, ...(kind ? { error: kind } : {}), ...(status ? { upstreamStatus: status } : {}), durationMs: Date.now() - started }));
    return NextResponse.json({ configured: !!process.env.API_INTERNAL_URL, host: safeHost(api), dns, probe, ...(kind ? { error: kind } : {}), ...(status ? { upstreamStatus: status } : {}) });
  }
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
  const started = Date.now();

  try {
    const targetUrl = new URL(`/${tail}`, api);
    targetUrl.search = req.nextUrl.search;
    const target = targetUrl.toString();
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
    if (!upstream.ok) console.warn('[api-proxy:upstream-http]', JSON.stringify({ method: req.method, path: `/${tail}`, host: safeHost(api), status: upstream.status, durationMs: Date.now() - started }));
    if (refreshed) {
      const secure = secureCookies(req);
      response.cookies.set(COOKIE, refreshed.access, { httpOnly: true, secure, sameSite: 'lax', maxAge: refreshed.expires, path: '/' });
      response.cookies.set(REFRESH_COOKIE, refreshed.refresh, { httpOnly: true, secure, sameSite: 'lax', maxAge: 60 * 60 * 24 * 30, path: '/' });
    }
    return response;
  } catch (error) {
    const kind = errorKind(error);
    console.error('[api-proxy:connection-failure]', JSON.stringify({ method: req.method, path: `/${tail}`, host: safeHost(api), error: kind, durationMs: Date.now() - started }));
    return NextResponse.json({ error: 'Backend unavailable' }, { status: 502 });
  }
}

export { handler as GET, handler as POST };
