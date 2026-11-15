"use client";

import { usePathname } from "next/navigation";

import { RequireAuth } from "@/components/auth/RequireAuth";
import { AppSidebar } from "@/components/layout/AppSidebar";
import { AppTopbar } from "@/components/layout/AppTopbar";
import { GlobalStatusBar } from "@/components/layout/GlobalStatusBar";
import { RouteProgress } from "@/components/layout/RouteProgress";
import { RouteWarmup } from "@/components/layout/RouteWarmup";
import { PageMotion } from "@/components/shared/PageMotion";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import {
  pathStartsWith,
  AUTH_ROUTE_PREFIXES,
  MARKETING_ROUTE_EXACT,
} from "@/lib/auth/auth-paths";
import { ExecutionStateProvider, useExecutionState } from "@/providers/ExecutionStateProvider";

function ShellFooter() {
  const { data } = useExecutionState();
  const lane = !data
    ? "runtime state loading"
    : data.live === "armed_approve_required"
      ? `LIVE armed on Bybit ${data.bybitEnv} · Approve required per order`
      : data.testnet === "armed"
        ? "TESTNET armed · live mainnet locked"
        : "paper supervision · live trading locked";
  return (
    <footer className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-t border-border/50 px-4 py-2 text-[11px] text-muted-foreground md:px-5">
      <span>CryptoNova Command Center · {lane}</span>
      <span className="font-mono text-muted-foreground">v0.3.2</span>
    </footer>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const authChrome = pathStartsWith(pathname, AUTH_ROUTE_PREFIXES);
  const marketingChrome = MARKETING_ROUTE_EXACT.some((p) => pathname === p);

  if (authChrome || marketingChrome) {
    return <>{children}</>;
  }

  const chatFillPage = pathname === "/orchestrator";

  return (
    <ExecutionStateProvider>
      <SidebarProvider defaultOpen className="h-svh overflow-hidden">
        <RouteProgress />
        <RouteWarmup />
        <AppSidebar />
        <SidebarInset className="flex h-svh min-h-0 min-w-0 flex-col overflow-hidden">
          <AppTopbar />
          <GlobalStatusBar />
          <main
            id="main"
            className={
              chatFillPage
                ? "mx-auto flex w-full min-h-0 min-w-0 max-w-[1480px] flex-1 flex-col overflow-hidden px-3 py-2 md:px-6"
                : "mx-auto flex w-full min-h-0 min-w-0 max-w-[1480px] flex-1 flex-col overflow-y-auto px-4 py-4 md:px-6 md:py-5"
            }
          >
            <RequireAuth>
              <PageMotion
                className={
                  chatFillPage
                    ? "flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden"
                    : "flex min-h-0 min-w-0 w-full flex-col"
                }
              >
                {children}
              </PageMotion>
            </RequireAuth>
          </main>
          {chatFillPage ? null : <ShellFooter />}
        </SidebarInset>
      </SidebarProvider>
    </ExecutionStateProvider>
  );
}
