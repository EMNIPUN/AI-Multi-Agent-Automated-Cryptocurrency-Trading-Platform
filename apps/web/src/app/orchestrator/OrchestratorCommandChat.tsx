"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowUpIcon,
  Bot,
  ChevronDown,
  ChevronDownIcon,
  MessageCircleDashedIcon,
  User,
} from "lucide-react";

import { Suggestion, Suggestions } from "@/components/ai-elements/suggestion";
import { Bubble, BubbleContent } from "@/components/ui/bubble";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupTextarea,
} from "@/components/ui/input-group";
import { Message, MessageContent, MessageFooter } from "@/components/ui/message";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";

import { OrchestratorReply, type ReplyPayload } from "./OrchestratorReply";
import type { ChatExecutionMode } from "./OrchestratorStatusStrip";

export type ChatTurn = {
  id: string;
  role: "user" | "assistant";
  text: string;
  at: number;
  payload?: ReplyPayload;
  meta?: {
    toolNames?: string[];
    openaiCalled?: boolean;
    error?: string | null;
  };
};

type SuggestionMode = "both" | "paper" | "live";

const SUGGESTIONS: {
  text: string;
  label: string;
  mode?: SuggestionMode;
}[] = [
  { text: "Start autonomous paper trading.", label: "Start paper", mode: "paper" },
  { text: "Pause the trading supervisor.", label: "Pause", mode: "paper" },
  { text: "Resume the trading supervisor.", label: "Resume", mode: "paper" },
  { text: "Emergency halt.", label: "Halt", mode: "both" },
  { text: "Analyze HYPEUSDT futures.", label: "Analyze HYPEUSDT", mode: "both" },
  { text: "Place futures order HYPEUSDT", label: "Futures intake", mode: "live" },
  {
    text: "Buy Market qty 0.74 leverage 5 skip sl skip tp",
    label: "Example intake",
    mode: "live",
  },
  {
    text: "Close current HYPEUSDT position on Bybit",
    label: "Close HYPE on Bybit",
    mode: "live",
  },
  { text: "Show Bybit position for HYPEUSDT", label: "Bybit position", mode: "live" },
  {
    text: "Run all agents and give entry TP and SL for HYPE",
    label: "Entry / TP / SL",
    mode: "both",
  },
  { text: "Summarize paper equity and open positions.", label: "Paper equity", mode: "paper" },
  { text: "Show the live-readiness checklist.", label: "Live checklist", mode: "live" },
];

export function OrchestratorCommandChat({
  sending,
  onSend,
  turns,
  chatMode = "PAPER",
  onChatModeChange,
}: {
  sending: boolean;
  onSend: (text: string) => Promise<void> | void;
  turns: ChatTurn[];
  chatMode?: ChatExecutionMode;
  onChatModeChange?: (mode: ChatExecutionMode) => void;
}) {
  function approveMessage(proposalId?: string) {
    if (proposalId?.startsWith("ltp_")) {
      return `Approve live trade ${proposalId}`;
    }
    if (proposalId?.startsWith("ptp_")) {
      return `Approve paper trade ${proposalId}`;
    }
    return chatMode === "LIVE" ? "Approve live trade" : "Approve paper trade";
  }
  function rejectMessage(proposalId?: string) {
    if (proposalId?.startsWith("ltp_")) {
      return `Reject live trade ${proposalId}`;
    }
    if (proposalId?.startsWith("ptp_")) {
      return `Reject paper trade ${proposalId}`;
    }
    return chatMode === "LIVE" ? "Reject live trade" : "Reject paper trade";
  }

  const [draft, setDraft] = useState("");
  const [commandsOpen, setCommandsOpen] = useState(true);
  const formRef = useRef<HTMLFormElement>(null);
  const threadRef = useRef<HTMLDivElement>(null);

  const visible = useMemo(() => {
    const modeKey = chatMode === "LIVE" ? "live" : "paper";
    return SUGGESTIONS.filter((s) => !s.mode || s.mode === "both" || s.mode === modeKey);
  }, [chatMode]);

  const canSend = draft.trim().length > 0 && !sending;
  const showEmpty = turns.length === 0 && !sending;
  const hasThread = turns.length > 0 || sending;

  useEffect(() => {
    if (hasThread) setCommandsOpen(false);
  }, [hasThread]);

  useEffect(() => {
    const pane = threadRef.current;
    if (!pane) return;
    pane.scrollTop = pane.scrollHeight;
  }, [turns, sending]);

  function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSend) return;
    const text = draft.trim();
    setDraft("");
    void onSend(text);
  }

  return (
    <section className="cn-panel relative flex h-full min-h-0 flex-1 flex-col overflow-hidden">
      <div className="flex shrink-0 items-center justify-between gap-3 border-b border-border px-4 py-2 md:px-5">
        <h2 className="text-sm font-medium tracking-tight text-foreground">Command chat</h2>
        <button
          type="button"
          onClick={() => setCommandsOpen((v) => !v)}
          className="inline-flex shrink-0 items-center gap-1 rounded-full border border-border px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          aria-expanded={commandsOpen}
        >
          Suggestions
          <ChevronDown
            className={cn("h-3.5 w-3.5 transition-transform", commandsOpen && "rotate-180")}
          />
        </button>
      </div>

      {commandsOpen ? (
        <div className="shrink-0 border-b border-border px-4 py-3 md:px-5">
          <Suggestions>
            {visible.map((hint) => (
              <Suggestion
                key={hint.text}
                suggestion={hint.text}
                disabled={sending}
                onClick={(text) => void onSend(text)}
                className={cn(
                  "h-8 shrink-0 text-xs",
                  hint.label === "Halt" &&
                    "border-destructive/40 text-destructive hover:bg-destructive/10 hover:text-destructive",
                )}
              >
                {hint.label}
              </Suggestion>
            ))}
          </Suggestions>
        </div>
      ) : null}

      <div
        ref={threadRef}
        className="cn-thin-scroll min-h-[18rem] flex-1 overflow-y-auto overscroll-contain px-4 py-3 md:px-5"
        role="log"
        aria-live="polite"
        aria-busy={sending}
      >
        {showEmpty ? (
          <div className="flex h-full min-h-[12rem] flex-col items-center justify-center gap-3 text-center">
            <div className="flex size-11 items-center justify-center rounded-full border border-border bg-muted text-muted-foreground">
              <MessageCircleDashedIcon className="h-5 w-5" />
            </div>
            <p className="text-sm font-medium text-foreground">
              {chatMode === "LIVE" ? "Ask the live Bybit orchestrator" : "Ask the paper supervisor"}
            </p>
            <p className="max-w-sm text-xs leading-relaxed text-muted-foreground">
              Pick PAPER or LIVE in the composer, tap a suggestion, or type below. LIVE still needs
              Approve for every Bybit order.
            </p>
          </div>
        ) : (
          <div className="mx-auto flex w-full max-w-3xl flex-col gap-5 pb-2">
            {turns.map((turn) => {
              const isUser = turn.role === "user";
              if (isUser) {
                return (
                  <Message key={turn.id} align="end">
                    <div
                      className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full border border-primary bg-primary text-primary-foreground"
                      aria-hidden
                    >
                      <User className="h-3.5 w-3.5" />
                    </div>
                    <MessageContent className="max-w-[min(100%,28rem)]">
                      <Bubble align="end" variant="muted">
                        <BubbleContent>{turn.text}</BubbleContent>
                      </Bubble>
                      <MessageFooter>
                        <span className="text-[10px] uppercase tracking-wide">You</span>
                      </MessageFooter>
                    </MessageContent>
                  </Message>
                );
              }

              return (
                <Message key={turn.id} align="start" className="items-start">
                  <div
                    className="mt-1 flex size-7 shrink-0 items-center justify-center rounded-full border border-border bg-muted text-muted-foreground"
                    aria-hidden
                  >
                    <Bot className="h-3.5 w-3.5" />
                  </div>
                  <MessageContent className="max-w-full flex-1 gap-2">
                    <OrchestratorReply
                      text={turn.text}
                      payload={turn.payload}
                      toolNames={turn.meta?.toolNames}
                      error={turn.meta?.error}
                      approvalBusy={sending}
                      onApprovePaper={(proposalId) => void onSend(approveMessage(proposalId))}
                      onRejectPaper={(proposalId) => void onSend(rejectMessage(proposalId))}
                      onQuickReply={(message) => void onSend(message)}
                    />
                    <MessageFooter>
                      <span className="text-[10px] uppercase tracking-wide">Orchestrator</span>
                    </MessageFooter>
                  </MessageContent>
                </Message>
              );
            })}

            {sending ? (
              <Message align="start" className="items-start">
                <div
                  className="mt-1 flex size-7 shrink-0 items-center justify-center rounded-full border border-border bg-muted text-muted-foreground"
                  aria-hidden
                >
                  <Bot className="h-3.5 w-3.5" />
                </div>
                <MessageContent>
                  <div className="inline-flex items-center gap-2 rounded-2xl border border-border bg-card px-4 py-3 text-sm text-muted-foreground">
                    <Spinner className="size-4" />
                    Working on that…
                  </div>
                </MessageContent>
              </Message>
            ) : null}
          </div>
        )}
      </div>

      <div className="relative z-10 shrink-0 border-t border-border bg-card px-3 py-2 md:px-4">
        <form ref={formRef} onSubmit={onSubmit} className="mx-auto w-full max-w-3xl">
          <InputGroup className="border-border bg-background">
            <InputGroupTextarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder={
                chatMode === "LIVE"
                  ? "Ask for a live Bybit open, close, or position…"
                  : "Ask the paper supervisor…"
              }
              aria-label="Message"
              disabled={sending}
              rows={1}
              className="min-h-[2.5rem] max-h-28 py-2.5"
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  formRef.current?.requestSubmit();
                }
              }}
            />
            <InputGroupAddon align="block-end">
              <DropdownMenu>
                <DropdownMenuTrigger
                  disabled={sending}
                  aria-label="Trading mode"
                  className={cn(
                    "inline-flex h-8 items-center gap-1 rounded-full px-2.5 text-sm font-medium outline-none hover:bg-accent hover:text-accent-foreground disabled:opacity-50",
                    chatMode === "LIVE" && "text-destructive hover:text-destructive",
                  )}
                >
                  {chatMode}
                  <ChevronDownIcon className="size-3.5 opacity-70" />
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start" className="min-w-[12rem]">
                  <DropdownMenuRadioGroup
                    value={chatMode}
                    onValueChange={(value) =>
                      onChatModeChange?.(value === "LIVE" ? "LIVE" : "PAPER")
                    }
                  >
                    <DropdownMenuGroup>
                      <DropdownMenuLabel>Execution mode</DropdownMenuLabel>
                      <DropdownMenuRadioItem value="PAPER">
                        PAPER — simulated journal
                      </DropdownMenuRadioItem>
                      <DropdownMenuRadioItem value="LIVE">
                        LIVE — Bybit MAINNET + Approve
                      </DropdownMenuRadioItem>
                    </DropdownMenuGroup>
                  </DropdownMenuRadioGroup>
                </DropdownMenuContent>
              </DropdownMenu>
              <InputGroupButton
                type="submit"
                variant="default"
                size="icon-sm"
                className="ml-auto"
                disabled={!canSend}
                aria-label="Send"
              >
                {sending ? <Spinner className="size-4" /> : <ArrowUpIcon className="h-4 w-4" />}
              </InputGroupButton>
            </InputGroupAddon>
          </InputGroup>
          <p className="mt-1 px-0.5 text-[10px] text-muted-foreground">
            {chatMode === "LIVE"
              ? "LIVE MAINNET · Approve required per order · Enter to send"
              : "PAPER mode · Enter to send · Shift+Enter for newline"}
          </p>
        </form>
      </div>
    </section>
  );
}
