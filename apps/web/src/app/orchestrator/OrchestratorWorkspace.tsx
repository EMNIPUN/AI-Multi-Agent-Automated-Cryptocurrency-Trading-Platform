"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  Briefcase,
  ChartCandlestick,
  MessageSquarePlus,
  PanelRight,
  Newspaper,
  Shield,
  Sparkles,
  TrendingUp,
  Wallet,
  Zap,
} from "lucide-react";

import {
  AgentStatusList,
  SectionPanel,
} from "@/components/command-center";
import { AiWorkspaceTemplate } from "@/components/design-system/templates";
import { StatusBadge } from "@/components/design-system";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";

import {
  OrchestratorCommandChat,
  type ChatTurn,
} from "./OrchestratorCommandChat";
import {
  OrchestratorStatusStrip,
  type ChatExecutionMode,
} from "./OrchestratorStatusStrip";

type AnyRow = Record<string, unknown>;

const CONV_KEY = "cryptonova.orchestrator.conversation_id";

const AGENTS = [
  { name: "Market Data", icon: ChartCandlestick },
  { name: "Technical Analysis", icon: Activity },
  { name: "Strategy", icon: Sparkles },
  { name: "News", icon: Newspaper },
  { name: "Portfolio", icon: Wallet },
  { name: "Risk", icon: Shield },
  { name: "Execution", icon: Zap },
  { name: "Performance", icon: TrendingUp },
  { name: "Reliability", icon: Briefcase },
];

const HALT_MESSAGE = "Emergency halt.";

async function readJson(path: string, init?: RequestInit) {
  const res = await fetch(path, { cache: "no-store", ...init });
  const body = (await res.json().catch(() => ({}))) as AnyRow;
  return { res, body };
}

function newTurn(
  role: ChatTurn["role"],
  text: string,
  payload?: ChatTurn["payload"],
  meta?: ChatTurn["meta"],
): ChatTurn {
  return {
    id: `${role}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    role,
    text,
    at: Date.now(),
    payload,
    meta,
  };
}

function payloadFromBody(body: AnyRow): ChatTurn["payload"] {
  const calls = body.tool_calls;
  const last =
    Array.isArray(calls) && calls.length > 0 ? (calls[calls.length - 1] as AnyRow) : null;
  const result = last?.result;
  const base = result && typeof result === "object" ? { ...(result as AnyRow) } : {};
  return {
    ...base,
    execution_mode: body.execution_mode ?? base.execution_mode,
    preferred_mode: body.preferred_mode ?? base.preferred_mode,
    live_orders: body.live_orders ?? base.live_orders,
    live_env_armed: body.live_env_armed ?? base.live_env_armed,
    exchange_order_sent: body.exchange_order_sent ?? base.exchange_order_sent,
  };
}

function toolNamesFromBody(body: AnyRow): string[] {
  const calls = body.tool_calls;
  if (!Array.isArray(calls)) return [];
  return calls
    .map((c) => (c && typeof c === "object" ? String((c as AnyRow).name || "") : ""))
    .filter(Boolean);
}

export function OrchestratorWorkspace() {
  const [status, setStatus] = useState<AnyRow | null>(null);
  const [report, setReport] = useState<AnyRow | null>(null);
  const [diagnostics, setDiagnostics] = useState<AnyRow | null>(null);
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [sending, setSending] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [lastTools, setLastTools] = useState<string[]>([]);
  const [lastOpenAi, setLastOpenAi] = useState<boolean | null>(null);
  const [lastModel, setLastModel] = useState<string | null>(null);
  const [lastMode, setLastMode] = useState<string | null>(null);
  const [chatMode, setChatMode] = useState<ChatExecutionMode>("PAPER");

  const load = useCallback(async (soft = false) => {
    if (soft) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const [st, rp, diag] = await Promise.all([
        readJson("/api/orchestrator/status"),
        readJson("/api/orchestrator/report"),
        readJson("/api/orchestrator/diagnostics"),
      ]);
      setStatus(st.body);
      setReport(rp.body);
      setDiagnostics(diag.res.ok ? diag.body : null);
      if (!st.res.ok) setError("Orchestrator status unavailable");
    } catch {
      setError("Orchestrator unreachable");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(CONV_KEY);
      if (saved) setConversationId(saved);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (!conversationId) return;
    let cancelled = false;
    void (async () => {
      try {
        const { res, body } = await readJson(
          `/api/orchestrator/conversations/${encodeURIComponent(conversationId)}`,
        );
        if (cancelled || !res.ok) return;
        const messages = Array.isArray(body.messages) ? body.messages : [];
        if (messages.length === 0) return;
        setTurns(
          messages.map((m: AnyRow, i: number) =>
            newTurn(
              m.role === "user" ? "user" : "assistant",
              String(m.content || ""),
              undefined,
              undefined,
            ),
          ).map((t, i) => ({ ...t, id: `hist-${i}-${t.at}` })),
        );
      } catch {
        /* history optional */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  const supervisorState = String(status?.state || "STOPPED").toUpperCase();
  const supervisorOn = Boolean(status?.enabled);
  const openPositions = Number(report?.open_positions ?? status?.open_positions ?? 0) || 0;
  const equityRaw = report?.equity;
  const equityNum =
    equityRaw == null || equityRaw === "" || equityRaw === "—"
      ? null
      : Number(equityRaw);
  const currency = String(report?.currency || "USDT");
  const auth =
    status?.authorization && typeof status.authorization === "object"
      ? (status.authorization as AnyRow)
      : null;
  const symbol = String(auth?.symbol || "HYPEUSDT");
  const liveArmed = Boolean(status?.live_mutate_allowed ?? status?.live_unlocked);
  const pageModes = ["paper"] as const;
  const openai = (diagnostics?.openai as AnyRow | undefined) || null;
  const inspector =
    (status?.decision_inspector as AnyRow | undefined) ||
    (diagnostics?.latest_decision as AnyRow | undefined) ||
    null;

  async function newConversation() {
    const prev = conversationId;
    setTurns([]);
    setLastTools([]);
    setLastOpenAi(null);
    setLastModel(null);
    setLastMode(null);
    setError(null);
    setConversationId(null);
    try {
      window.localStorage.removeItem(CONV_KEY);
    } catch {
      /* ignore */
    }
    if (prev) {
      try {
        await readJson(`/api/orchestrator/conversations/${encodeURIComponent(prev)}/reset`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: "{}",
        });
      } catch {
        /* reset best-effort */
      }
    }
  }

  async function sendMessage(text: string) {
    const trimmed = text.trim();
    if (!trimmed || sending) return;
    setSending(true);
    setError(null);
    setTurns((prev) => [...prev, newTurn("user", trimmed)]);
    try {
      const result = await readJson("/api/orchestrator/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: trimmed,
          execution_mode: chatMode,
          conversation_id: conversationId || undefined,
        }),
      });
      if (!result.res.ok) {
        const detail = String(result.body.detail || result.body.error || "Chat request failed");
        setError(detail);
        setTurns((prev) => [
          ...prev,
          newTurn(
            "assistant",
            `Request failed (${result.res.status}): ${detail}. Check that the API is running and try again.`,
          ),
        ]);
        return;
      }
      const nextCid = result.body.conversation_id
        ? String(result.body.conversation_id)
        : conversationId;
      if (nextCid && nextCid !== conversationId) {
        setConversationId(nextCid);
        try {
          window.localStorage.setItem(CONV_KEY, nextCid);
        } catch {
          /* ignore */
        }
      }
      const replyRaw =
        result.body.reply ??
        result.body.message ??
        result.body.response ??
        result.body.text ??
        "";
      const reply =
        String(replyRaw).trim() ||
        "Orchestrator returned an empty reply. Status may still have updated — check the strip above.";
      const tools = toolNamesFromBody(result.body);
      const openaiCalled = Boolean(result.body.openai_called);
      const modelName = result.body.model ? String(result.body.model) : null;
      const orchMode = result.body.orchestration_mode
        ? String(result.body.orchestration_mode)
        : null;
      setLastTools(tools);
      setLastOpenAi(openaiCalled);
      setLastModel(modelName);
      setLastMode(orchMode);
      const liveTools = new Set([
        "start_futures_intake",
        "continue_futures_intake",
        "propose_live_trade",
        "propose_live_close",
        "propose_live_cancel_orders",
        "approve_live_trade",
        "reject_live_trade",
        "list_live_positions",
      ]);
      if (
        result.body.execution_mode === "LIVE" ||
        result.body.live_orders === true ||
        tools.some((name) => liveTools.has(name))
      ) {
        setChatMode("LIVE");
      }
      setTurns((prev) => [
        ...prev,
        newTurn("assistant", reply, payloadFromBody(result.body), {
          toolNames: tools,
          openaiCalled,
          error: result.body.error ? String(result.body.error) : null,
          model: modelName,
          orchestrationMode: orchMode,
          usedFallback: Boolean(result.body.used_fallback),
        }),
      ]);
      void load(true);
    } catch {
      setError("Chat request failed");
      setTurns((prev) => [
        ...prev,
        newTurn(
          "assistant",
          "Chat request failed. Orchestrator API may be unreachable — start the backend and refresh.",
        ),
      ]);
    } finally {
      setSending(false);
    }
  }

  if (loading) {
    return (
      <AiWorkspaceTemplate title="Orchestrator" modes={[...pageModes]}>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Spinner className="size-4" />
          Connecting…
        </div>
        <Skeleton className="h-12 w-full rounded-2xl" />
        <Skeleton className="h-[28rem] w-full rounded-3xl" />
      </AiWorkspaceTemplate>
    );
  }

  const leftRail = (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <Button
        type="button"
        variant="outline"
        className="w-full justify-start gap-2 rounded-xl"
        onClick={() => void newConversation()}
      >
        <MessageSquarePlus className="h-4 w-4" />
        New conversation
      </Button>
      <div className="cn-panel flex min-h-0 flex-1 flex-col p-3">
        <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          Session
        </p>
        <p className="mt-2 text-sm font-medium text-foreground">
          {conversationId ? "Server-backed thread" : "Current chat"}
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          {conversationId
            ? `${turns.length} message${turns.length === 1 ? "" : "s"} · ${conversationId.slice(0, 12)}…`
            : turns.length === 0
              ? "No messages yet — history persists after the first reply."
              : `${turns.length} message${turns.length === 1 ? "" : "s"} in this browser session.`}
        </p>
        <div className="mt-3 flex flex-wrap gap-1.5">
          <StatusBadge
            label={chatMode}
            tone={chatMode === "LIVE" ? "danger" : "paper"}
          />
          <StatusBadge label={supervisorState} tone={supervisorState === "RUNNING" ? "ok" : "neutral"} />
        </div>
      </div>
    </div>
  );

  const paperRail = (
    <>
      <SectionPanel title="Paper session" description="Simulated supervisor journal — not exchange equity.">
        <dl className="space-y-2 text-sm">
          {[
            ["Symbol", symbol],
            ["Supervisor", `${supervisorState}${supervisorOn ? " · on" : " · off"}`],
            ["Open positions", String(openPositions)],
            ["Equity", equityNum != null ? `${equityNum} ${currency}` : `— ${currency}`],
            ["Per-trade Approve", "Not required (session-authorized)"],
          ].map(([label, value]) => (
            <div
              key={label}
              className="flex items-center justify-between gap-3 rounded-xl border border-border bg-muted/50 px-3 py-2"
            >
              <dt className="text-muted-foreground">{label}</dt>
              <dd className="max-w-[12rem] text-right font-mono text-xs text-foreground">{value}</dd>
            </div>
          ))}
        </dl>
      </SectionPanel>

      <SectionPanel
        title="Decision inspector"
        description="Verified supervisor decision fields only — not model speculation."
      >
        {inspector ? (
          <dl className="space-y-2 text-sm">
            {[
              ["Action", String(inspector.action ?? "—")],
              ["Strategy", String(inspector.strategy ?? "—")],
              ["Risk", String(inspector.risk_verdict ?? inspector.risk ?? "—")],
              [
                "Blockers",
                Array.isArray(inspector.blockers)
                  ? (inspector.blockers as unknown[]).map(String).join(", ") || "none"
                  : String(inspector.blockers ?? "—"),
              ],
              ["Freshness", String(inspector.freshness ?? "—")],
            ].map(([label, value]) => (
              <div
                key={label}
                className="flex items-center justify-between gap-3 rounded-xl border border-border bg-muted/50 px-3 py-2"
              >
                <dt className="text-muted-foreground">{label}</dt>
                <dd className="max-w-[12rem] text-right font-mono text-xs text-foreground">{value}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <p className="text-xs text-muted-foreground">
            No latest decision yet — start paper trading or ask “Explain the last trading decision.”
          </p>
        )}
      </SectionPanel>

      <SectionPanel
        title="Paper performance"
        description="Journal figures only — exchange equity is not included."
      >
        <dl className="space-y-2 text-sm">
          {[
            ["Realized PnL", String(report?.realized_pnl || "0")],
            ["Fees", String(report?.fees_paid || "0")],
            ["Drawdown", String(report?.drawdown || "0")],
          ].map(([label, value]) => (
            <div
              key={label}
              className="flex items-center justify-between gap-3 rounded-xl border border-border bg-muted/50 px-3 py-2"
            >
              <dt className="text-muted-foreground">{label}</dt>
              <dd className="font-mono text-foreground">{value}</dd>
            </div>
          ))}
        </dl>
      </SectionPanel>
    </>
  );

  const liveRail = (
    <>
      <SectionPanel
        title="Live Bybit"
        description="MAINNET path via Orchestrator Approve — switch does not skip approval."
      >
        <dl className="space-y-2 text-sm">
          {[
            ["Chat mode", "LIVE"],
            ["Symbol", symbol],
            ["Env armed", liveArmed ? "Yes" : "No — set AGENT_ALLOW_LIVE + MAINNET_TRADING_ENABLED"],
            ["Bybit mainnet", status?.bybit_mainnet ? "Yes" : "Check BYBIT_TESTNET/DEMO"],
            ["Per-order Approve", "Required"],
          ].map(([label, value]) => (
            <div
              key={label}
              className="flex items-center justify-between gap-3 rounded-xl border border-border bg-muted/50 px-3 py-2"
            >
              <dt className="text-muted-foreground">{label}</dt>
              <dd className="max-w-[12rem] text-right font-mono text-xs text-foreground">{value}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-3 text-[11px] leading-relaxed text-muted-foreground">
          Opens use futures intake (side, Market/Limit, qty, leverage, SL/TP). Closes and cancels
          still need Approve. If Bybit returns 10029, add the symbol to the API-key whitelist.
        </p>
      </SectionPanel>

      <SectionPanel title="Live shortcuts" description="Send from chat while LIVE is selected.">
        <ul className="space-y-1.5 text-xs text-muted-foreground">
          <li>Place futures order HYPEUSDT</li>
          <li>Close current HYPEUSDT position on Bybit</li>
          <li>Show Bybit position for HYPEUSDT</li>
          <li>Approve live trade</li>
        </ul>
      </SectionPanel>
    </>
  );

  const rightRail = (
    <div className="flex min-w-0 flex-col gap-3">
      {chatMode === "LIVE" ? liveRail : paperRail}

      <SectionPanel title="Model & spend" description="Ledger-backed usage — no fabricated costs.">
        <dl className="space-y-2 text-sm">
          {[
            ["Last path", lastMode || (lastOpenAi == null ? "—" : lastOpenAi ? "openai" : "deterministic")],
            ["Model", lastModel || String(openai?.model || "—")],
            ["Spent 24h", `$${Number(openai?.spent_usd_24h ?? 0).toFixed(4)}`],
            [
              "Remaining 24h",
              openai?.remaining_usd_24h != null
                ? `$${Number(openai.remaining_usd_24h).toFixed(4)}`
                : "—",
            ],
            ["Total envelope", `$${Number(openai?.spent_usd_total ?? 0).toFixed(4)}`],
          ].map(([label, value]) => (
            <div
              key={label}
              className="flex items-center justify-between gap-3 rounded-xl border border-border bg-muted/50 px-3 py-2"
            >
              <dt className="text-muted-foreground">{label}</dt>
              <dd className="font-mono text-xs text-foreground">{value}</dd>
            </div>
          ))}
        </dl>
      </SectionPanel>

      <SectionPanel title="Last tool trace" description="Only tools returned by the chat API.">
        {lastTools.length === 0 ? (
          <p className="text-xs text-muted-foreground">No tool calls in this session yet.</p>
        ) : (
          <ul className="space-y-1.5">
            {lastTools.map((name) => (
              <li
                key={name}
                className="flex items-center justify-between rounded-lg border border-border bg-muted/40 px-2.5 py-1.5 text-xs"
              >
                <span className="font-mono text-foreground">{name}</span>
                <StatusBadge label="Completed" tone="ok" />
              </li>
            ))}
          </ul>
        )}
        {lastOpenAi != null ? (
          <p className="mt-2 text-[11px] text-muted-foreground">
            Model path:{" "}
            {lastOpenAi
              ? `OpenAI${lastModel ? ` (${lastModel})` : ""}`
              : "Local / deterministic planner"}
          </p>
        ) : null}
      </SectionPanel>

      <SectionPanel
        title="Agents"
        description="Status mirrors the supervisor — no invented heartbeats."
      >
        <AgentStatusList
          agents={AGENTS.map((a) => ({
            name: a.name,
            state: supervisorState,
            icon: a.icon,
          }))}
        />
      </SectionPanel>
    </div>
  );

  return (
    <AiWorkspaceTemplate
      title="Orchestrator"
      modes={[...pageModes, "readonly"]}
      className="flex h-full min-h-0 flex-1 flex-col gap-2 space-y-0 overflow-hidden pb-0"
    >
      {error ? (
        <div className="shrink-0 rounded-2xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <div className="shrink-0">
        <OrchestratorStatusStrip
          chatMode={chatMode}
          liveArmed={liveArmed}
          supervisorState={supervisorState}
          supervisorOn={supervisorOn}
          equityNum={equityNum}
          currency={currency}
          openPositions={openPositions}
          refreshing={refreshing}
          sending={sending}
          onRefresh={() => void load(true)}
          onHalt={() => void sendMessage(HALT_MESSAGE)}
        />
      </div>

      <div className="grid min-h-0 min-w-0 flex-1 gap-3 overflow-hidden [grid-template-rows:minmax(0,1fr)] lg:grid-cols-[12rem_minmax(0,1fr)] xl:grid-cols-[12rem_minmax(0,1fr)_minmax(16rem,18rem)]">
        <div className="hidden min-h-0 lg:block">{leftRail}</div>

        <div className="flex h-full min-h-0 min-w-0 flex-col">
          <div className="mb-2 flex shrink-0 gap-2 xl:hidden">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="rounded-full lg:hidden"
              onClick={() => void newConversation()}
            >
              New chat
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="rounded-full"
              onClick={() => setInspectorOpen(true)}
            >
              <PanelRight className="mr-1.5 h-3.5 w-3.5" />
              Context
            </Button>
          </div>
          <OrchestratorCommandChat
            sending={sending}
            turns={turns}
            chatMode={chatMode}
            onChatModeChange={setChatMode}
            onSend={sendMessage}
          />
        </div>

        <div className="hidden min-h-0 min-w-0 overflow-y-auto cn-thin-scroll xl:block">
          {rightRail}
        </div>
      </div>
      <Sheet open={inspectorOpen} onOpenChange={setInspectorOpen}>
        <SheetContent side="right" className="w-[min(100%,24rem)] overflow-y-auto sm:max-w-md">
          <SheetHeader className="pr-8">
            <SheetTitle>Session context</SheetTitle>
            <SheetDescription>Supervisor, risk, and the last real tool trace.</SheetDescription>
          </SheetHeader>
          <div className="mt-4">{rightRail}</div>
        </SheetContent>
      </Sheet>
    </AiWorkspaceTemplate>
  );
}
