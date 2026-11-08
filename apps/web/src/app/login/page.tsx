"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { toast } from "sonner";

import { AuthFormField } from "@/components/auth/AuthFormField";
import { AuthShell } from "@/components/auth/AuthShell";
import { useAuth } from "@/components/auth/AuthProvider";
import { LogoLoader } from "@/components/brand/LogoLoader";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { mapAuthError } from "@/lib/auth/map-auth-error";
import { safeInternalPath } from "@/lib/auth/safe-redirect";
import { requireSupabaseBrowser } from "@/lib/auth/supabase-auth";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const next = safeInternalPath(params.get("next"));
  const { ready, session, configured } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<{ email?: string; password?: string }>({});

  useEffect(() => {
    if (ready && session) router.replace(next);
  }, [ready, session, router, next]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    const fe: { email?: string; password?: string } = {};
    if (!email.trim()) fe.email = "Email is required.";
    if (!password) fe.password = "Password is required.";
    setFieldErrors(fe);
    if (Object.keys(fe).length) return;

    setBusy(true);
    try {
      const supabase = requireSupabaseBrowser();
      const { error: authError } = await supabase.auth.signInWithPassword({
        email: email.trim(),
        password,
      });
      if (authError) {
        const message = mapAuthError(authError);
        setError(message);
        toast.error(message);
        return;
      }
      toast.success("Signed in");
      router.replace(next);
    } catch (err) {
      const message = err instanceof Error ? err.message : mapAuthError(null);
      setError(message);
      toast.error(message);
    } finally {
      setBusy(false);
    }
  }

  if (!ready) return <LogoLoader label="Loading…" className="py-24" />;
  if (session) return <LogoLoader label="Continuing…" className="py-24" />;

  return (
    <AuthShell
      title="Sign in"
      subtitle="Welcome back — sign in to your CryptoNova workspace."
      footer={
        <>
          New here?{" "}
          <Link href="/signup" className="text-primary hover:underline">
            Create an account
          </Link>
        </>
      }
    >
      {!configured ? (
        <p className="rounded-lg border border-warning/40 bg-warning/10 px-3 py-2 text-sm text-warning">
          Supabase public env is not configured in this build.
        </p>
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
            disabled={busy}
            required
          />
          <AuthFormField
            id="password"
            label="Password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(ev) => setPassword(ev.target.value)}
            error={fieldErrors.password}
            disabled={busy}
            required
          />
          <div className="flex justify-end">
            <Link
              href="/forgot-password"
              className="text-xs text-muted-foreground hover:text-primary"
            >
              Forgot password?
            </Link>
          </div>
          {error ? (
            <p className="rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">
              {error}
            </p>
          ) : null}
          <Button type="submit" variant="cyan" className="w-full" disabled={busy || !configured}>
            {busy ? "Signing in…" : "Sign in"}
          </Button>
          <Separator className="bg-border/70" />
          <p className="text-[11px] leading-relaxed text-muted-foreground">
            API data still requires FastAPI JWT verification. A browser session alone does not unlock
            private wallet reads.
          </p>
        </form>
      )}
    </AuthShell>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<LogoLoader label="Loading…" className="py-24" />}>
      <LoginForm />
    </Suspense>
  );
}
