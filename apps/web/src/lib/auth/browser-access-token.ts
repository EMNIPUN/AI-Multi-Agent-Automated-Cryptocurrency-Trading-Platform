/**
 * Browser access token resolution for owner-bound LIVE reads.
 *
 * Prefer live Supabase Auth session (auto-refresh). Interim sessionStorage
 * remains a local operator fallback when Supabase public env is unset.
 * Never put tokens in URLs or logs.
 */

import { createBrowserSupabase } from "@/lib/supabase/client";

const STORAGE_KEY = "cryptonova.access_token";

export function getBrowserAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const value = window.sessionStorage.getItem(STORAGE_KEY);
    return value && value.trim() ? value.trim() : null;
  } catch {
    return null;
  }
}

export function setBrowserAccessToken(token: string | null): void {
  if (typeof window === "undefined") return;
  try {
    if (!token) window.sessionStorage.removeItem(STORAGE_KEY);
    else window.sessionStorage.setItem(STORAGE_KEY, token.trim());
  } catch {
    // ignore quota / private mode
  }
}

/** Clear interim storage; call after Supabase sign-out. */
export function clearBrowserAccessToken(): void {
  setBrowserAccessToken(null);
}

/**
 * Resolve bearer token.
 *
 * When NEXT_PUBLIC Supabase is configured: use the Auth session only.
 * Interim sessionStorage must not bypass / substitute for a configured Auth client
 * (signed-out → null). SessionStorage remains only when Supabase public env is unset.
 * FastAPI still cryptographically verifies any Bearer token that is sent.
 */
export async function resolveAccessToken(): Promise<string | null> {
  if (typeof window === "undefined") return null;
  try {
    const supabase = createBrowserSupabase();
    if (supabase) {
      const { data, error } = await supabase.auth.getSession();
      if (error) return null;
      const token = data.session?.access_token?.trim();
      return token || null;
    }
  } catch {
    return null;
  }
  return getBrowserAccessToken();
}

export async function authHeaders(): Promise<HeadersInit> {
  const token = await resolveAccessToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/**
 * Sync helper for static/tests — prefer authHeaders() in UI.
 * When Supabase public env is configured, returns {} so interim sessionStorage
 * cannot bypass the real Auth client on the sync path.
 */
export function authHeadersSync(): HeadersInit {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  const anon = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim();
  if (url && anon) return {};
  const token = getBrowserAccessToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/**
 * Sign out via Supabase when configured and clear interim token.
 * Does not introduce a second auth system.
 */
export async function signOutBrowserSession(): Promise<void> {
  try {
    const supabase = createBrowserSupabase();
    if (supabase) {
      await supabase.auth.signOut();
    }
  } catch {
    // still clear interim
  }
  clearBrowserAccessToken();
}
