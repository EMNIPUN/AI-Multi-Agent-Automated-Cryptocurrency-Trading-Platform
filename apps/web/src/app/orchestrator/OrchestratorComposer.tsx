"use client";

import { ArrowUpIcon, ChevronDownIcon, Square } from "lucide-react";
import { useRef, useState } from "react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupTextarea } from "@/components/ui/input-group";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";

import type { ChatExecutionMode } from "./orchestrator-state";

export function OrchestratorComposer({
  sending,
  chatMode,
  onChatModeChange,
  onSend,
  onCancel,
}: {
  sending: boolean;
  chatMode: ChatExecutionMode;
  onChatModeChange: (mode: ChatExecutionMode) => void;
  onSend: (text: string) => void;
  onCancel: () => void;
}) {
  const [draft, setDraft] = useState("");
  const formRef = useRef<HTMLFormElement>(null);
  const canSend = draft.trim().length > 0 && !sending;

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSend) return;
    const text = draft.trim();
    setDraft("");
    onSend(text);
  }

  return (
    <div className="relative z-10 shrink-0 border-t border-border bg-card px-3 py-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] md:px-4">
      <form ref={formRef} onSubmit={submit} className="mx-auto w-full max-w-3xl">
        <InputGroup className="border-border bg-background">
          <InputGroupTextarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder={chatMode === "LIVE" ? "Ask for a live Bybit open, close, or position…" : "Ask the paper supervisor…"}
            aria-label="Message"
            disabled={sending}
            rows={1}
            className="min-h-[2.5rem] max-h-32 py-2.5 text-[14px]"
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                formRef.current?.requestSubmit();
              }
            }}
          />
          <InputGroupAddon align="block-end">
            <DropdownMenu>
              <DropdownMenuTrigger
                disabled={sending}
                aria-label="Execution lane"
                className={cn(
                  "inline-flex h-8 items-center gap-1 rounded-full px-2.5 text-sm font-medium outline-none hover:bg-accent hover:text-accent-foreground focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50",
                  chatMode === "LIVE" && "text-destructive hover:text-destructive",
                )}
              >
                {chatMode}
                <ChevronDownIcon className="size-3.5 opacity-70" aria-hidden />
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="min-w-[14rem]">
                <DropdownMenuRadioGroup value={chatMode} onValueChange={(value) => onChatModeChange(value === "LIVE" ? "LIVE" : "PAPER")}>
                  <DropdownMenuGroup>
                    <DropdownMenuLabel>Execution lane</DropdownMenuLabel>
                    <DropdownMenuRadioItem value="PAPER">PAPER — simulated journal</DropdownMenuRadioItem>
                    <DropdownMenuRadioItem value="LIVE">LIVE — Bybit MAINNET + Approve</DropdownMenuRadioItem>
                  </DropdownMenuGroup>
                </DropdownMenuRadioGroup>
              </DropdownMenuContent>
            </DropdownMenu>
            {sending ? (
              <InputGroupButton type="button" variant="outline" size="sm" className="ml-auto" onClick={onCancel} aria-label="Cancel request">
                <Square className="h-3.5 w-3.5" aria-hidden />
                Cancel
              </InputGroupButton>
            ) : (
              <InputGroupButton type="submit" variant="default" size="icon-sm" className="ml-auto" disabled={!canSend} aria-label="Send message">
                <ArrowUpIcon className="h-4 w-4" aria-hidden />
              </InputGroupButton>
            )}
          </InputGroupAddon>
        </InputGroup>
        <p className="mt-1 px-0.5 text-[10px] text-muted-foreground">
          {sending ? (
            <span className="inline-flex items-center gap-1.5"><Spinner className="size-3" />Working… you can cancel.</span>
          ) : chatMode === "LIVE" ? (
            "LIVE MAINNET · Approve required per order · Enter to send · Shift+Enter for newline"
          ) : (
            "PAPER lane · Enter to send · Shift+Enter for newline"
          )}
        </p>
      </form>
    </div>
  );
}
