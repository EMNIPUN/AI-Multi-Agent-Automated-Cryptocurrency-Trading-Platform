"use client";

import * as React from "react";
import {
  AlertTriangle,
  CheckCircle2,
  CircleAlertIcon,
  CirclePause,
  Info,
  Radio,
  TerminalIcon,
  Wrench,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemMedia,
  ItemTitle,
} from "@/components/ui/item";
import {
  Trace,
  TraceCollapsible,
  TraceCollapsibleContent,
  TraceCollapsibleTrigger,
  TraceIcon,
  TraceLine,
  TraceTitle,
} from "@/components/ui/trace";
import { cn } from "@/lib/utils";

export type ReplyPayload = Record<string, unknown> | null | undefined;

type ParsedReply = {
  headline: string;
  chips: { label: string; tone: "ok" | "warn" | "muted" | "danger" }[];
  facts: { label: string; value: string }[];
  bullets: string[];
  paragraphs: string[];
  note: string | null;
};

const DISCLAIMER_RE =
  /does not authorize|live (orders?|trading|bybit)|exchange order|testnet stay|mainnet|approve required|every live/i;

function toneClass(tone: ParsedReply["chips"][number]["tone"]) {
  switch (tone) {
    case "ok":
      return "border-profit/40 bg-profit/10 text-foreground";
    case "warn":
      return "border-brand/40 bg-brand/10 text-foreground";
    case "danger":
      return "border-destructive/40 bg-destructive/10 text-destructive";
    default:
      return "border-border bg-muted text-muted-foreground";
  }
}

function stateTone(state: string): ParsedReply["chips"][number]["tone"] {
  const s = state.toUpperCase();
  if (s === "RUNNING") return "ok";
  if (s === "PAUSED" || s === "HALTED") return "warn";
  if (s === "STOPPED" || s === "ERROR") return "danger";
  return "muted";
}

function parseFromText(text: string, payload?: ReplyPayload): ParsedReply {
  const lines = text
    .split(/\n+/)
    .map((l) => l.replace(/^[-•*]\s+/, "").trim())
    .filter(Boolean);

  const notes: string[] = [];
  const bodyLines: string[] = [];
  for (const line of lines) {
    if (DISCLAIMER_RE.test(line)) notes.push(line);
    else bodyLines.push(line);
  }

  const chips: ParsedReply["chips"] = [];
  const facts: ParsedReply["facts"] = [];
  const bullets: string[] = [];
  const paragraphs: string[] = [];

  const state = String(payload?.state || "").toUpperCase();
  if (state) {
    chips.push({ label: state, tone: stateTone(state) });
  } else {
    const m = text.match(/Supervisor is\s+([A-Z_]+)/i);
    if (m?.[1]) chips.push({ label: m[1].toUpperCase(), tone: stateTone(m[1]) });
  }

  if (payload?.enabled === true || /feature is on|supervisor feature is on/i.test(text)) {
    chips.push({ label: "Supervisor on", tone: "ok" });
  } else if (payload?.enabled === false || /feature is off|supervisor is disabled/i.test(text)) {
    chips.push({ label: "Supervisor off", tone: "muted" });
  }

  const mode = String(payload?.execution_mode || "").toUpperCase();
  if (mode === "LIVE" || payload?.live_orders === true) {
    chips.push({ label: "LIVE MAINNET", tone: "danger" });
    chips.push({ label: "Approve/order", tone: "warn" });
  } else {
    chips.push({ label: "PAPER", tone: "warn" });
  }

  if (payload?.equity != null && payload.equity !== "" && payload.equity !== "—") {
    facts.push({
      label: "Equity",
      value: `${payload.equity} ${String(payload.currency || "USDT")}`,
    });
  }
  if (payload?.open_positions != null) {
    facts.push({ label: "Open", value: String(payload.open_positions) });
  }
  if (payload?.realized_pnl != null) {
    facts.push({ label: "Realized PnL", value: String(payload.realized_pnl) });
  }
  if (payload?.analysis_action) {
    facts.push({ label: "Decision", value: String(payload.analysis_action) });
  }
  if (payload?.side) facts.push({ label: "Side", value: String(payload.side) });
  if (payload?.entry != null && payload.entry !== "") {
    facts.push({ label: "Entry", value: String(payload.entry) });
  }
  if (payload?.stop_loss != null && payload.stop_loss !== "") {
    facts.push({ label: "Stop Loss", value: String(payload.stop_loss) });
  }
  if (payload?.take_profit != null && payload.take_profit !== "") {
    facts.push({ label: "Take Profit", value: String(payload.take_profit) });
  }
  if (payload?.proposal_id != null && String(payload.proposal_id).trim()) {
    facts.push({ label: "Proposal", value: String(payload.proposal_id) });
  }
  if (payload?.qty != null && String(payload.qty).trim()) {
    facts.push({ label: "Qty", value: String(payload.qty) });
  }
  if (payload?.leverage != null && String(payload.leverage).trim()) {
    facts.push({ label: "Leverage", value: String(payload.leverage) });
  }
  if (payload?.order_type != null && String(payload.order_type).trim()) {
    facts.push({ label: "Order type", value: String(payload.order_type) });
  }

  const headline = bodyLines[0] || String(payload?.summary || "Orchestrator update").split("\n")[0];
  for (const line of bodyLines.slice(1)) {
    if (line.length < 90 && !/[.!?]$/.test(line) && /:/.test(line)) {
      const [label, ...rest] = line.split(":");
      if (label && rest.length) {
        facts.push({ label: label.trim(), value: rest.join(":").trim() });
        continue;
      }
    }
    if (line.length < 120) bullets.push(line);
    else paragraphs.push(line);
  }

  const uniqueFacts = facts.filter(
    (f, i, arr) => arr.findIndex((x) => x.label === f.label && x.value === f.value) === i,
  );

  return {
    headline,
    chips: chips.slice(0, 5),
    facts: uniqueFacts.slice(0, 10),
    bullets: bullets.slice(0, 12),
    paragraphs: paragraphs.slice(0, 6),
    note: notes[0] || null,
  };
}

function ReplyIcon({ headline }: { headline: string }) {
  if (/halt|emergency|blocked|failed|refused|error/i.test(headline)) {
    return <AlertTriangle className="h-4 w-4 text-destructive" aria-hidden />;
  }
  if (/pause|paused|stopped|disabled|off\b/i.test(headline)) {
    return <CirclePause className="h-4 w-4 text-brand" aria-hidden />;
  }
  if (/started|running|resumed|approved|ok\b/i.test(headline)) {
    return <CheckCircle2 className="h-4 w-4 text-profit" aria-hidden />;
  }
  return <Info className="h-4 w-4 text-muted-foreground" aria-hidden />;
}

const TOOL_LABELS: Record<string, string> = {
  supervisor_status: "Checked session status",
  analyze_symbol: "Analyzed the market",
  paper_report: "Loaded paper performance",
  supervisor_command: "Updated the supervisor",
  openai_usage: "Checked OpenAI usage",
  live_readiness: "Checked live readiness",
  hype_feasibility: "Checked risk feasibility",
  run_full_analysis: "Ran full multi-agent analysis",
  agent_status: "Checked agents",
  get_market_price: "Fetched market price",
  list_market_quotes: "Listed available quotes",
  propose_paper_trade: "Prepared a paper trade",
  approve_paper_trade: "Approved a paper trade",
  reject_paper_trade: "Rejected a paper trade",
  propose_live_trade: "Prepared a live trade",
  approve_live_trade: "Sent an approved live order",
  reject_live_trade: "Rejected a live proposal",
  propose_live_close: "Prepared a live close",
  propose_live_cancel_orders: "Prepared an order cancel",
  list_live_positions: "Checked Bybit positions",
  start_futures_intake: "Started futures order setup",
  continue_futures_intake: "Collected order details",
};

function friendlyToolTitle(name: string) {
  return TOOL_LABELS[name] || name.replace(/_/g, " ");
}

function friendlyErrorText(raw: string) {
  const text = raw.trim();
  const map: Record<string, string> = {
    tool_not_allowed: "That action isn’t available here.",
    tool_arguments_invalid: "I need a clearer request.",
    llm_timeout: "The AI timed out — answered locally.",
    llm_unavailable: "The AI is unavailable — answered locally.",
    openai_spend_gate_closed: "OpenAI spend is off — answered locally.",
    supervisor_worker_busy: "Paper worker is busy — try again in a moment.",
    market_data_unavailable: "Market data is temporarily unavailable.",
  };
  return map[text] || text;
}

function ToolTrace({
  toolNames,
  error,
}: {
  toolNames?: string[];
  payload?: ReplyPayload;
  error?: string | null;
}) {
  const tools = (toolNames || []).filter(Boolean);
  const failed = Boolean(error);

  if (failed) {
    const errText = friendlyErrorText(String(error || "Something went wrong"));
    return (
      <Trace className="mt-2">
        <TraceLine status="error">
          <TraceIcon>
            <CircleAlertIcon />
          </TraceIcon>
          <TraceTitle>{errText}</TraceTitle>
        </TraceLine>
      </Trace>
    );
  }

  if (tools.length === 0) return null;

  return (
    <Trace className="mt-1">
      <TraceCollapsible>
        <TraceCollapsibleTrigger>
          <TraceLine>
            <TraceIcon>
              <Wrench />
            </TraceIcon>
            <TraceTitle>
              {tools.length === 1
                ? friendlyToolTitle(tools[0])
                : `${tools.length} steps completed`}
            </TraceTitle>
          </TraceLine>
        </TraceCollapsibleTrigger>
        <TraceCollapsibleContent keepMounted>
          <Trace>
            {tools.map((name) => (
              <TraceLine key={name}>
                <TraceIcon>
                  <TerminalIcon />
                </TraceIcon>
                <TraceTitle>{friendlyToolTitle(name)}</TraceTitle>
              </TraceLine>
            ))}
          </Trace>
        </TraceCollapsibleContent>
      </TraceCollapsible>
    </Trace>
  );
}

function ApprovalConfirmation({
  title,
  description,
  approveLabel,
  rejectLabel = "Deny",
  busy,
  onApprove,
  onReject,
}: {
  title: string;
  description: string;
  approveLabel: string;
  rejectLabel?: string;
  busy?: boolean;
  onApprove?: () => void;
  onReject?: () => void;
}) {
  return (
    <Item variant="outline" size="sm" className="mt-3 border-brand/40 bg-brand/5">
      <ItemMedia variant="icon">
        <TerminalIcon />
      </ItemMedia>
      <ItemContent>
        <ItemTitle>{title}</ItemTitle>
        <ItemDescription>{description}</ItemDescription>
      </ItemContent>
      <ItemActions>
        {onReject ? (
          <Button size="sm" variant="outline" disabled={busy} onClick={onReject}>
            {rejectLabel}
          </Button>
        ) : null}
        {onApprove ? (
          <Button size="sm" disabled={busy} onClick={onApprove}>
            {approveLabel}
          </Button>
        ) : null}
      </ItemActions>
    </Item>
  );
}

function ChoiceChip({
  label,
  selected,
  disabled,
  onClick,
}: {
  label: string;
  selected: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
        selected
          ? "border-brand bg-brand/15 text-foreground"
          : "border-border bg-background text-muted-foreground hover:bg-muted/60",
        disabled && "pointer-events-none opacity-50",
      )}
    >
      <span
        className={cn(
          "flex size-3.5 items-center justify-center rounded-[3px] border",
          selected ? "border-brand bg-brand text-primary-foreground" : "border-muted-foreground/40",
        )}
        aria-hidden
      >
        {selected ? <CheckCircle2 className="size-2.5" /> : null}
      </span>
      {label}
    </button>
  );
}

function FuturesIntakeSelector({
  missing,
  collected,
  suggestedLimit,
  busy,
  onSubmit,
}: {
  missing: string[];
  collected?: Record<string, unknown> | null;
  suggestedLimit?: string | null;
  busy?: boolean;
  onSubmit: (message: string) => void;
}) {
  const needSide = missing.includes("side");
  const needType = missing.includes("order_type");
  const needLimit = missing.includes("limit_price");
  const needMargin = missing.includes("margin_or_qty") || missing.includes("qty");
  const needLev = missing.includes("leverage");
  const needSl = missing.includes("stop_loss_or_skip");
  const needTp = missing.includes("take_profit_or_skip");

  const preSide = String(collected?.side || "").toUpperCase();
  const preType = String(collected?.order_type || "");
  const preLev =
    collected?.leverage != null && String(collected.leverage).trim()
      ? String(collected.leverage)
      : "";
  const preMargin =
    collected?.margin_usdt != null && String(collected.margin_usdt).trim()
      ? String(collected.margin_usdt)
      : "";

  const [side, setSide] = React.useState<"BUY" | "SELL" | "">(
    preSide === "BUY" || preSide === "SELL" ? preSide : "",
  );
  const [orderType, setOrderType] = React.useState<"Market" | "Limit" | "">(
    preType === "Market" || preType === "Limit" ? preType : "",
  );
  const [leverage, setLeverage] = React.useState(preLev);
  const [marginUsdt, setMarginUsdt] = React.useState(preMargin);
  const [useEntryLimit, setUseEntryLimit] = React.useState(Boolean(suggestedLimit));
  const [slMode, setSlMode] = React.useState<"keep" | "skip">(needSl ? "keep" : "keep");
  const [tpMode, setTpMode] = React.useState<"keep" | "skip">(needTp ? "keep" : "keep");

  const accountHint =
    collected?.account_usdt != null ? String(collected.account_usdt) : null;

  const canSubmit =
    (!needSide || Boolean(side)) &&
    (!needType || Boolean(orderType)) &&
    (!needLev || Boolean(leverage)) &&
    (!needMargin || Boolean(marginUsdt)) &&
    (!needLimit || useEntryLimit || orderType === "Market");

  function buildMessage() {
    const parts: string[] = [];
    if (needSide && side) parts.push(side === "BUY" ? "Buy" : "Sell");
    if (needType && orderType) parts.push(orderType);
    if (needLimit && orderType === "Limit" && useEntryLimit) parts.push("use entry");
    if (needLev && leverage) parts.push(`leverage ${leverage}`);
    if (needMargin && marginUsdt) parts.push(`use ${marginUsdt} USDT`);
    if (needSl && slMode === "skip") parts.push("skip sl");
    if (needTp && tpMode === "skip") parts.push("skip tp");
    return parts.join(" ").trim();
  }

  if (!needSide && !needType && !needLimit && !needMargin && !needLev && !needSl && !needTp) {
    return null;
  }

  return (
    <div className="mt-3 space-y-3 rounded-xl border border-brand/40 bg-brand/5 p-3">
      <div>
        <p className="text-sm font-medium text-foreground">Select order details</p>
        <p className="text-[11px] text-muted-foreground">
          Tap options below, then Continue — no need to type the checklist.
          {accountHint ? ` Account ≈ ${accountHint} USDT.` : ""}
        </p>
      </div>

      {needSide ? (
        <div className="space-y-1.5">
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground">Side</p>
          <div className="flex flex-wrap gap-2">
            <ChoiceChip
              label="Buy / Long"
              selected={side === "BUY"}
              disabled={busy}
              onClick={() => setSide("BUY")}
            />
            <ChoiceChip
              label="Sell / Short"
              selected={side === "SELL"}
              disabled={busy}
              onClick={() => setSide("SELL")}
            />
          </div>
        </div>
      ) : null}

      {needType ? (
        <div className="space-y-1.5">
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground">Order type</p>
          <div className="flex flex-wrap gap-2">
            <ChoiceChip
              label="Market"
              selected={orderType === "Market"}
              disabled={busy}
              onClick={() => setOrderType("Market")}
            />
            <ChoiceChip
              label="Limit"
              selected={orderType === "Limit"}
              disabled={busy}
              onClick={() => setOrderType("Limit")}
            />
          </div>
        </div>
      ) : null}

      {needLimit && (orderType === "Limit" || (!needType && preType === "Limit")) ? (
        <div className="space-y-1.5">
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground">Limit price</p>
          <div className="flex flex-wrap gap-2">
            <ChoiceChip
              label={suggestedLimit ? `Use entry ${suggestedLimit}` : "Use analysis entry"}
              selected={useEntryLimit}
              disabled={busy || !suggestedLimit}
              onClick={() => setUseEntryLimit(true)}
            />
          </div>
        </div>
      ) : null}

      {needLev ? (
        <div className="space-y-1.5">
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground">Leverage</p>
          <div className="flex flex-wrap gap-2">
            {["2", "3", "5", "10", "20"].map((lev) => (
              <ChoiceChip
                key={lev}
                label={`${lev}x`}
                selected={leverage === lev}
                disabled={busy}
                onClick={() => setLeverage(lev)}
              />
            ))}
          </div>
        </div>
      ) : null}

      {needMargin ? (
        <div className="space-y-1.5">
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
            USDT for this trade
          </p>
          <div className="flex flex-wrap gap-2">
            {["1", "2", "3", "5"].map((amt) => (
              <ChoiceChip
                key={amt}
                label={`${amt} USDT`}
                selected={marginUsdt === amt}
                disabled={busy}
                onClick={() => setMarginUsdt(amt)}
              />
            ))}
          </div>
        </div>
      ) : null}

      {needSl ? (
        <div className="space-y-1.5">
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground">Stop loss</p>
          <div className="flex flex-wrap gap-2">
            <ChoiceChip
              label="Keep analysis SL"
              selected={slMode === "keep"}
              disabled={busy}
              onClick={() => setSlMode("keep")}
            />
            <ChoiceChip
              label="Skip SL"
              selected={slMode === "skip"}
              disabled={busy}
              onClick={() => setSlMode("skip")}
            />
          </div>
        </div>
      ) : null}

      {needTp ? (
        <div className="space-y-1.5">
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground">Take profit</p>
          <div className="flex flex-wrap gap-2">
            <ChoiceChip
              label="Keep analysis TP"
              selected={tpMode === "keep"}
              disabled={busy}
              onClick={() => setTpMode("keep")}
            />
            <ChoiceChip
              label="Skip TP"
              selected={tpMode === "skip"}
              disabled={busy}
              onClick={() => setTpMode("skip")}
            />
          </div>
        </div>
      ) : null}

      <div className="flex items-center justify-end gap-2 pt-1">
        <Button
          size="sm"
          disabled={busy || !canSubmit}
          onClick={() => {
            const message = buildMessage();
            if (message) onSubmit(message);
          }}
        >
          Continue
        </Button>
      </div>
    </div>
  );
}

export function OrchestratorReply({
  text,
  payload,
  className,
  onApprovePaper,
  onRejectPaper,
  onQuickReply,
  approvalBusy,
  toolNames,
  error,
}: {
  text: string;
  payload?: ReplyPayload;
  className?: string;
  onApprovePaper?: (proposalId?: string) => void;
  onRejectPaper?: (proposalId?: string) => void;
  onQuickReply?: (message: string) => void;
  approvalBusy?: boolean;
  toolNames?: string[];
  error?: string | null;
}) {
  const hasStructuredPayload = Boolean(payload && typeof payload === "object");
  const awaitingApproval = Boolean(
    payload &&
      (payload.awaiting_human_approval === true || payload.human_approval_required === true),
  );
  const awaitingIntake = Boolean(payload?.awaiting_intake === true || payload?.intake === true);
  const missing = Array.isArray(payload?.missing)
    ? (payload?.missing as unknown[]).map((m) => String(m))
    : [];
  const suggestedLimit =
    payload?.suggested_limit_price != null && String(payload.suggested_limit_price).trim()
      ? String(payload.suggested_limit_price)
      : null;
  const proposalId =
    payload?.proposal_id != null && String(payload.proposal_id).trim()
      ? String(payload.proposal_id)
      : undefined;
  const isLiveProposal =
    String(payload?.execution_mode || "").toUpperCase() === "LIVE" ||
    Boolean(payload?.live_placeable) ||
    Boolean(proposalId && proposalId.startsWith("ltp_"));
  const approveLabel = isLiveProposal ? "Approve" : "Approve paper";
  const approvalHint = isLiveProposal
    ? "This will place a real Bybit order. Nothing is sent until you Approve."
    : "This will place a simulated paper order.";
  const sideLabel = String(payload?.side || "order").toLowerCase();
  const confirmationTitle = isLiveProposal
    ? `Send this live ${sideLabel} to Bybit?`
    : `Place this paper ${sideLabel}?`;
  const collected =
    payload?.collected && typeof payload.collected === "object"
      ? (payload.collected as Record<string, unknown>)
      : null;
  const showIntakeSelector =
    awaitingIntake &&
    !awaitingApproval &&
    missing.length > 0 &&
    Boolean(onQuickReply);
  const showLimitSeed =
    awaitingIntake &&
    !awaitingApproval &&
    !showIntakeSelector &&
    missing.includes("limit_price") &&
    Boolean(suggestedLimit) &&
    Boolean(onQuickReply);

  if (!hasStructuredPayload) {
    const body = String(text || "").trim();
    const lines = body
      .split(/\n+/)
      .map((line) => line.trim())
      .filter(Boolean);
    const note = lines.find((line) => DISCLAIMER_RE.test(line)) || null;
    const paragraphs = lines.filter((line) => line !== note);
    return (
      <div className={cn("w-full max-w-2xl space-y-2", className)}>
        <div className="space-y-2 text-[14px] leading-relaxed text-foreground">
          {paragraphs.length > 0 ? (
            paragraphs.map((p) => <p key={p}>{p}</p>)
          ) : (
            <p>{body || "…"}</p>
          )}
        </div>
        <ToolTrace toolNames={toolNames} error={error} />
        {note ? (
          <p className="text-[11px] leading-snug text-muted-foreground">{note}</p>
        ) : null}
      </div>
    );
  }

  const parsed = parseFromText(text, payload);

  return (
    <div className={cn("w-full max-w-2xl space-y-3", className)}>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="mr-1 inline-flex size-6 items-center justify-center rounded-full border border-border bg-muted">
          <ReplyIcon headline={parsed.headline} />
        </span>
        {parsed.chips.map((chip) => (
          <Badge
            key={`${chip.label}-${chip.tone}`}
            variant="outline"
            className={cn("rounded-full px-2 py-0 text-[10px] font-medium", toneClass(chip.tone))}
          >
            {chip.label === "PAPER" ? <Radio className="mr-1 h-2.5 w-2.5" /> : null}
            {chip.label}
          </Badge>
        ))}
      </div>

      <p className="text-[15px] font-medium leading-snug tracking-tight text-foreground">
        {parsed.headline}
      </p>

      {parsed.facts.length > 0 ? (
        <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {parsed.facts.map((fact) => (
            <div
              key={fact.label}
              className="rounded-xl border border-border/80 bg-muted/40 px-2.5 py-2"
            >
              <dt className="text-[10px] uppercase tracking-wide text-muted-foreground">
                {fact.label}
              </dt>
              <dd className="mt-0.5 font-mono text-xs font-medium text-foreground">{fact.value}</dd>
            </div>
          ))}
        </dl>
      ) : null}

      {parsed.paragraphs.length > 0 ? (
        <div className="space-y-2 text-[13px] leading-relaxed text-muted-foreground">
          {parsed.paragraphs.map((p) => (
            <p key={p}>{p}</p>
          ))}
        </div>
      ) : null}

      {parsed.bullets.length > 0 ? (
        <ul className="space-y-1.5">
          {parsed.bullets.map((item) => (
            <li key={item} className="flex gap-2 text-[13px] leading-snug text-foreground/90">
              <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-brand" aria-hidden />
              <span>{item}</span>
            </li>
          ))}
        </ul>
      ) : null}

      <ToolTrace toolNames={toolNames} error={error} />

      {showIntakeSelector && onQuickReply ? (
        <FuturesIntakeSelector
          missing={missing}
          collected={collected}
          suggestedLimit={suggestedLimit}
          busy={approvalBusy}
          onSubmit={onQuickReply}
        />
      ) : null}

      {showLimitSeed ? (
        <ApprovalConfirmation
          title={`Use limit price ${suggestedLimit}?`}
          description="Taken from your latest analysis entry. Or switch to a Market order."
          approveLabel="Use entry"
          rejectLabel="Market"
          busy={approvalBusy}
          onApprove={onQuickReply ? () => onQuickReply("use entry") : undefined}
          onReject={onQuickReply ? () => onQuickReply("Market") : undefined}
        />
      ) : null}

      {awaitingApproval && (onApprovePaper || onRejectPaper) ? (
        <ApprovalConfirmation
          title={confirmationTitle}
          description={approvalHint}
          approveLabel={approveLabel}
          busy={approvalBusy}
          onApprove={onApprovePaper ? () => onApprovePaper(proposalId) : undefined}
          onReject={onRejectPaper ? () => onRejectPaper(proposalId) : undefined}
        />
      ) : null}

      {parsed.note ? (
        <p className="text-[11px] leading-snug text-muted-foreground">{parsed.note}</p>
      ) : null}
    </div>
  );
}
