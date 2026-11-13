"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Search } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { NAV_FLAT } from "@/lib/nav";
import { cn } from "@/lib/utils";

/** Navigate-only command palette (Ctrl+K). Never submits orders. */
export function CommandPalette({
  open,
  onOpenChange,
}: {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
} = {}) {
  const router = useRouter();
  const [internalOpen, setInternalOpen] = useState(false);
  const [q, setQ] = useState("");
  const isControlled = open !== undefined;
  const resolvedOpen = isControlled ? open : internalOpen;

  function setOpen(next: boolean) {
    if (!isControlled) setInternalOpen(next);
    onOpenChange?.(next);
  }

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen(!resolvedOpen);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resolvedOpen]);

  const results = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return NAV_FLAT;
    return NAV_FLAT.filter(
      (item) =>
        item.label.toLowerCase().includes(needle) ||
        item.href.toLowerCase().includes(needle) ||
        item.group.toLowerCase().includes(needle),
    );
  }, [q]);

  function go(href: string) {
    setOpen(false);
    setQ("");
    router.push(href);
  }

  return (
    <Dialog
      open={resolvedOpen}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) setQ("");
      }}
    >
      <DialogContent className="gap-0 overflow-hidden p-0 sm:max-w-lg">
        <DialogHeader className="border-b border-border px-4 py-3">
          <DialogTitle className="flex items-center gap-2 text-sm font-medium">
            <Search className="h-4 w-4 text-muted-foreground" aria-hidden />
            Jump to page
          </DialogTitle>
        </DialogHeader>
        <div className="px-3 py-2">
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search routes…"
            autoFocus
            aria-label="Search navigation"
          />
        </div>
        <ul className="cn-thin-scroll max-h-72 overflow-y-auto px-2 pb-2" role="listbox">
          {results.map((item) => (
            <li key={item.href}>
              <button
                type="button"
                role="option"
                aria-selected={false}
                className={cn(
                  "flex w-full items-center justify-between rounded-xl px-3 py-2 text-left text-sm transition-colors",
                  "hover:bg-muted focus-visible:bg-muted focus-visible:outline-none",
                )}
                onClick={() => go(item.href)}
              >
                <span className="font-medium text-foreground">{item.label}</span>
                <span className="text-[11px] text-muted-foreground">{item.group}</span>
              </button>
            </li>
          ))}
          {results.length === 0 ? (
            <li className="px-3 py-6 text-center text-sm text-muted-foreground">No matches</li>
          ) : null}
        </ul>
        <p className="border-t border-border px-4 py-2 text-[11px] text-muted-foreground">
          Navigation only · never places orders · Ctrl+K search · Ctrl+B sidebar · Esc closes
        </p>
      </DialogContent>
    </Dialog>
  );
}

export function CommandPaletteTrigger({ onOpen }: { onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="hidden items-center gap-2 rounded-full border border-border bg-muted/50 px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground md:inline-flex"
      aria-label="Open command palette"
    >
      <Search className="h-3.5 w-3.5" />
      <span>Search</span>
      <kbd className="rounded border border-border bg-background px-1.5 font-mono text-[10px]">
        Ctrl K
      </kbd>
    </button>
  );
}
