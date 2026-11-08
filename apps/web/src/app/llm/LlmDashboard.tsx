"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  LLM_ADVISORY_LABEL,
  llmStateCopy,
  llmViewState,
  type LlmViewState,
} from "@/lib/llm/llm-format";

type AnyRow = Record<string, unknown>;

async function readJson(path: string) {
  const res = await fetch(path, { cache: "no-store" });
  const body = (await res.json().catch(() => ({}))) as AnyRow;
  return { ok: res.ok, body };
}

export function LlmDashboard() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [status, setStatus] = useState<AnyRow | null>(null);
  const [items, setItems] = useState<AnyRow[]>([]);
  const [report, setReport] = useState<AnyRow | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [statusRes, listRes, reportRes] = await Promise.all([
          readJson("/api/llm/status"),
          readJson("/api/llm/evaluations"),
          readJson("/api/llm/report"),
        ]);
        if (cancelled) return;
        if (!statusRes.ok) {
          setError(true);
          return;
        }
        setStatus(statusRes.body);
        setItems(Array.isArray(listRes.body.items) ? (listRes.body.items as AnyRow[]) : []);
        setReport(reportRes.ok ? reportRes.body : null);
      } catch {
        if (!cancelled) setError(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const enabled = status?.enabled === true;
  const state: LlmViewState = llmViewState({
    loading,
    enabled,
    apiKeyConfigured: status?.api_key_configured === true,
    modelConfigured: status?.model_configured === true,
    error,
    budgetExhausted: false,
    count: items.length,
  });

  return (
    <div className="space-y-4 p-4 md:p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">LLM Intelligence</h1>
        <p className="text-sm text-muted-foreground">{LLM_ADVISORY_LABEL}</p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Status</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <Badge variant="secondary">{llmStateCopy(state)}</Badge>
          <p>Provider: {String(status?.provider ?? "none")}</p>
          <p>Model: {String(status?.model ?? "not configured")}</p>
          <p>Storage: {String(status?.storage_kind ?? "unknown")}</p>
          <p>
            Estimated spend today:{" "}
            {String((status?.budget as AnyRow | undefined)?.estimated_spend_today_usd ?? "—")}
          </p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Comparison report</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          {report ? (
            <p>
              Evaluations {String(report.evaluations ?? 0)}. Agreement rate{" "}
              {String(report.agreement_rate ?? "—")}. {String(report.note ?? "")}
            </p>
          ) : (
            <p>No comparison report is available.</p>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Audit history</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          {items.length === 0 ? <p>{llmStateCopy(state === "ready" ? "empty" : state)}</p> : null}
          {items.map((row) => (
            <div key={String(row.evaluation_id)} className="rounded-md border p-3">
              <p className="font-medium">
                {String(row.symbol)} {String(row.interval)} · technical {String(row.coordinator_action)} ·
                suggested {String(row.suggested_action ?? "none")} · {String(row.agreement)}
              </p>
              <p className="text-muted-foreground">{String(row.reason ?? "")}</p>
              <p>Uncertainty: {String(row.uncertainty ?? "UNKNOWN")}</p>
              <p>Evidence: {(row.evidence_event_ids as string[] | undefined)?.join(", ") || "none"}</p>
              <p>llm_changed_decision=false</p>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
