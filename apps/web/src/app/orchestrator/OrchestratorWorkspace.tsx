"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { MessageSquarePlus, PanelLeft, PanelRight } from "lucide-react";

import { AiWorkspaceTemplate } from "@/components/design-system/templates";
import { ErrorState } from "@/components/design-system";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { usePolledResource } from "@/hooks/use-polled-resource";
import {
  fetchAutonomySnapshot,
  fetchConversation,
  fetchConversations,
  fetchDiagnostics,
  fetchOrchestratorStatus,
  fetchPaperReport,
  resetConversation,
  sendChat,
} from "@/lib/api/orchestrator";
import { toNumber } from "@/lib/formatting/decimal";

import { ContextInspector } from "./ContextInspector";
import { ConversationRail } from "./ConversationRail";
import { OrchestratorCommandChat } from "./OrchestratorCommandChat";
import { OrchestratorStatusStrip } from "./OrchestratorStatusStrip";
import {
  metaFromResponse,
  orchestrationState,
  payloadFromResponse,
  responseUsesLiveLane,
  type ChatExecutionMode,
  type ChatTurn,
  type OrchestrationState,
} from "./orchestrator-state";

const CONV_KEY = "cryptonova.orchestrator.conversation_id";
const HALT_MESSAGE = "Emergency halt.";

function newTurn(role: ChatTurn["role"], text: string, payload?: ChatTurn["payload"], meta?: ChatTurn["meta"]): ChatTurn {
  return { id: `${role}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`, role, text, at: Date.now(), payload, meta };
}

export function OrchestratorWorkspace() {
  const status = usePolledResource(fetchOrchestratorStatus, { intervalMs: 15_000 });
  const report = usePolledResource(fetchPaperReport, { intervalMs: 30_000 });
  const autonomy = usePolledResource(fetchAutonomySnapshot, { intervalMs: 20_000 });
  const diagnostics = usePolledResource(fetchDiagnostics, { intervalMs: 60_000 });
  const conversations = usePolledResource(fetchConversations, { intervalMs: 0 });

  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [chatMode, setChatMode] = useState<ChatExecutionMode>("PAPER");
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [railOpen, setRailOpen] = useState(false);
  const [lastState, setLastState] = useState<OrchestrationState | null>(null);
  const [lastModel, setLastModel] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Restore the last thread id once.
  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(CONV_KEY);
      if (saved) setConversationId(saved);
    } catch {
      /* ignore */
    }
  }, []);

  // Load server history when the active thread changes.
  useEffect(() => {
    if (!conversationId) return;
    let cancelled = false;
    setHistoryLoading(true);
    void (async () => {
      const result = await fetchConversation(conversationId);
      if (cancelled) return;
      setHistoryLoading(false);
      if (!result.ok) {
        if (result.status === 404) {
          setConversationId(null);
          try {
            window.localStorage.removeItem(CONV_KEY);
          } catch {
            /* ignore */
          }
        }
        return;
      }
      const messages = Array.isArray(result.data.messages) ? result.data.messages : [];
      setTurns(
        messages.map((m, i) => ({
          id: `hist-${i}-${m.created_ms ?? i}`,
          role: m.role === "user" ? "user" : "assistant",
          text: String(m.content || ""),
          at: toNumber(m.created_ms) ?? Date.now(),
        })),
      );
    })();
    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  const selectConversation = useCallback((id: string) => {
    abortRef.current?.abort();
    setTurns([]);
    setConversationId(id);
    setRailOpen(false);
    try {
      window.localStorage.setItem(CONV_KEY, id);
    } catch {
      /* ignore */
    }
  }, []);

  const newConversation = useCallback(async () => {
    abortRef.current?.abort();
    const prev = conversationId;
    setTurns([]);
    setLastState(null);
    setLastModel(null);
    setConversationId(null);
    setRailOpen(false);
    try {
      window.localStorage.removeItem(CONV_KEY);
    } catch {
      /* ignore */
    }
    if (prev) {
      await resetConversation(prev);
      void conversations.refresh();
    }
  }, [conversationId, conversations]);

  const refreshAll = useCallback(() => {
    void status.refresh();
    void report.refresh();
    void autonomy.refresh();
  }, [status, report, autonomy]);

  const cancelRequest = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  async function sendMessage(text: string) {
    const trimmed = text.trim();
    if (!trimmed || sending) return;
    const controller = new AbortController();
    abortRef.current = controller;
    setSending(true);
    setTurns((prev) => [...prev, newTurn("user", trimmed)]);
    const result = await sendChat({ message: trimmed, execution_mode: chatMode, conversation_id: conversationId });
    if (controller.signal.aborted || (!result.ok && result.code === "aborted")) {
      setTurns((prev) => [...prev, newTurn("assistant", "Request cancelled before a reply arrived. Nothing was changed by this message unless the server had already acted.", undefined, { cancelled: true })]);
      setLastState("cancelled");
      setSending(false);
      return;
    }
    if (!result.ok) {
      setTurns((prev) => [
        ...prev,
        newTurn("assistant", `Request failed (${result.status || "network"}): ${result.message}. Check that the API is running and try again.`, undefined, { error: result.code }),
      ]);
      setLastState("tool_failed");
      setSending(false);
      return;
    }
    const body = result.data;
    const nextCid = body.conversation_id ? String(body.conversation_id) : conversationId;
    if (nextCid && nextCid !== conversationId) {
      setConversationId(nextCid);
      try {
        window.localStorage.setItem(CONV_KEY, nextCid);
      } catch {
        /* ignore */
      }
    }
    const meta = metaFromResponse(body);
    const reply = String(body.reply ?? "").trim() || "Orchestrator returned an empty reply. Status may still have updated — check the strip above.";
    if (responseUsesLiveLane(body, meta.toolNames || [])) setChatMode("LIVE");
    setLastState(orchestrationState(meta));
    setLastModel(meta.model ?? null);
    setTurns((prev) => [...prev, newTurn("assistant", reply, payloadFromResponse(body), meta)]);
    setSending(false);
    refreshAll();
    if (!conversationId) void conversations.refresh();
  }

  // Abort any in-flight chat on unmount (never leave a dangling fetch).
  useEffect(() => () => abortRef.current?.abort(), []);

  const st = status.data;
  const liveArmed = Boolean(st?.live_mutate_allowed ?? st?.live_unlocked);
  const equityNum = toNumber(report.data?.equity);
  const openPositions = toNumber(report.data?.open_positions) ?? 0;
  const initialLoading = status.loading && !st;

  const inspector = (
    <ContextInspector
      status={st}
      report={report.data}
      autonomy={autonomy.data}
      openai={diagnostics.data?.openai ?? null}
      loading={initialLoading}
      chatMode={chatMode}
      liveArmed={liveArmed}
      lastState={lastState}
      lastModel={lastModel}
    />
  );

  const rail = (
    <ConversationRail
      conversations={conversations.data?.conversations ?? []}
      loading={conversations.loading}
      activeId={conversationId}
      onSelect={selectConversation}
      onNew={() => void newConversation()}
      turnCount={turns.length}
      chatMode={chatMode}
    />
  );

  if (initialLoading) {
    return (
      <AiWorkspaceTemplate title="AI Orchestrator" modes={["paper"]}>
        <Skeleton className="h-12 w-full rounded-2xl" />
        <Skeleton className="h-[28rem] w-full rounded-3xl" />
      </AiWorkspaceTemplate>
    );
  }

  return (
    <AiWorkspaceTemplate
      title="AI Orchestrator"
      modes={["paper", "readonly"]}
      className="flex h-full min-h-0 flex-1 flex-col gap-2 space-y-0 overflow-hidden pb-0"
    >
      {status.error && !st ? (
        <ErrorState compact title="Orchestrator unavailable" code={status.error.code} at={status.error.at} onRetry={refreshAll} retrying={status.refreshing} className="shrink-0" />
      ) : null}

      <div className="shrink-0">
        <OrchestratorStatusStrip
          chatMode={chatMode}
          liveArmed={liveArmed}
          supervisorState={String(st?.state || "STOPPED").toUpperCase()}
          supervisorOn={Boolean(st?.enabled)}
          equityNum={equityNum}
          currency={String(report.data?.currency || "USDT")}
          openPositions={openPositions}
          refreshing={status.refreshing || report.refreshing}
          sending={sending}
          onRefresh={refreshAll}
          onHalt={() => void sendMessage(HALT_MESSAGE)}
        />
      </div>

      <div className="grid min-h-0 min-w-0 flex-1 gap-3 overflow-hidden [grid-template-rows:minmax(0,1fr)] lg:grid-cols-[13rem_minmax(0,1fr)] xl:grid-cols-[13rem_minmax(0,1fr)_minmax(17rem,19rem)]">
        <div className="hidden min-h-0 lg:block">{rail}</div>

        <div className="flex h-full min-h-0 min-w-0 flex-col">
          <div className="mb-2 flex shrink-0 gap-2 xl:hidden">
            <Button type="button" variant="outline" size="sm" className="rounded-full lg:hidden" onClick={() => setRailOpen(true)}>
              <PanelLeft className="mr-1.5 h-3.5 w-3.5" aria-hidden />
              Threads
            </Button>
            <Button type="button" variant="outline" size="sm" className="rounded-full lg:hidden" onClick={() => void newConversation()}>
              <MessageSquarePlus className="mr-1.5 h-3.5 w-3.5" aria-hidden />
              New
            </Button>
            <Button type="button" variant="outline" size="sm" className="ml-auto rounded-full" onClick={() => setInspectorOpen(true)}>
              <PanelRight className="mr-1.5 h-3.5 w-3.5" aria-hidden />
              Context
            </Button>
          </div>
          <OrchestratorCommandChat
            sending={sending}
            turns={turns}
            chatMode={chatMode}
            onChatModeChange={setChatMode}
            onSend={sendMessage}
            onCancel={cancelRequest}
            historyLoading={historyLoading}
          />
        </div>

        <div className="cn-thin-scroll hidden min-h-0 min-w-0 overflow-y-auto xl:block">{inspector}</div>
      </div>

      <Sheet open={inspectorOpen} onOpenChange={setInspectorOpen}>
        <SheetContent side="right" className="w-[min(100%,24rem)] overflow-y-auto sm:max-w-md">
          <SheetHeader className="pr-8">
            <SheetTitle>Context</SheetTitle>
            <SheetDescription>Market scope, supervisor, risk verdict, latest analysis and model spend.</SheetDescription>
          </SheetHeader>
          <div className="mt-4">{inspector}</div>
        </SheetContent>
      </Sheet>
      <Sheet open={railOpen} onOpenChange={setRailOpen}>
        <SheetContent side="left" className="w-[min(100%,20rem)] overflow-y-auto">
          <SheetHeader className="pr-8">
            <SheetTitle>Threads</SheetTitle>
            <SheetDescription>Saved conversations on this operator machine.</SheetDescription>
          </SheetHeader>
          <div className="mt-4 h-[70vh]">{rail}</div>
        </SheetContent>
      </Sheet>
    </AiWorkspaceTemplate>
  );
}
