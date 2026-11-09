"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { AuthFormField } from "@/components/auth/AuthFormField";
import { AuthShell } from "@/components/auth/AuthShell";
import { useAuth } from "@/components/auth/AuthProvider";
import { LogoLoader } from "@/components/brand/LogoLoader";
import { Button } from "@/components/ui/button";
import { mapAuthError } from "@/lib/auth/map-auth-error";
import { createBrowserSupabase } from "@/lib/supabase/client";
import { requireSupabaseBrowser } from "@/lib/auth/supabase-auth";

export default function ResetPasswordPage() {
  const router = useRouter();
  const { ready, session, configured } = useAuth();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [recoveryReady, setRecoveryReady] = useState(false);
  const [done, setDone] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<{ password?: string; confirm?: string }>({});

  useEffect(() => {
    const supabase = createBrowserSupabase();
    if (!supabase) return;
    const { data } = supabase.auth.onAuthStateChange((event) => {
      if (event === "PASSWORD_RECOVERY") setRecoveryReady(true);
    });
    // detectSessionInUrl may already have established a recovery session
    void supabase.auth.getSession().then(({ data: sess }) => {
      if (sess.session) setRecoveryReady(true);
    });
    return () => data.subscription.unsubscribe();
  }, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    const fe: { password?: string; confirm?: string } = {};
    if (password.length < 8) fe.password = "Use at least 8 characters.";
    if (password !== confirm) fe.confirm = "Passwords do not match.";
    setFieldErrors(fe);
    if (Object.keys(fe).length) return;

    setBusy(true);
    try {
      const supabase = requireSupabaseBrowser();
      const { error: authError } = await supabase.auth.updateUser({ password });
      if (authError) {
        setError(mapAuthError(authError));
        return;
      }
      setDone(true);
      setTimeout(() => router.replace("/orchestrator"), 1200);
    } catch (err) {
      setError(err instanceof Error ? err.message : mapAuthError(null));
    } finally {
      setBusy(false);
    }
  }

  if (!ready) return <LogoLoader label="Loading…" className="py-24" />;

  const canUpdate = Boolean(session || recoveryReady);

  return (
    <AuthShell
      title="Set a new password"
      subtitle="Choose a strong password for this account."
      footer={
        <Link href="/login" className="text-primary hover:underline">
          Back to sign in
        </Link>
      }
    >
      {!configured ? (
        <p className="text-sm text-warning">Supabase is not configured.</p>
      ) : done ? (
        <p className="rounded-lg border border-primary/35 bg-primary/10 px-3 py-3 text-sm">
          Password updated. Redirecting…
        </p>
      ) : !canUpdate ? (
        <div className="space-y-3 text-sm text-muted-foreground">
          <p>
            Open the recovery link from your email on this browser. If the link expired, request a
            new one.
          </p>
          <Button asChild variant="secondary" className="w-full">
            <Link href="/forgot-password">Request a new link</Link>
          </Button>
        </div>
      ) : (
        <form className="space-y-4" onSubmit={onSubmit} noValidate>
          <AuthFormField
            id="password"
            label="New password"
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(ev) => setPassword(ev.target.value)}
            error={fieldErrors.password}
            disabled={busy}
            required
          />
          <AuthFormField
            id="confirm"
            label="Confirm new password"
            type="password"
            autoComplete="new-password"
            value={confirm}
            onChange={(ev) => setConfirm(ev.target.value)}
            error={fieldErrors.confirm}
            disabled={busy}
            required
          />
          {error ? (
            <p className="rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">
              {error}
            </p>
          ) : null}
          <Button type="submit" variant="brand" className="w-full" disabled={busy}>
            {busy ? "Updating…" : "Update password"}
          </Button>
        </form>
      )}
    </AuthShell>
  );
}
