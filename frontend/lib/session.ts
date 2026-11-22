import { createHmac, timingSafeEqual } from 'node:crypto';

export const COOKIE = 'bearingai_studio';
export const REFRESH_COOKIE = 'bearingai_refresh';

const secret = () => process.env.SESSION_SECRET || '';

// Local prototype sessions remain supported while Supabase is configured.
export function makeLocalSession() {
  if (!secret() || secret().length < 24) throw new Error('SESSION_SECRET must be at least 24 characters');
  const exp = Date.now() + 8 * 3600 * 1000;
  const body = String(exp);
  const sig = createHmac('sha256', secret()).update(body).digest('hex');
  return `${body}.${sig}`;
}

function validLocalSession(token: string) {
  if (!secret()) return false;
  const [body, sig] = token.split('.');
  if (!body || !sig || !/^\d+$/.test(body) || Number(body) < Date.now()) return false;
  const expected = createHmac('sha256', secret()).update(body).digest('hex');
  return sig.length === expected.length && timingSafeEqual(Buffer.from(sig), Buffer.from(expected));
}

export function verifyLocalSession(token?: string) {
  return !!token && /^\d+\.[a-f0-9]{64}$/.test(token) && validLocalSession(token);
}

export function tokenExpiration(token: string): number | null {
  try {
    const payload = JSON.parse(Buffer.from(token.split('.')[1], 'base64url').toString('utf8'));
    return typeof payload.exp === 'number' ? payload.exp * 1000 : null;
  } catch {
    return null;
  }
}

// JWT integrity and role checks are performed by FastAPI/Supabase. This check
// only avoids forwarding obviously expired or malformed browser sessions.
export function verifySession(token?: string) {
  if (!token) return false;
  if (/^\d+\.[a-f0-9]{64}$/.test(token)) return verifyLocalSession(token);
  const exp = tokenExpiration(token);
  return token.split('.').length === 3 && exp !== null && exp > Date.now();
}
