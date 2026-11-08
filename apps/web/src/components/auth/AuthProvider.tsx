"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { Session, User } from "@supabase/supabase-js";

import { clearBrowserAccessToken } from "@/lib/auth/browser-access-token";
import { createBrowserSupabase } from "@/lib/supabase/client";

type AuthContextValue = {
  ready: boolean;
  session: Session | null;
  user: User | null;
  configured: boolean;
  refresh: () => Promise<void>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [session, setSession] = useState<Session | null>(null);
  const configured = Boolean(
    process.env.NEXT_PUBLIC_SUPABASE_URL?.trim() &&
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim(),
  );

  const refresh = useCallback(async () => {
    const supabase = createBrowserSupabase();
    if (!supabase) {
      setSession(null);
      setReady(true);
      return;
    }
    const { data } = await supabase.auth.getSession();
    setSession(data.session ?? null);
    setReady(true);
  }, []);

  const signOut = useCallback(async () => {
    const supabase = createBrowserSupabase();
    if (supabase) {
      await supabase.auth.signOut();
    }
    clearBrowserAccessToken();
    setSession(null);
  }, []);

  useEffect(() => {
    const supabase = createBrowserSupabase();
    if (!supabase) {
      setReady(true);
      return;
    }
    let mounted = true;
    void supabase.auth.getSession().then(({ data }) => {
      if (!mounted) return;
      setSession(data.session ?? null);
      setReady(true);
    });
    const { data: sub } = supabase.auth.onAuthStateChange((_event, next) => {
      setSession(next);
      setReady(true);
    });
    return () => {
      mounted = false;
      sub.subscription.unsubscribe();
    };
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      ready,
      session,
      user: session?.user ?? null,
      configured,
      refresh,
      signOut,
    }),
    [ready, session, configured, refresh, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}
