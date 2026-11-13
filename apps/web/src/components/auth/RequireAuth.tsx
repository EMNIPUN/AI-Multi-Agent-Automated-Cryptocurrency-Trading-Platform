"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { LogoLoader } from "@/components/brand/LogoLoader";
import { useAuth } from "@/components/auth/AuthProvider";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { pathStartsWith, PROTECTED_ROUTE_PREFIXES } from "@/lib/auth/auth-paths";

/**
 * UI session gate only. API authorization still requires FastAPI JWT verification.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { ready, session, configured } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const mustProtect = pathStartsWith(pathname, PROTECTED_ROUTE_PREFIXES);

  useEffect(() => {
    if (!ready || !mustProtect) return;
    if (!configured) return;
    if (!session) {
      const next = encodeURIComponent(pathname || "/orchestrator");
      router.replace(`/login?next=${next}`);
    }
  }, [ready, mustProtect, configured, session, pathname, router]);

  if (!mustProtect) return <>{children}</>;
  if (!ready) {
    return (
      <div className="mx-auto flex min-h-[40vh] w-full max-w-3xl flex-col justify-center gap-3 px-2" role="status">
        <Skeleton className="h-10 w-48 rounded-full" />
        <Skeleton className="h-40 w-full rounded-3xl" />
        <Skeleton className="h-28 w-full rounded-3xl" />
        <LogoLoader label="Checking your session…" className="py-2" />
        <p className="text-center text-xs text-muted-foreground">This only takes a moment.</p>
      </div>
    );
  }
  if (!configured) {
    return (
      <div className="mx-auto max-w-lg rounded-2xl border border-border/70 bg-card/80 p-6 text-sm text-muted-foreground shadow-[var(--panel-shadow)]">
        <p className="font-display text-lg text-foreground">Auth is not configured</p>
        <p className="mt-2">
          Set{" "}
          <span className="font-mono text-brand">NEXT_PUBLIC_SUPABASE_URL</span> and{" "}
          <span className="font-mono text-brand">NEXT_PUBLIC_SUPABASE_ANON_KEY</span> to enable
          sign-in.
        </p>
        <Button asChild variant="brand" className="mt-4">
          <Link href="/">Back to home</Link>
        </Button>
      </div>
    );
  }
  if (!session) {
    return (
      <div className="flex min-h-[40vh] flex-col items-center justify-center gap-3" role="status">
        <LogoLoader label="Redirecting to sign in…" className="py-0" />
        <Button asChild variant="outline" size="sm" className="rounded-full">
          <Link href="/login">Sign in now</Link>
        </Button>
      </div>
    );
  }
  return <>{children}</>;
}
