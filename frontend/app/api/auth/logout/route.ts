import { NextRequest, NextResponse } from 'next/server';
import { COOKIE, REFRESH_COOKIE } from '@/lib/session';

export async function POST(req: NextRequest) {
  const origin = req.headers.get('origin');
  if (origin && origin !== req.nextUrl.origin) return NextResponse.json({ error: 'Invalid origin' }, { status: 403 });
  const access = req.cookies.get(COOKIE)?.value;
  const supabaseUrl = process.env.SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.SUPABASE_ANON_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (access && supabaseUrl && anonKey) {
    await fetch(`${supabaseUrl.replace(/\/$/, '')}/auth/v1/logout`, {
      method: 'POST',
      headers: { apikey: anonKey, authorization: `Bearer ${access}` },
      cache: 'no-store',
      signal: AbortSignal.timeout(8000),
    }).catch(() => undefined);
  }
  const response = NextResponse.json({ ok: true });
  response.cookies.set(COOKIE, '', { httpOnly: true, maxAge: 0, path: '/' });
  response.cookies.set(REFRESH_COOKIE, '', { httpOnly: true, maxAge: 0, path: '/' });
  return response;
}
