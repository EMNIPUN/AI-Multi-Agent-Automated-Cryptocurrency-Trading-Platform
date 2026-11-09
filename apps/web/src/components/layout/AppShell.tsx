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

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const authChrome = pathStartsWith(pathname, AUTH_ROUTE_PREFIXES);
  const marketingChrome = MARKETING_ROUTE_EXACT.some((p) => pathname === p);

  if (authChrome || marketingChrome) {
    return <>{children}</>;
  }

  const chatFillPage = pathname === "/orchestrator";

  return (
    <SidebarProvider defaultOpen className="h-svh overflow-hidden">
      <RouteProgress />
      <RouteWarmup />
      <AppSidebar />
      <SidebarInset className="flex h-svh min-h-0 min-w-0 flex-col overflow-hidden">
        <AppTopbar />
        <GlobalStatusBar />
        <main
          className={
            chatFillPage
              ? "mx-auto flex w-full min-h-0 min-w-0 max-w-[1480px] flex-1 flex-col overflow-hidden px-3 py-2 md:px-5"
              : "mx-auto flex w-full min-h-0 min-w-0 max-w-[1480px] flex-1 flex-col overflow-y-auto px-3 py-3 md:px-5 md:py-4"
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
        {chatFillPage ? null : (
          <footer className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-t border-border/50 px-4 py-2 text-[11px] text-muted-foreground md:px-5">
            <span>CryptoNova Command Center · paper supervision · live trading locked</span>
            <span className="font-mono text-muted-foreground">v0.3.1</span>
          </footer>
        )}
      </SidebarInset>
    </SidebarProvider>
  );
}
