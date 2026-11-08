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
import { emailRedirectTo, requireSupabaseBrowser } from "@/lib/auth/supabase-auth";

export default function SignupPage() {
  const router = useRouter();
  const { ready, session, configured } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<{
    email?: string;
    password?: string;
    confirm?: string;
  }>({});

  useEffect(() => {
    if (ready && session) router.replace("/dashboard");
  }, [ready, session, router]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    const fe: { email?: string; password?: string; confirm?: string } = {};
    if (!email.trim()) fe.email = "Email is required.";
    if (password.length < 8) fe.password = "Use at least 8 characters.";
    if (password !== confirm) fe.confirm = "Passwords do not match.";
    setFieldErrors(fe);
    if (Object.keys(fe).length) return;

    setBusy(true);
    try {
      const supabase = requireSupabaseBrowser();
      const { data, error: authError } = await supabase.auth.signUp({
        email: email.trim(),
        password,
        options: { emailRedirectTo: emailRedirectTo() },
      });
      if (authError) {
        setError(mapAuthError(authError));
        return;
      }
      // If email confirmation is required, session may be null.
      if (data.session) {
        router.replace("/dashboard");
        return;
      }
      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : mapAuthError(null));
    } finally {
      setBusy(false);
    }
  }

  if (!ready) return <LogoLoader label="Loading…" className="py-24" />;
  if (session) return <LogoLoader label="Continuing…" className="py-24" />;

  return (
    <AuthShell
      title="Create account"
      subtitle="Create your free workspace and start exploring paper trading."
      footer={
        <>
          Already have an account?{" "}
          <Link href="/login" className="text-primary hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      {done ? (
        <div className="space-y-4 text-sm">
          <p className="rounded-lg border border-primary/35 bg-primary/10 px-3 py-3 text-foreground">
            Check your email to confirm your account before signing in.
          </p>
          <Button asChild variant="secondary" className="w-full">
            <Link href="/login">Back to sign in</Link>
          </Button>
        </div>
      ) : (
        <form className="space-y-4" onSubmit={onSubmit} noValidate>
          <AuthFormField
            id="email"
            label="Email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(ev) => setEmail(ev.target.value)}
            error={fieldErrors.email}
            disabled={busy || !configured}
            required
          />
          <AuthFormField
            id="password"
            label="Password"
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(ev) => setPassword(ev.target.value)}
            error={fieldErrors.password}
            hint="Minimum 8 characters."
            disabled={busy || !configured}
            required
          />
          <AuthFormField
            id="confirm"
            label="Confirm password"
            type="password"
            autoComplete="new-password"
            value={confirm}
            onChange={(ev) => setConfirm(ev.target.value)}
            error={fieldErrors.confirm}
            disabled={busy || !configured}
            required
          />
          {error ? (
            <p className="rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">
              {error}
            </p>
          ) : null}
          <Button type="submit" variant="cyan" className="w-full" disabled={busy || !configured}>
            {busy ? "Creating account…" : "Create account"}
          </Button>
        </form>
      )}
    </AuthShell>
  );
}
