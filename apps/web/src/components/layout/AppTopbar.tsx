"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Bell,
  Columns2,
  LogOut,
  Moon,
  Rows2,
  Sun,
  UserRound,
} from "lucide-react";
import { useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { CryptoNovaMark } from "@/components/brand/CryptoNovaLogo";
import { CommandPalette, CommandPaletteTrigger } from "@/components/layout/CommandPalette";
import { StatusBadge } from "@/components/design-system";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { crumbForPath } from "@/lib/nav";
import { usePersistedDensity, usePersistedTheme } from "@/lib/theme";

export function AppTopbar() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, signOut, configured } = useAuth();
  const { light, setLight } = usePersistedTheme();
  const { density, setDensity } = usePersistedDensity();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const crumb = crumbForPath(pathname);
  const label = user?.email?.split("@")[0] || (configured ? "Sign in" : "Guest");

  async function handleSignOut() {
    await signOut();
    router.replace("/login");
  }

  return (
    <>
      <header className="app-topbar z-40 flex h-12 shrink-0 items-center justify-between gap-3 border-b border-border/60 bg-background/85 px-3 md:px-5">
        <div className="flex min-w-0 items-center gap-2">
          <SidebarTrigger className="-ml-1" />
          <Link
            href="/orchestrator"
            className="flex shrink-0 items-center gap-2 md:hidden"
            aria-label="CryptoNova"
          >
            <CryptoNovaMark className="h-7 w-7" />
          </Link>
          <nav aria-label="Breadcrumb" className="min-w-0">
            <ol className="flex min-w-0 items-center gap-1.5 text-xs text-muted-foreground">
              <li className="hidden truncate sm:inline">{crumb.group}</li>
              <li className="hidden text-border sm:inline" aria-hidden>
                /
              </li>
              <li className="truncate font-medium text-foreground">{crumb.label}</li>
            </ol>
          </nav>
        </div>

        <div className="flex items-center gap-1.5">
          <CommandPaletteTrigger onOpen={() => setPaletteOpen(true)} />
          <StatusBadge label="PAPER" tone="paper" className="hidden lg:inline-flex" />
          <StatusBadge label="LIVE locked" tone="live" className="hidden lg:inline-flex" />
          <Button variant="ghost" size="icon" asChild aria-label="Notifications">
            <Link href="/notifications">
              <Bell className="h-4 w-4" />
            </Link>
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label={density === "compact" ? "Use comfortable density" : "Use compact density"}
            onClick={() => setDensity(density === "compact" ? "comfortable" : "compact")}
          >
            {density === "compact" ? (
              <Rows2 className="h-4 w-4" />
            ) : (
              <Columns2 className="h-4 w-4" />
            )}
          </Button>
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
                <Link href="/system">System Health</Link>
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
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
    </>
  );
}
