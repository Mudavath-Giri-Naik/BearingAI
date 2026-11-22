import { NextRequest, NextResponse } from 'next/server';
import { COOKIE, REFRESH_COOKIE } from '@/lib/session';

const clearTransient = (response: NextResponse) => {
  response.cookies.set('bearingai_oauth_verifier', '', { maxAge: 0, path: '/api/auth/callback' });
};

export async function GET(req: NextRequest) {
  const code = req.nextUrl.searchParams.get('code');
  const verifier = req.cookies.get('bearingai_oauth_verifier')?.value;
  const supabaseUrl = process.env.SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.SUPABASE_ANON_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  const fail = () => {
    const response = NextResponse.redirect(new URL('/studio?auth_error=google_login_failed', req.nextUrl.origin));
    clearTransient(response);
    return response;
  };

  if (!code || !verifier || !supabaseUrl || !anonKey) return fail();

  try {
    const response = await fetch(`${supabaseUrl.replace(/\/$/, '')}/auth/v1/token?grant_type=pkce`, {
      method: 'POST',
      headers: { apikey: anonKey, 'content-type': 'application/json' },
      body: JSON.stringify({ auth_code: code, code_verifier: verifier }),
      cache: 'no-store',
      signal: AbortSignal.timeout(15000),
    });
    if (!response.ok) return fail();
    const tokens = await response.json();
    if (typeof tokens.access_token !== 'string' || typeof tokens.refresh_token !== 'string') return fail();

    const result = NextResponse.redirect(new URL('/studio', req.nextUrl.origin));
    const secure = req.nextUrl.protocol === 'https:' || req.headers.get('x-forwarded-proto') === 'https';
    const maxAge = Math.max(60, Math.min(Number(tokens.expires_in) || 3600, 3600));
    result.cookies.set(COOKIE, tokens.access_token, { httpOnly: true, secure, sameSite: 'lax', maxAge, path: '/' });
    result.cookies.set(REFRESH_COOKIE, tokens.refresh_token, { httpOnly: true, secure, sameSite: 'lax', maxAge: 60 * 60 * 24 * 30, path: '/' });
    clearTransient(result);
    return result;
  } catch {
    return fail();
  }
}
