"use client";

import { useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export function AutomationControlPanel() {
  const [status, setStatus] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/automation/status", { cache: "no-store" });
      if (!res.ok) throw new Error(`automation_status_${res.status}`);
      setStatus((await res.json()) as Record<string, unknown>);
    } catch (err) {
      setError(err instanceof Error ? err.message : "automation_unavailable");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const local = (status?.local_execution as Record<string, unknown> | undefined) || {};

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0">
        <div>
          <CardTitle className="text-base">Automation control (Phase 6A)</CardTitle>
          <CardDescription>
            Trading mode and risk visibility. Live execution controls stay disarmed until
            operator-approved Testnet gates open. Not Mainnet.
          </CardDescription>
        </div>
        <Button size="sm" variant="outline" onClick={() => void refresh()} disabled={loading}>
          {loading ? "…" : "Refresh"}
        </Button>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <div className="flex flex-wrap gap-2">
          <Badge variant="outline">mode {String(status?.mode ?? "SIGNALS_ONLY")}</Badge>
          <Badge variant="sample">CONTROLS DISARMED</Badge>
          <Badge variant={status?.order_submission_allowed ? "warning" : "secondary"}>
            orders {status?.order_submission_allowed ? "armed" : "blocked"}
          </Badge>
          <Badge variant="outline">
            testnet env {String(status?.bybit_testnet_env ?? "—")}
          </Badge>
          <Badge variant="outline">
            linear auto {String(status?.linear_auto_exec_allowed ?? false)}
          </Badge>
          <Badge variant="danger">mainnet path {String(status?.mainnet_execution_path_exists)}</Badge>
        </div>
        {error ? <p className="text-amber-300">{error}</p> : null}
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4 font-mono text-xs">
          <div>Pending/accepted {String(local.pending_or_accepted ?? 0)}</div>
          <div>Ack≠fill {String(local.ack_is_not_fill ?? true)}</div>
          <div>Supabase exec writes {String(status?.supabase_execution_writes ?? false)}</div>
          <div>Private WS {String(status?.private_ws ?? "n/a")}</div>
        </div>
        <p className="text-xs text-muted-foreground">
          {String(status?.note ?? "")}
        </p>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" disabled title="HTTP arm refused by design">
            Arm Testnet (disabled)
          </Button>
          <Button size="sm" variant="outline" disabled title="Requires approved live path">
            Submit order (disabled)
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
