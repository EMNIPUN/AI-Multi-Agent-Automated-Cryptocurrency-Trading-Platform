"use client";

import { Bot, Check, ChevronDown, Copy, MessageCircleDashedIcon, User } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Conversation, ConversationContent, ConversationScrollButton } from "@/components/ai-elements/conversation";
import { Suggestion, Suggestions } from "@/components/ai-elements/suggestion";
import { StatusBadge } from "@/components/design-system";
import { Bubble, BubbleContent } from "@/components/ui/bubble";
import { Message, MessageContent, MessageFooter } from "@/components/ui/message";
import { MessageScrollerItem } from "@/components/ui/message-scroller";
import { Spinner } from "@/components/ui/spinner";
import { formatClock } from "@/lib/formatting/time";
import { cn } from "@/lib/utils";

import { OrchestratorComposer } from "./OrchestratorComposer";
import { OrchestratorReply } from "./OrchestratorReply";
import { ToolTraceCard } from "./ToolTraceCard";
import { ORCHESTRATION_LABEL, orchestrationState, type ChatExecutionMode, type ChatTurn } from "./orchestrator-state";

export type { ChatTurn } from "./orchestrator-state";

type SuggestionMode = "both" | "paper" | "live";

/** Only prompts the backend tool registry supports. */
const SUGGESTIONS: { text: string; label: string; mode: SuggestionMode }[] = [
  { text: "Analyze HYPEUSDT futures.", label: "Analyze HYPEUSDT", mode: "both" },
  { text: "Run all agents and give entry TP and SL for HYPE", label: "Run all agents", mode: "both" },
  { text: "Why didn't the system open a position?", label: "Explain a block", mode: "paper" },
  { text: "Explain the last trading decision.", label: "Explain decision", mode: "paper" },
  { text: "Summarize paper equity and open positions.", label: "Paper performance", mode: "paper" },
  { text: "Show the supervisor status.", label: "Supervisor status", mode: "paper" },
  { text: "Check OpenAI usage.", label: "OpenAI usage", mode: "both" },
  { text: "Start autonomous paper trading.", label: "Start paper", mode: "paper" },
  { text: "Pause the trading supervisor.", label: "Pause", mode: "paper" },
  { text: "Resume the trading supervisor.", label: "Resume", mode: "paper" },
  { text: "Emergency halt.", label: "Halt", mode: "both" },
  { text: "Show the live-readiness checklist.", label: "Live checklist", mode: "live" },
  { text: "Show Bybit position for HYPEUSDT", label: "Bybit position", mode: "live" },
  { text: "Place futures order HYPEUSDT", label: "Futures intake", mode: "live" },
  { text: "Close current HYPEUSDT position on Bybit", label: "Close on Bybit", mode: "live" },
];

function CopyButton({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      className="inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] text-muted-foreground opacity-0 transition-opacity hover:text-foreground focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring group-hover/message:opacity-100"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setDone(true);
          window.setTimeout(() => setDone(false), 1500);
        } catch {
          /* clipboard unavailable */
        }
      }}
      aria-label="Copy response"
    >
      {done ? <Check className="h-3 w-3" aria-hidden /> : <Copy className="h-3 w-3" aria-hidden />}
      {done ? "Copied" : "Copy"}
    </button>
  );
}

export function OrchestratorCommandChat({
  sending,
  onSend,
  onCancel,
  turns,
  chatMode,
  onChatModeChange,
  historyLoading,
}: {
  sending: boolean;
  onSend: (text: string) => Promise<void> | void;
  onCancel: () => void;
  turns: ChatTurn[];
  chatMode: ChatExecutionMode;
  onChatModeChange: (mode: ChatExecutionMode) => void;
  historyLoading?: boolean;
}) {
  const [suggestionsOpen, setSuggestionsOpen] = useState(true);
  const visible = useMemo(() => {
    const modeKey = chatMode === "LIVE" ? "live" : "paper";
    return SUGGESTIONS.filter((s) => s.mode === "both" || s.mode === modeKey);
  }, [chatMode]);
  const hasThread = turns.length > 0 || sending;

  useEffect(() => {
    if (hasThread) setSuggestionsOpen(false);
  }, [hasThread]);

  function approveMessage(proposalId?: string) {
    if (proposalId?.startsWith("ltp_")) return `Approve live trade ${proposalId}`;
    if (proposalId?.startsWith("ptp_")) return `Approve paper trade ${proposalId}`;
    return chatMode === "LIVE" ? "Approve live trade" : "Approve paper trade";
  }
  function rejectMessage(proposalId?: string) {
    if (proposalId?.startsWith("ltp_")) return `Reject live trade ${proposalId}`;
    if (proposalId?.startsWith("ptp_")) return `Reject paper trade ${proposalId}`;
    return chatMode === "LIVE" ? "Reject live trade" : "Reject paper trade";
  }

  return (
    <section className="cn-panel relative flex h-full min-h-0 flex-1 flex-col overflow-hidden" aria-label="Orchestrator conversation">
      <div className="flex shrink-0 items-center justify-between gap-3 border-b border-border px-4 py-2 md:px-5">
        <h2 className="text-sm font-medium tracking-tight text-foreground">Conversation</h2>
        <button
          type="button"
          onClick={() => setSuggestionsOpen((v) => !v)}
          className="inline-flex shrink-0 items-center gap-1 rounded-full border border-border px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-expanded={suggestionsOpen}
          aria-controls="orchestrator-suggestions"
        >
          Suggestions
          <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", suggestionsOpen && "rotate-180")} aria-hidden />
        </button>
      </div>

      {suggestionsOpen ? (
        <div id="orchestrator-suggestions" className="shrink-0 border-b border-border px-4 py-2.5 md:px-5">
          <Suggestions aria-label="Suggested prompts">
            {visible.map((hint) => (
              <Suggestion
                key={hint.text}
                suggestion={hint.text}
                disabled={sending}
                onClick={(text) => void onSend(text)}
                className={cn("h-8 shrink-0 text-xs", hint.label === "Halt" && "border-destructive/40 text-destructive hover:bg-destructive/10 hover:text-destructive")}
              >
                {hint.label}
              </Suggestion>
            ))}
          </Suggestions>
        </div>
      ) : null}

      <Conversation className="min-h-[14rem]" aria-busy={sending || historyLoading || undefined}>
        <ConversationContent className="mx-auto w-full max-w-3xl gap-5 px-4 py-4 md:px-5" role="log" aria-live="polite">
          {historyLoading ? (
            <div className="flex items-center justify-center gap-2 py-10 text-xs text-muted-foreground">
              <Spinner className="size-4" /> Loading thread…
            </div>
          ) : null}
          {!hasThread && !historyLoading ? (
            <div className="flex min-h-[14rem] flex-1 flex-col items-center justify-center gap-3 text-center">
              <div className="flex size-11 items-center justify-center rounded-full border border-border bg-muted text-muted-foreground">
                <MessageCircleDashedIcon className="h-5 w-5" aria-hidden />
              </div>
              <p className="text-sm font-medium text-foreground">
                {chatMode === "LIVE" ? "Ask the live Bybit orchestrator" : "Ask the paper supervisor"}
              </p>
              <p className="max-w-sm text-xs leading-relaxed text-muted-foreground">
                Pick a suggestion or type below. The Orchestrator explains and coordinates; the deterministic Risk Engine keeps veto authority. LIVE still needs Approve for every Bybit order.
              </p>
            </div>
          ) : null}

          {turns.map((turn, index) => {
            const isUser = turn.role === "user";
            if (isUser) {
              return (
                <MessageScrollerItem key={turn.id} messageId={turn.id} scrollAnchor={index === turns.length - 1 || (sending && index === turns.length - 1)}>
                  <Message align="end">
                    <div className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full border border-primary bg-primary text-primary-foreground" aria-hidden>
                      <User className="h-3.5 w-3.5" />
                    </div>
                    <MessageContent className="max-w-[min(100%,30rem)]">
                      <Bubble align="end" variant="muted">
                        <BubbleContent>{turn.text}</BubbleContent>
                      </Bubble>
                      <MessageFooter>
                        <span className="text-[10px] uppercase tracking-wide">You · {formatClock(turn.at)}</span>
                      </MessageFooter>
                    </MessageContent>
                  </Message>
                </MessageScrollerItem>
              );
            }
            const state = orchestrationState(turn.meta);
            const badge = ORCHESTRATION_LABEL[state];
            return (
              <MessageScrollerItem key={turn.id} messageId={turn.id}>
                <Message align="start" className="items-start">
                  <div className="mt-1 flex size-7 shrink-0 items-center justify-center rounded-full border border-border bg-muted text-muted-foreground" aria-hidden>
                    <Bot className="h-3.5 w-3.5" />
                  </div>
                  <MessageContent className="max-w-full flex-1 gap-2">
                    <OrchestratorReply
                      text={turn.text}
                      payload={turn.payload}
                      approvalBusy={sending}
                      onApprovePaper={(proposalId) => void onSend(approveMessage(proposalId))}
                      onRejectPaper={(proposalId) => void onSend(rejectMessage(proposalId))}
                      onQuickReply={(message) => void onSend(message)}
                    />
                    {turn.meta ? <ToolTraceCard envelopes={turn.meta.envelopes} toolNames={turn.meta.toolNames} error={turn.meta.error} /> : null}
                    <MessageFooter className="flex-wrap gap-2">
                      <span className="text-[10px] uppercase tracking-wide">Orchestrator · {formatClock(turn.at)}</span>
                      {turn.meta ? (
                        <StatusBadge
                          label={state === "openai" && turn.meta.model ? `${badge.label} · ${turn.meta.model}` : badge.label}
                          tone={badge.tone === "ok" ? "ok" : badge.tone === "warn" ? "warn" : badge.tone === "danger" ? "danger" : badge.tone === "info" ? "info" : "neutral"}
                          className="px-2 py-0 text-[10px]"
                        />
                      ) : null}
                      {turn.meta?.exchangeOrderSent ? <StatusBadge label="Exchange order sent" tone="live" className="px-2 py-0 text-[10px]" /> : null}
                      <CopyButton text={turn.text} />
                    </MessageFooter>
                  </MessageContent>
                </Message>
              </MessageScrollerItem>
            );
          })}

          {sending ? (
            <MessageScrollerItem messageId="pending">
              <Message align="start" className="items-start">
                <div className="mt-1 flex size-7 shrink-0 items-center justify-center rounded-full border border-border bg-muted text-muted-foreground" aria-hidden>
                  <Bot className="h-3.5 w-3.5" />
                </div>
                <MessageContent>
                  <div className="inline-flex items-center gap-2 rounded-2xl border border-border bg-card px-4 py-3 text-sm text-muted-foreground" role="status">
                    <Spinner className="size-4" />
                    Working on that…
                  </div>
                </MessageContent>
              </Message>
            </MessageScrollerItem>
          ) : null}
        </ConversationContent>
        <ConversationScrollButton aria-label="Scroll to latest message" />
      </Conversation>

      <OrchestratorComposer sending={sending} chatMode={chatMode} onChatModeChange={onChatModeChange} onSend={(t) => void onSend(t)} onCancel={onCancel} />
    </section>
  );
}
