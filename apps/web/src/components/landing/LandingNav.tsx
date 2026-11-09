"use client";

import Link from "next/link";
import { Menu, Moon, Sun, X } from "lucide-react";
import { useEffect, useState } from "react";

import { CryptoNovaMark } from "@/components/brand/CryptoNovaLogo";
import { Button } from "@/components/ui/button";
import { NAV_LINKS } from "@/components/landing/landing-data";
import { usePersistedTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";

export function LandingNav() {
  const [open, setOpen] = useState(false);
  const { light, setLight } = usePersistedTheme();
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={cn(
        "sticky top-0 z-50 transition-colors",
        scrolled
          ? "border-b border-border bg-background/85 backdrop-blur-xl"
          : "bg-transparent",
      )}
    >
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-3 px-4 md:h-16 md:px-6">
        <Link href="/" className="flex items-center gap-2.5" aria-label="CryptoNova home">
          <CryptoNovaMark className="h-7 w-7" priority />
          <span className="text-[15px] font-semibold tracking-tight text-foreground">
            CryptoNova
          </span>
        </Link>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="icon"
            className="h-9 w-9 rounded-full"
            aria-label={light ? "Use dark theme" : "Use light theme"}
            onClick={() => setLight((v) => !v)}
          >
            {light ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
          </Button>
          <Button
            variant="outline"
            size="icon"
            className="h-9 w-9 rounded-full"
            aria-label={open ? "Close menu" : "Open menu"}
            aria-expanded={open}
            onClick={() => setOpen((v) => !v)}
          >
            {open ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
          </Button>
          <Button asChild className="rounded-full px-4">
            <Link href="/signup">Try for Free</Link>
          </Button>
        </div>
      </div>

      {open ? (
        <div className="border-t border-border bg-background/95 px-4 py-5 backdrop-blur-xl">
          <nav className="mx-auto flex max-w-6xl flex-col gap-4" aria-label="Site">
            {NAV_LINKS.map((link) => (
              <a
                key={link.href}
                href={link.href}
                className="text-sm text-muted-foreground transition-colors hover:text-foreground"
                onClick={() => setOpen(false)}
              >
                {link.label}
              </a>
            ))}
            <Link
              href="/login"
              className="text-sm text-muted-foreground transition-colors hover:text-foreground"
              onClick={() => setOpen(false)}
            >
              Log in
            </Link>
            <Button asChild className="mt-1 w-full rounded-full sm:hidden">
              <Link href="/signup" onClick={() => setOpen(false)}>
                Try for Free
              </Link>
            </Button>
          </nav>
        </div>
      ) : null}
    </header>
  );
}
