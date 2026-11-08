/**
 * Browser-only Supabase Auth helpers.
 * FastAPI still verifies JWTs independently — this never authorizes API data alone.
 */

import { createBrowserSupabase } from "@/lib/supabase/client";

export function requireSupabaseBrowser() {
  const client = createBrowserSupabase();
  if (!client) {
    throw new Error(
      "Supabase is not configured. Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.",
    );
  }
  return client;
}

export async function getBrowserSession() {
  const supabase = createBrowserSupabase();
  if (!supabase) return null;
  const { data, error } = await supabase.auth.getSession();
  if (error) return null;
  return data.session ?? null;
}

export function recoveryRedirectTo(): string {
  if (typeof window === "undefined") return "";
  return `${window.location.origin}/reset-password`;
}

export function emailRedirectTo(): string {
  if (typeof window === "undefined") return "";
  return `${window.location.origin}/login`;
}
