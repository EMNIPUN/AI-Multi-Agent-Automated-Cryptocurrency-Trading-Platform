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
        "sticky top-0 z-50 border-b transition-colors",
        scrolled ? "border-white/10 bg-black/70 backdrop-blur-xl" : "border-transparent bg-transparent",
      )}
    >
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-4 px-4 md:px-6">
        <Link href="/" className="flex items-center gap-2" aria-label="CryptoNova home">
          <CryptoNovaMark className="h-8 w-8" priority />
          <span className="text-sm font-medium tracking-tight text-white/90">CryptoNova</span>
        </Link>

        <nav className="hidden items-center gap-6 md:flex" aria-label="Main">
          {NAV_LINKS.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="text-sm text-white/55 transition-colors hover:text-white"
            >
              {link.label}
            </a>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="icon"
            className="text-white/70"
            aria-label={light ? "Use dark theme" : "Use light theme"}
            onClick={() => setLight((v) => !v)}
          >
            {light ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
          </Button>
          <Button asChild variant="ghost" className="hidden text-white/70 sm:inline-flex">
            <Link href="/login">Log in</Link>
          </Button>
          <Button asChild variant="secondary" className="hidden rounded-md sm:inline-flex">
            <Link href="/signup">Sign up</Link>
          </Button>
          <Button
            variant="outline"
            size="icon"
            className="md:hidden"
            aria-label={open ? "Close menu" : "Open menu"}
            onClick={() => setOpen((v) => !v)}
          >
            {open ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
          </Button>
        </div>
      </div>

      {open ? (
        <div className="border-t border-white/10 bg-black/95 px-4 py-4 md:hidden">
          <nav className="flex flex-col gap-3" aria-label="Mobile">
            {NAV_LINKS.map((link) => (
              <a
                key={link.href}
                href={link.href}
                className="text-sm text-white/70"
                onClick={() => setOpen(false)}
              >
                {link.label}
              </a>
            ))}
            <Link href="/login" className="text-sm" onClick={() => setOpen(false)}>
              Log in
            </Link>
            <Button asChild>
              <Link href="/signup" onClick={() => setOpen(false)}>
                Sign up
              </Link>
            </Button>
          </nav>
        </div>
      ) : null}
    </header>
  );
}
