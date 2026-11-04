"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Overview" },
  { href: "/agents/live", label: "Agent Live" },
  { href: "/paper", label: "Paper" },
];

export function SiteNav() {
  const pathname = usePathname();
  return (
    <header className="topnav">
      <div className="brand">CryptoNova</div>
      <nav className="nav-links" aria-label="Primary">
        {LINKS.map((l) => (
          <Link
            key={l.href}
            href={l.href}
            aria-current={pathname === l.href ? "page" : undefined}
          >
            {l.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}
