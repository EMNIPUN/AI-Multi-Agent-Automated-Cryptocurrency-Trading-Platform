"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { useAuth } from "@/components/auth/AuthProvider";
import { DataModeBanner } from "@/components/shared/DataModeBanner";
import { EmptyState } from "@/components/shared/EmptyState";
import { SettingsTemplate } from "@/components/design-system/templates";
import { LogoLoader } from "@/components/brand/LogoLoader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { authHeaders } from "@/lib/auth/browser-access-token";
import {
  statusBadgeVariant,
  type ExchangeBindingListResponse,
  type ExchangeBindingPublic,
} from "@/lib/exchange/bindings";

export default function ExchangeAccountsPage() {
  const { ready, session, configured } = useAuth();
  const [data, setData] = useState<ExchangeBindingListResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [actionId, setActionId] = useState<string | null>(null);
  const sessionUserId = session?.user?.id ?? null;

  const load = useCallback(async () => {
    if (!sessionUserId) {
      setData(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/api/exchange/bindings", {
        headers: await authHeaders(),
        cache: "no-store",
      });
      const body = (await res.json().catch(() => ({}))) as ExchangeBindingListResponse & {
        detail?: string;
        message?: string;
      };
      if (!res.ok) {
        setError(
          typeof body.detail === "string"
            ? body.detail
            : body.message || `Failed to load bindings (${res.status})`,
        );
        setData(null);
        return;
      }
      setData(body);
    } catch {
      setError("Unable to reach the bindings API.");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [sessionUserId]);

  useEffect(() => {
    if (!ready) return;
    void load();
  }, [ready, load]);

  async function requestTestnetPending() {
    setBusy(true);
    setError("");
    try {
      const res = await fetch("/api/exchange/bindings", {
        method: "POST",
        headers: {
          ...(await authHeaders()),
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          environment: "testnet",
          display_label: "Bybit Testnet (pending)",
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        const message =
          typeof body.detail === "string"
            ? body.detail
            : `Request failed (${res.status})`;
        setError(message);
        toast.error(message);
        return;
      }
      toast.success("Testnet binding requested (pending)");
      await load();
    } catch {
      setError("Unable to create pending binding.");
      toast.error("Unable to create pending binding.");
    } finally {
      setBusy(false);
    }
  }

  async function revokeBinding(binding: ExchangeBindingPublic) {
    setActionId(binding.id);
    setError("");
    try {
      const res = await fetch(`/api/exchange/bindings/${binding.id}/revoke`, {
        method: "POST",
        headers: await authHeaders(),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        const message =
          typeof body.detail === "string"
            ? body.detail
            : `Revoke failed (${res.status})`;
        setError(message);
        toast.error(message);
        return;
      }
      toast.success("Binding revoked");
      await load();
    } catch {
      setError("Unable to revoke binding.");
      toast.error("Unable to revoke binding.");
    } finally {
      setActionId(null);
    }
  }

  async function simulateVerify(binding: ExchangeBindingPublic) {
    setActionId(`verify:${binding.id}`);
    setError("");
    try {
      const res = await fetch(
        `/api/exchange/bindings/${binding.id}/simulate-verify`,
        {
          method: "POST",
          headers: await authHeaders(),
        },
      );
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        const message =
          typeof body.detail === "string"
            ? body.detail
            : body.verification?.safe_message ||
              `Simulation failed (${res.status})`;
        setError(message);
        toast.error(message);
        return;
      }
      toast.success("Simulated Testnet verification finished");
      await load();
    } catch {
      setError("Unable to run verification simulator.");
      toast.error("Unable to run verification simulator.");
    } finally {
      setActionId(null);
    }
  }

  if (!ready) {
    return <LogoLoader label="Checking session…" className="py-24" />;
  }

  return (
    <SettingsTemplate
      title="Exchanges"
      description="Secure Bybit account bindings — ownership enforced server-side. Live trading stays locked."
      modes={["readonly"]}
    >
      <DataModeBanner
        mode="demo"
        notes={[
          "Fixture / offline bindings only — not a live exchange connection.",
          "Simulated Testnet verification is not a real Bybit connection.",
          "Private wallet reads remain disabled. Mainnet activation locked.",
        ]}
      />

      <Card className="mb-4 border-border/70 bg-card/80 shadow-none">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Authentication verification required</CardTitle>
          <CardDescription>
            Real Supabase Auth E2E has not passed yet. Binding requests here use in-memory
            fixtures and must not be treated as connected exchange accounts.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2 text-xs text-muted-foreground">
          <Badge variant="warning">Auth E2E: NOT PASS</Badge>
          <Badge variant="outline">Persistence: off</Badge>
          <Badge variant="outline">Private reads: off</Badge>
          <Badge variant="danger">Mainnet: locked</Badge>
          <Button asChild variant="outline" size="sm" className="ml-auto">
            <Link href="/settings">Back to settings</Link>
          </Button>
        </CardContent>
      </Card>

      {!configured || !session ? (
        <EmptyState
          title="Sign in required"
          badge="Auth"
          description="A verified Supabase session is required before requesting exchange bindings. FastAPI still verifies JWTs independently."
        />
      ) : (
        <div className="space-y-4">
          <Card className="border-border/70 shadow-none">
            <CardHeader>
              <CardTitle>Bybit</CardTitle>
              <CardDescription>
                Default environment: Testnet. Credential references stay opaque and
                server-side. Operator env credentials cannot be claimed from this UI.
                Activation requires a separate approved verification workflow.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-wrap items-center gap-3">
              <Button onClick={() => void requestTestnetPending()} disabled={busy}>
                {busy ? "Requesting…" : "Request Testnet binding (pending)"}
              </Button>
              <Button variant="outline" disabled title="Mainnet activation is locked">
                Mainnet (locked)
              </Button>
            </CardContent>
          </Card>

          <Separator className="bg-border/70" />

          {error ? (
            <p className="rounded-lg border border-[hsl(var(--loss)/0.35)] bg-[hsl(var(--loss)/0.08)] px-3 py-2 text-sm text-[hsl(var(--loss))]">
              {error}
            </p>
          ) : null}

          {loading ? (
            <div className="space-y-3" role="status" aria-label="Loading bindings">
              <Skeleton className="h-28 w-full rounded-2xl" />
              <Skeleton className="h-28 w-full rounded-2xl" />
              <Skeleton className="h-28 w-full rounded-2xl" />
            </div>
          ) : !data ? (
            <EmptyState
              title="Bindings unavailable"
              badge="API"
              description={
                error ||
                "Could not load exchange bindings. Restart FastAPI after Part 6A if routes return 404."
              }
            />
          ) : data.items.length === 0 ? (
            <EmptyState
              title="No exchange bindings"
              badge="Bybit"
              description="Request a Testnet pending binding to exercise the secure lifecycle. Nothing here is LIVE."
            />
          ) : (
            <div className="grid gap-3">
              {data.items.map((b) => (
                <Card key={b.id} className="border-border/70 shadow-none">
                  <CardContent className="grid gap-3 p-4 sm:grid-cols-[1fr_auto] sm:items-center">
                    <div className="space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium">{b.display_label}</span>
                        <Badge variant="secondary">Bybit</Badge>
                        <Badge variant="outline">{b.environment}</Badge>
                        <Badge variant={statusBadgeVariant(b.status)}>{b.status}</Badge>
                        {b.is_live_exchange_connection ? (
                          <Badge variant="success">Live connection</Badge>
                        ) : (
                          <Badge variant="sample">Not a live connection</Badge>
                        )}
                        <Badge
                          variant={
                            b.verification_status === "simulated_verified"
                              ? "warning"
                              : b.verification_status === "simulated_failed"
                                ? "danger"
                                : "secondary"
                          }
                        >
                          Verify: {b.verification_status || "unverified"}
                        </Badge>
                      </div>
                      <dl className="grid gap-1 text-xs text-muted-foreground sm:grid-cols-2">
                        <div>
                          <dt className="inline text-muted-foreground/80">Credential ref </dt>
                          <dd className="inline font-mono text-foreground">
                            {b.credential_ref_alias}
                          </dd>
                        </div>
                        <div>
                          <dt className="inline text-muted-foreground/80">Last verified </dt>
                          <dd className="inline">
                            {b.last_verified_at
                              ? new Date(b.last_verified_at).toLocaleString()
                              : "Never"}
                          </dd>
                        </div>
                        <div>
                          <dt className="inline text-muted-foreground/80">Persistence </dt>
                          <dd className="inline">{b.persistence}</dd>
                        </div>
                        <div>
                          <dt className="inline text-muted-foreground/80">Updated </dt>
                          <dd className="inline">
                            {new Date(b.updated_at).toLocaleString()}
                          </dd>
                        </div>
                      </dl>
                      {b.verification_message ? (
                        <p className="text-xs text-muted-foreground">{b.verification_message}</p>
                      ) : null}
                      {b.activation_blocked_reason ? (
                        <p className="text-xs text-muted-foreground">
                          Blocked: {b.activation_blocked_reason}
                        </p>
                      ) : null}
                      <p className="text-xs text-muted-foreground">
                        Simulated verification never marks this account ACTIVE or connected LIVE.
                      </p>
                    </div>
                    <div className="flex flex-col gap-2 sm:items-end">
                      {b.status !== "revoked" && b.environment === "testnet" ? (
                        <Button
                          variant="secondary"
                          size="sm"
                          disabled={actionId === `verify:${b.id}` || actionId === b.id}
                          onClick={() => void simulateVerify(b)}
                        >
                          {actionId === `verify:${b.id}`
                            ? "Simulating…"
                            : "Simulate Testnet verify"}
                        </Button>
                      ) : null}
                      {b.status !== "revoked" ? (
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={actionId === b.id || actionId === `verify:${b.id}`}
                          onClick={() => void revokeBinding(b)}
                        >
                          {actionId === b.id ? "Revoking…" : "Revoke"}
                        </Button>
                      ) : null}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </div>
      )}
    </SettingsTemplate>
  );
}
