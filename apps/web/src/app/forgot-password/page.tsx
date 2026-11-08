"use client";

import Link from "next/link";
import { useState } from "react";

import { AuthFormField } from "@/components/auth/AuthFormField";
import { AuthShell } from "@/components/auth/AuthShell";
import { useAuth } from "@/components/auth/AuthProvider";
import { Button } from "@/components/ui/button";
import { mapAuthError } from "@/lib/auth/map-auth-error";
import { recoveryRedirectTo, requireSupabaseBrowser } from "@/lib/auth/supabase-auth";

export default function ForgotPasswordPage() {
  const { configured } = useAuth();
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [sent, setSent] = useState(false);
  const [fieldError, setFieldError] = useState("");

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (!email.trim()) {
      setFieldError("Email is required.");
      return;
    }
    setFieldError("");
    setBusy(true);
    try {
      const supabase = requireSupabaseBrowser();
      const { error: authError } = await supabase.auth.resetPasswordForEmail(email.trim(), {
        redirectTo: recoveryRedirectTo(),
      });
      if (authError) {
        setError(mapAuthError(authError));
        return;
      }
      // Always show success-style message to avoid email enumeration UX extremes,
      // while still surfacing hard provider failures above.
      setSent(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : mapAuthError(null));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell
      title="Reset password"
      subtitle="We will email a secure recovery link if the account exists."
      footer={
        <Link href="/login" className="text-primary hover:underline">
          Back to sign in
        </Link>
      }
    >
      {sent ? (
        <div className="space-y-4 text-sm">
          <p className="rounded-lg border border-primary/35 bg-primary/10 px-3 py-3">
            If an account exists for that email, a recovery link is on the way. Open it on this
            device to set a new password.
          </p>
          <Button asChild variant="secondary" className="w-full">
            <Link href="/login">Return to sign in</Link>
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
            error={fieldError}
            disabled={busy || !configured}
            required
          />
          {error ? (
            <p className="rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">
              {error}
            </p>
          ) : null}
          <Button type="submit" variant="cyan" className="w-full" disabled={busy || !configured}>
            {busy ? "Sending…" : "Send recovery link"}
          </Button>
        </form>
      )}
    </AuthShell>
  );
}
