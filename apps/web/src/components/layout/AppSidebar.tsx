"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Home } from "lucide-react";
import { useEffect, useState, useTransition } from "react";

import { CryptoNovaMark } from "@/components/brand/CryptoNovaLogo";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  SidebarSeparator,
  useSidebar,
} from "@/components/ui/sidebar";
import { NAV_GROUPS } from "@/lib/nav";
import { cn } from "@/lib/utils";

function isActive(pathname: string, href: string) {
  if (href === "/orchestrator") return pathname === "/orchestrator" || pathname === "/dashboard";
  if (href === "/agents") return pathname === "/agents";
  return pathname === href || pathname.startsWith(`${href}/`);
}

function NavGroups() {
  const pathname = usePathname();
  const router = useRouter();
  const { isMobile, setOpenMobile } = useSidebar();
  const [isPending, startTransition] = useTransition();
  const [pendingHref, setPendingHref] = useState<string | null>(null);

  useEffect(() => {
    setPendingHref(null);
  }, [pathname]);

  return (
    <>
      {NAV_GROUPS.map((group) => (
        <SidebarGroup key={group.label || "primary"}>
          {group.label ? <SidebarGroupLabel>{group.label}</SidebarGroupLabel> : null}
          <SidebarGroupContent>
            <SidebarMenu>
              {group.items.map((item) => {
                const active = isActive(pathname, item.href);
                const pending = isPending && pendingHref === item.href;
                const Icon = item.icon;
                return (
                  <SidebarMenuItem key={item.href}>
                    <SidebarMenuButton
                      asChild
                      isActive={active || pending}
                      tooltip={item.label}
                      className={cn(
                        (active || pending) && "cn-nav-active data-[active=true]:bg-transparent",
                        pending && "opacity-80",
                      )}
                    >
                      <Link
                        href={item.href}
                        prefetch
                        aria-current={active ? "page" : undefined}
                        aria-busy={pending || undefined}
                        onClick={(event) => {
                          if (
                            event.defaultPrevented ||
                            event.button !== 0 ||
                            event.metaKey ||
                            event.altKey ||
                            event.ctrlKey ||
                            event.shiftKey
                          ) {
                            return;
                          }
                          event.preventDefault();
                          if (isMobile) setOpenMobile(false);
                          setPendingHref(item.href);
                          startTransition(() => {
                            router.push(item.href);
                          });
                        }}
                        onMouseEnter={() => router.prefetch(item.href)}
                        onFocus={() => router.prefetch(item.href)}
                      >
                        <Icon className={cn(pending && "animate-pulse")} />
                        <span>{item.label}</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      ))}
    </>
  );
}

export function AppSidebar() {
  const { isMobile, setOpenMobile } = useSidebar();

  return (
    <Sidebar collapsible="icon" variant="sidebar" className="border-sidebar-border">
      <SidebarHeader className="border-b border-sidebar-border">
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" asChild tooltip="CryptoNova">
              <Link href="/orchestrator" aria-label="CryptoNova Orchestrator">
                <CryptoNovaMark priority className="h-8 w-8 shrink-0" />
                <div className="grid flex-1 text-left text-sm leading-tight">
                  <span className="font-display truncate text-base tracking-tight">CryptoNova</span>
                  <span className="truncate text-[10px] uppercase tracking-[0.14em] text-brand">
                    Command Center
                  </span>
                </div>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton asChild tooltip="Marketing site">
                  <Link
                    href="/"
                    onClick={() => {
                      if (isMobile) setOpenMobile(false);
                    }}
                  >
                    <Home />
                    <span>Marketing site</span>
                  </Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
        <SidebarSeparator />
        <NavGroups />
      </SidebarContent>

      <SidebarFooter>
        <Separator className="mb-2 bg-sidebar-border" />
        <div className="group-data-[collapsible=icon]:hidden rounded-xl border border-border bg-muted/40 p-3">
          <div className="flex flex-wrap gap-1.5">
            <Badge variant="sample">SAMPLE-safe</Badge>
            <Badge variant="outline" className="rounded-full text-[10px]">
              Trading off
            </Badge>
          </div>
          <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
            Orchestrator is paper-only. Live exchange orders stay locked.
          </p>
        </div>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
