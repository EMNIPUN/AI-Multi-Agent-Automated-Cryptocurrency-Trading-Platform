"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  ChevronLeft,
  Menu,
  Moon,
  Radio,
  ShieldOff,
  Sun,
  UserRound,
} from "lucide-react";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { CryptoNovaMark } from "@/components/brand/CryptoNovaLogo";
import { NAV_GROUPS } from "@/lib/nav";
import { cn } from "@/lib/utils";

function isActive(pathname: string, href: string) {
  if (href === "/dashboard") return pathname === "/dashboard";
  if (href === "/agents") return pathname === "/agents";
  return pathname === href || pathname.startsWith(`${href}/`);
}

function NavLinks({
  collapsed,
  onNavigate,
}: {
  collapsed?: boolean;
  onNavigate?: () => void;
}) {
  const pathname = usePathname();
  return (
    <div className="flex flex-col gap-5">
      {NAV_GROUPS.map((group) => (
        <div key={group.label || "primary"}>
          {!collapsed && group.label ? (
            <p className="mb-1.5 px-3 text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
              {group.label}
            </p>
          ) : null}
          <nav className="flex flex-col gap-0.5" aria-label={group.label || "Primary"}>
            {group.items.map((item) => {
              const active = isActive(pathname, item.href);
              const Icon = item.icon;
              const link = (
                <Link
                  href={item.href}
                  onClick={onNavigate}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "group flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors",
                    collapsed && "justify-center px-2",
                    active
                      ? "bg-primary/15 text-primary shadow-[inset_2px_0_0_hsl(var(--primary))]"
                      : "text-muted-foreground hover:bg-muted/80 hover:text-foreground",
                  )}
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  {!collapsed ? <span>{item.label}</span> : null}
                </Link>
              );
              if (!collapsed) return <div key={item.href}>{link}</div>;
              return (
                <Tooltip key={item.href}>
                  <TooltipTrigger asChild>{link}</TooltipTrigger>
                  <TooltipContent side="right">{item.label}</TooltipContent>
                </Tooltip>
              );
            })}
          </nav>
        </div>
      ))}
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [light, setLight] = useState(false);

  useEffect(() => {
    document.documentElement.classList.toggle("light", light);
    document.documentElement.classList.toggle("dark", !light);
  }, [light]);

  const crumb = pathname.split("/").filter(Boolean).join(" / ") || "dashboard";

  return (
    <div
      className={cn(
        "min-h-screen lg:grid",
        collapsed ? "lg:grid-cols-[4.5rem_1fr]" : "lg:grid-cols-[16.5rem_1fr]",
      )}
    >
      <aside className="app-sidebar relative hidden border-r border-border/70 bg-card/80 backdrop-blur-xl lg:flex lg:flex-col">
        <div className={cn("flex items-center gap-2.5 px-3 py-3", collapsed && "justify-center px-2")}>
          <Link href="/dashboard" aria-label="CryptoNova dashboard" className="flex items-center gap-2.5">
            <CryptoNovaMark
              priority
              className={cn("shrink-0", collapsed ? "h-11 w-11" : "h-12 w-12")}
            />
            {!collapsed ? (
              <span className="font-display text-lg leading-none tracking-tight">CryptoNova</span>
            ) : null}
          </Link>
        </div>
        <ScrollArea className="flex-1 px-2 pb-4">
          <NavLinks collapsed={collapsed} />
        </ScrollArea>
        <div className="border-t border-border/70 p-3">
          {!collapsed ? (
            <div className="mb-2 rounded-lg border border-border/70 bg-background/40 p-2.5">
              <Badge variant="sample">SAMPLE-safe</Badge>
              <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
                Live order routes stay off. Fixtures are labeled.
              </p>
            </div>
          ) : null}
          <Button
            variant="ghost"
            size={collapsed ? "icon" : "sm"}
            className="w-full"
            onClick={() => setCollapsed((v) => !v)}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            <ChevronLeft className={cn("h-4 w-4 transition-transform", collapsed && "rotate-180")} />
            {!collapsed ? "Collapse" : null}
          </Button>
        </div>
      </aside>

      <div className="flex min-h-screen min-w-0 flex-col">
        <header className="app-topbar sticky top-0 z-40 flex items-center justify-between gap-3 border-b border-border/70 bg-background/85 px-3 py-2.5 backdrop-blur-xl md:px-5">
          <div className="flex min-w-0 items-center gap-2">
            <Sheet open={open} onOpenChange={setOpen}>
              <SheetTrigger asChild>
                <Button variant="outline" size="icon" className="lg:hidden" aria-label="Open menu">
                  <Menu className="h-4 w-4" />
                </Button>
              </SheetTrigger>
              <SheetContent side="left" className="bg-card">
                <div className="mb-5 flex items-center gap-2.5">
                  <CryptoNovaMark className="h-11 w-11 shrink-0" />
                  <span className="font-display text-lg leading-none tracking-tight">CryptoNova</span>
                </div>
                <NavLinks onNavigate={() => setOpen(false)} />
              </SheetContent>
            </Sheet>
            <Link
              href="/dashboard"
              className="flex shrink-0 items-center gap-2 lg:hidden"
              aria-label="CryptoNova"
            >
              <CryptoNovaMark className="h-9 w-9" />
              <span className="font-display text-base leading-none tracking-tight">CryptoNova</span>
            </Link>
            {collapsed ? (
              <Link
                href="/dashboard"
                className="hidden shrink-0 items-center lg:inline-flex"
                aria-label="CryptoNova"
              >
                <span className="font-display text-base leading-none tracking-tight">CryptoNova</span>
              </Link>
            ) : null}
            <div className="min-w-0">
              <p className="truncate font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
                {crumb}
              </p>
              <p className="hidden text-sm text-foreground sm:block">Operator terminal</p>
            </div>
          </div>

          <div className="flex items-center gap-1.5">
            <Badge variant="warning" className="hidden md:inline-flex">
              <Radio className="mr-1 h-3 w-3" />
              Read-only
            </Badge>
            <Badge variant="outline" className="hidden sm:inline-flex">
              <ShieldOff className="mr-1 h-3 w-3" />
              Trading off
            </Badge>
            <Button
              variant="ghost"
              size="icon"
              aria-label={light ? "Use dark theme" : "Use light theme"}
              onClick={() => setLight((v) => !v)}
            >
              {light ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="secondary" size="sm" className="gap-2">
                  <UserRound className="h-4 w-4" />
                  <span className="hidden sm:inline">Operator</span>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem asChild>
                  <Link href="/settings">Settings</Link>
                </DropdownMenuItem>
                <DropdownMenuItem disabled>Sign out (auth scaffold)</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>

        <main className="mx-auto w-full max-w-[1400px] flex-1 px-3 py-4 md:px-6 md:py-6">
          {children}
        </main>
        <Separator />
        <footer className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5 text-[11px] text-muted-foreground md:px-6">
          <span>CryptoNova · private catalog reads gated · no place-order APIs</span>
          <span className="font-mono">v0.3.1</span>
        </footer>
      </div>
    </div>
  );
}
