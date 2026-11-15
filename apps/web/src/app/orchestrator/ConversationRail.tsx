"use client";

import { MessageSquarePlus, Search } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import type { ConversationSummary } from "@/lib/api/orchestrator";
import { formatRelative } from "@/lib/formatting/time";
import { cn } from "@/lib/utils";

import { conversationTitle } from "./orchestrator-state";

export function ConversationRail({
  conversations,
  loading,
  activeId,
  onSelect,
  onNew,
  turnCount,
  chatMode,
}: {
  conversations: ConversationSummary[];
  loading: boolean;
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  turnCount: number;
  chatMode: "PAPER" | "LIVE";
}) {
  const [q, setQ] = useState("");
  const list = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const sorted = [...conversations].sort((a, b) => b.updated_ms - a.updated_ms);
    if (!needle) return sorted;
    return sorted.filter((c) => conversationTitle(c).toLowerCase().includes(needle) || c.conversation_id.includes(needle));
  }, [conversations, q]);

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <Button type="button" variant="outline" className="w-full justify-start gap-2 rounded-xl" onClick={onNew}>
        <MessageSquarePlus className="h-4 w-4" aria-hidden />
        New conversation
      </Button>
      <div className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search threads"
          aria-label="Search conversations"
          className="h-8 rounded-full pl-8 text-xs"
        />
      </div>
      <div className="cn-panel flex min-h-0 flex-1 flex-col">
        <p className="shrink-0 border-b border-border px-3 py-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          Recent
        </p>
        <ul className="cn-thin-scroll min-h-0 flex-1 overflow-y-auto p-1.5" aria-label="Conversations">
          {loading && conversations.length === 0 ? (
            Array.from({ length: 4 }).map((_, i) => (
              <li key={i} className="p-1.5">
                <Skeleton className="h-10 w-full rounded-lg" />
              </li>
            ))
          ) : list.length === 0 ? (
            <li className="px-3 py-6 text-center text-xs text-muted-foreground">
              {q ? "No threads match." : "No saved threads yet. History persists after the first reply."}
            </li>
          ) : (
            list.map((c) => {
              const active = c.conversation_id === activeId;
              return (
                <li key={c.conversation_id}>
                  <button
                    type="button"
                    onClick={() => onSelect(c.conversation_id)}
                    aria-current={active ? "true" : undefined}
                    className={cn(
                      "w-full rounded-lg px-2.5 py-2 text-left transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      active && "cn-nav-active",
                    )}
                  >
                    <p className="truncate text-xs font-medium text-foreground">{conversationTitle(c)}</p>
                    <p className="mt-0.5 flex items-center justify-between gap-2 text-[10px] text-muted-foreground">
                      <span className="truncate font-mono">{c.conversation_id.slice(0, 14)}</span>
                      <span className="shrink-0">{formatRelative(c.updated_ms)}</span>
                    </p>
                  </button>
                </li>
              );
            })
          )}
        </ul>
        <div className="shrink-0 border-t border-border px-3 py-2 text-[11px] text-muted-foreground">
          <p>
            {activeId ? "Server-backed thread" : "Unsaved chat"} · {turnCount} message{turnCount === 1 ? "" : "s"}
          </p>
          <p className="mt-0.5 font-mono">{chatMode} lane</p>
        </div>
      </div>
    </div>
  );
}
