"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { LogOut, Moon, Radio, ShieldOff, Sun, UserRound } from "lucide-react";

import { RequireAuth } from "@/components/auth/RequireAuth";
import { useAuth } from "@/components/auth/AuthProvider";
import { AppSidebar } from "@/components/layout/AppSidebar";
import { RouteProgress } from "@/components/layout/RouteProgress";
import { RouteWarmup } from "@/components/layout/RouteWarmup";
import { PageMotion } from "@/components/shared/PageMotion";
import { CryptoNovaMark } from "@/components/brand/CryptoNovaLogo";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import {
  pathStartsWith,
  AUTH_ROUTE_PREFIXES,
  MARKETING_ROUTE_EXACT,
} from "@/lib/auth/auth-paths";
import { usePersistedTheme } from "@/lib/theme";

function titleFromPath(pathname: string) {
  const map: Record<string, string> = {
    "/dashboard": "Overview",
    "/agents": "Agents",
    "/agents/live": "Live AI Analysis",
    "/markets": "Markets & Charts",
    "/portfolio": "Portfolio",
    "/positions": "Positions & Orders",
    "/paper": "Demo Trading",
    "/risk": "Risk Center",
    "/analytics": "Analytics",
    "/backtesting": "Backtesting",
    "/settings": "Settings",
    "/settings/exchanges": "Exchanges",
    "/notifications": "Notifications",
    "/news": "News",
    "/llm": "LLM Intelligence",
  };
  return (
    map[pathname] ||
    pathname.split("/").filter(Boolean).pop()?.replace(/-/g, " ") ||
    "Workspace"
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, signOut, configured } = useAuth();
  const { light, setLight } = usePersistedTheme();
  const authChrome = pathStartsWith(pathname, AUTH_ROUTE_PREFIXES);
  const marketingChrome = MARKETING_ROUTE_EXACT.some((p) => pathname === p);

  if (authChrome || marketingChrome) {
    return <>{children}</>;
  }

  const pageTitle = titleFromPath(pathname);
  const label = user?.email?.split("@")[0] || (configured ? "Sign in" : "Guest");

  async function handleSignOut() {
    await signOut();
    router.replace("/login");
  }

  return (
    <SidebarProvider defaultOpen>
      <RouteProgress />
      <RouteWarmup />
      <AppSidebar />
      <SidebarInset className="min-w-0 overflow-x-hidden">
        <header className="app-topbar sticky top-0 z-40 flex h-14 shrink-0 items-center justify-between gap-3 border-b border-border/60 bg-background/80 px-3 md:px-5">
          <div className="flex min-w-0 items-center gap-2">
            <SidebarTrigger className="-ml-1" />
            <Link
              href="/dashboard"
              className="flex shrink-0 items-center gap-2 md:hidden"
              aria-label="CryptoNova"
            >
              <CryptoNovaMark className="h-8 w-8" />
              <span className="font-display text-base leading-none tracking-tight">CryptoNova</span>
            </Link>
            <div className="min-w-0">
              <p className="truncate text-sm font-medium capitalize text-foreground sm:text-base">
                {pageTitle}
              </p>
              <p className="hidden text-xs text-muted-foreground sm:block">
                Simple views · live trading stays off
              </p>
            </div>
          </div>

          <div className="flex items-center gap-1.5">
            <Badge variant="warning" className="hidden rounded-full md:inline-flex">
              <Radio className="mr-1 h-3 w-3" />
              Read-only
            </Badge>
            <Badge
              variant="outline"
              className="hidden rounded-full border-white/15 text-white/90 sm:inline-flex"
            >
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
                <Button variant="secondary" size="sm" className="gap-2 rounded-full">
                  <UserRound className="h-4 w-4" />
                  <span className="hidden max-w-[9rem] truncate sm:inline">{label}</span>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="min-w-[12rem]">
                {user?.email ? (
                  <>
                    <DropdownMenuLabel className="max-w-[16rem] truncate font-normal text-muted-foreground">
                      {user.email}
                    </DropdownMenuLabel>
                    <DropdownMenuSeparator />
                  </>
                ) : null}
                <DropdownMenuItem asChild>
                  <Link href="/settings">Settings</Link>
                </DropdownMenuItem>
                <DropdownMenuItem asChild>
                  <Link href="/">Marketing site</Link>
                </DropdownMenuItem>
                {user ? (
                  <DropdownMenuItem
                    onSelect={(ev) => {
                      ev.preventDefault();
                      void handleSignOut();
                    }}
                  >
                    <LogOut className="mr-2 h-3.5 w-3.5" />
                    Sign out
                  </DropdownMenuItem>
                ) : (
                  <DropdownMenuItem asChild>
                    <Link href="/login">Sign in</Link>
                  </DropdownMenuItem>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>

        <main className="mx-auto w-full min-w-0 max-w-[1480px] flex-1 px-3 py-4 md:px-5 md:py-5">
          <RequireAuth>
            <PageMotion>{children}</PageMotion>
          </RequireAuth>
        </main>
        <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-border/50 px-4 py-3 text-[11px] text-muted-foreground md:px-5">
          <span>CryptoNova · public markets + gated private reads · trading off</span>
          <span className="font-mono text-white/50">v0.3.1</span>
        </footer>
      </SidebarInset>
    </SidebarProvider>
  );
}
