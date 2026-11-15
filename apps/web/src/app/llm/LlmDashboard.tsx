"use client";

import { SectionPanel } from "@/components/command-center";
import { DataTable, ErrorState, FinancialValue, MetricCard, MetricCardGrid, StatusBadge, StatusIndicator, type DataTableColumn } from "@/components/design-system";
import { Skeleton } from "@/components/ui/skeleton";
import { usePolledResource } from "@/hooks/use-polled-resource";
import { getJson } from "@/lib/api/client";
import { formatDateTime } from "@/lib/formatting/time";
import { LLM_ADVISORY_LABEL, llmStateCopy, llmViewState } from "@/lib/llm/llm-format";

type LlmStatus = {
  enabled: boolean;
  model_configured: boolean;
  api_key_configured: boolean;
  model: string | null;
  provider: string | null;
  timeout_seconds: number;
  max_calls_per_hour: number;
  daily_budget_usd: number;
  storage_kind: string;
  storage_available: boolean;
  automatic_calls: boolean;
  provider_called: boolean;
  budget: { calls_this_hour: number; estimated_spend_today_usd: number; daily_budget_usd: number; remaining_usd: number; storage: string };
};

type LlmEvaluation = {
  evaluation_id: string;
  symbol: string;
  interval: string;
  coordinator_action: string;
  suggested_action: string | null;
  agreement: string;
  reason: string | null;
  uncertainty: string | null;
  evidence_event_ids?: string[];
  created_ms?: number;
  model?: string | null;
  latency_ms?: number | null;
};

type LlmReport = {
  evaluations: number;
  agreement_rate: number | null;
  disagreement_rate: number | null;
  abstention_rate: number | null;
  error_rate: number | null;
  average_latency_ms: number | null;
  prompt_tokens: number;
  completion_tokens: number;
  estimated_cost_usd: number;
  note: string;
};

function rate(v: number | null | undefined): string {
  return v == null ? "—" : `${(v * 100).toFixed(1)}%`;
}

const COLUMNS: DataTableColumn<LlmEvaluation>[] = [
  { id: "when", header: "When", cell: (r) => <span className="text-muted-foreground">{formatDateTime(r.created_ms)}</span>, accessor: (r) => r.created_ms ?? 0 },
  { id: "symbol", header: "Symbol", cell: (r) => <span className="font-medium text-foreground">{r.symbol} · {r.interval}</span>, accessor: (r) => `${r.symbol} ${r.interval}` },
  { id: "deterministic", header: "Deterministic decision", cell: (r) => <StatusIndicator status={r.coordinator_action === "BUY" || r.coordinator_action === "SELL" ? "OK" : r.coordinator_action} label={r.coordinator_action} />, accessor: (r) => r.coordinator_action },
  { id: "suggested", header: "Model suggestion", cell: (r) => <span className="font-mono">{r.suggested_action ?? "none"}</span>, accessor: (r) => r.suggested_action ?? "" },
  { id: "agreement", header: "Agreement", cell: (r) => <StatusBadge label={r.agreement} tone={r.agreement === "AGREE" ? "ok" : r.agreement === "DISAGREE" ? "warn" : "neutral"} />, accessor: (r) => r.agreement },
  { id: "uncertainty", header: "Uncertainty", cell: (r) => <span className="font-mono">{r.uncertainty ?? "UNKNOWN"}</span>, hideBelow: "md" },
  { id: "reason", header: "Commentary", cell: (r) => <span className="block max-w-[28rem] truncate text-muted-foreground" title={r.reason ?? ""}>{r.reason ?? "—"}</span>, hideBelow: "lg", enableSorting: false },
  { id: "evidence", header: "Evidence", cell: (r) => <span className="font-mono text-muted-foreground">{r.evidence_event_ids?.length ?? 0} ids</span>, accessor: (r) => r.evidence_event_ids?.length ?? 0, hideBelow: "xl" },
];

export function LlmDashboard() {
  const status = usePolledResource((init) => getJson<LlmStatus>("/api/llm/status", init), { intervalMs: 60_000 });
  const evaluations = usePolledResource((init) => getJson<{ items: LlmEvaluation[] }>("/api/llm/evaluations", init), { intervalMs: 60_000 });
  const report = usePolledResource((init) => getJson<LlmReport>("/api/llm/report", init), { intervalMs: 60_000 });

  const st = status.data;
  const items = evaluations.data?.items ?? [];
  const state = llmViewState({
    loading: status.loading,
    enabled: Boolean(st?.enabled),
    apiKeyConfigured: Boolean(st?.api_key_configured),
    modelConfigured: Boolean(st?.model_configured),
    error: Boolean(status.error && !st),
    budgetExhausted: Boolean(st && st.budget.remaining_usd <= 0),
    count: items.length,
  });

  return (
    <div className="space-y-4">
      {status.error && !st ? <ErrorState title="LLM status unavailable" code={status.error.code} at={status.error.at} onRetry={() => void status.refresh()} /> : null}

      <div className="flex flex-wrap items-center gap-2">
        <StatusIndicator status={status.loading ? "UNKNOWN" : st?.enabled ? (st.model_configured ? "RUNNING" : "PAUSED") : "STOPPED"} label={status.loading ? "Checking" : st?.enabled ? (st.model_configured ? "Advisory model enabled" : "Enabled · no model configured") : "Advisory model off"} />
        <StatusBadge label={LLM_ADVISORY_LABEL} tone="neutral" />
        <StatusBadge label="llm_changed_decision = false" tone="neutral" />
      </div>
      <p className="text-sm text-muted-foreground">{llmStateCopy(state)}</p>

      <MetricCardGrid>
        <MetricCard label="Provider / model" loading={status.loading} value={<span className="font-mono text-base">{st?.provider ?? "none"} · {st?.model ?? "not configured"}</span>} hint={st ? `storage ${st.storage_kind} · ${st.storage_available ? "available" : "unavailable"}` : undefined} />
        <MetricCard label="Spend today" loading={status.loading} value={<FinancialValue value={st?.budget.estimated_spend_today_usd} digits={4} unit="USD" size="md" />} hint={st ? `budget $${st.budget.daily_budget_usd.toFixed(2)} · remaining $${st.budget.remaining_usd.toFixed(4)}` : undefined} />
        <MetricCard label="Calls this hour" loading={status.loading} value={<span className="font-mono">{st?.budget.calls_this_hour ?? "—"}</span>} hint={st ? `cap ${st.max_calls_per_hour}/h · timeout ${st.timeout_seconds}s` : undefined} />
        <MetricCard label="Stored evaluations" loading={evaluations.loading} value={<span className="font-mono">{report.data?.evaluations ?? items.length}</span>} hint={report.data ? `agreement ${rate(report.data.agreement_rate)} · disagreement ${rate(report.data.disagreement_rate)}` : undefined} />
      </MetricCardGrid>

      <SectionPanel title="Comparison report" description="Model commentary measured against the deterministic decision. Agreement is not evidence of profitability.">
        {report.loading ? (
          <Skeleton className="h-16 w-full rounded-xl" />
        ) : report.data ? (
          <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 text-sm">
            {[
              ["Abstention rate", rate(report.data.abstention_rate)],
              ["Error rate", rate(report.data.error_rate)],
              ["Avg latency", report.data.average_latency_ms != null ? `${Math.round(report.data.average_latency_ms)} ms` : "—"],
              ["Tokens", `${report.data.prompt_tokens} in · ${report.data.completion_tokens} out`],
            ].map(([k, v]) => (
              <div key={k} className="rounded-xl border border-border bg-muted/40 px-3 py-2">
                <dt className="text-[11px] uppercase tracking-wide text-muted-foreground">{k}</dt>
                <dd className="mt-0.5 font-mono text-xs text-foreground">{v}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <p className="text-sm text-muted-foreground">No comparison report is available.</p>
        )}
        {report.data?.note ? <p className="mt-3 text-xs text-muted-foreground">{report.data.note}</p> : null}
      </SectionPanel>

      <SectionPanel title="Evaluation audit history" description="Each row pairs the deterministic decision with the model's advisory suggestion and the evidence ids it cited.">
        {evaluations.loading ? (
          <Skeleton className="h-40 w-full rounded-xl" />
        ) : (
          <DataTable
            rows={items}
            columns={COLUMNS}
            rowKey={(r) => r.evaluation_id}
            caption="LLM advisory evaluations"
            initialSort={{ id: "when", desc: true }}
            emptyState={llmStateCopy(state === "ready" ? "empty" : state)}
            pageSize={15}
          />
        )}
      </SectionPanel>
    </div>
  );
}
