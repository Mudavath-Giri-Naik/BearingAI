import { createHash, randomBytes, timingSafeEqual } from 'node:crypto';
import { NextRequest, NextResponse } from 'next/server';
import { COOKIE, makeLocalSession } from '@/lib/session';

const secureCookie = (req: NextRequest) =>
  req.nextUrl.protocol === 'https:' || req.headers.get('x-forwarded-proto') === 'https';

export async function POST(req: NextRequest) {
  const origin = req.headers.get('origin');
  if (origin && origin !== req.nextUrl.origin) return NextResponse.json({ error: 'Invalid origin' }, { status: 403 });

  const body = await req.json().catch(() => ({}));
  if (body.provider === 'google') {
    const supabaseUrl = process.env.SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL;
    const anonKey = process.env.SUPABASE_ANON_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
    if (!supabaseUrl || !anonKey) return NextResponse.json({ error: 'Supabase Auth is not configured on this server' }, { status: 503 });

    const verifier = randomBytes(32).toString('base64url');
    const challenge = createHash('sha256').update(verifier).digest('base64url');
    const callback = new URL('/api/auth/callback', req.nextUrl.origin).toString();
    const authorize = new URL('/auth/v1/authorize', supabaseUrl);
    authorize.searchParams.set('provider', 'google');
    authorize.searchParams.set('redirect_to', callback);
    authorize.searchParams.set('code_challenge', challenge);
    authorize.searchParams.set('code_challenge_method', 's256');

    const response = NextResponse.json({ redirect: authorize.toString() });
    const secure = secureCookie(req);
    response.cookies.set('bearingai_oauth_verifier', verifier, { httpOnly: true, secure, sameSite: 'lax', maxAge: 600, path: '/api/auth/callback' });
    return response;
  }

  if ((process.env.BEARING_AUTH_MODE || 'local').toLowerCase() !== 'local') {
    return NextResponse.json({ error: 'Use Supabase authentication' }, { status: 400 });
  }
  const password = typeof body.password === 'string' ? body.password : '';
  const expected = process.env.STUDIO_PASSWORD || '';
  if (!expected || !password || Buffer.byteLength(password) !== Buffer.byteLength(expected) ||
      !timingSafeEqual(Buffer.from(password), Buffer.from(expected))) {
    return NextResponse.json({ error: 'Invalid credentials' }, { status: 401 });
  }
  const response = NextResponse.json({ ok: true });
  response.cookies.set(COOKIE, makeLocalSession(), { httpOnly: true, secure: secureCookie(req), sameSite: 'strict', maxAge: 8 * 3600, path: '/' });
  return response;
}
