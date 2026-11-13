import type { Metadata } from "next";
import { IBM_Plex_Mono, Plus_Jakarta_Sans } from "next/font/google";

import { AuthProvider } from "@/components/auth/AuthProvider";
import { AppShell } from "@/components/layout/AppShell";
import { ThemeSync } from "@/components/layout/ThemeSync";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";

import "./globals.css";

/** Magic UI startup-template style: clean geometric sans (not Inter). */
const sans = Plus_Jakarta_Sans({
  subsets: ["latin"],
  variable: "--font-sans",
  weight: ["400", "500", "600", "700"],
});

const display = Plus_Jakarta_Sans({
  subsets: ["latin"],
  variable: "--font-display",
  weight: ["500", "600", "700"],
});

const mono = IBM_Plex_Mono({
  weight: ["400", "500"],
  subsets: ["latin"],
  variable: "--font-mono",
});

export const metadata: Metadata = {
  title: "CryptoNova — Intelligent Trading. Disciplined Execution.",
  description:
    "Multi-agent cryptocurrency trading platform. Paper-first, SAMPLE-safe, with public markets and gated private reads.",
  icons: {
    icon: "/brand/cryptonova-mark.png",
    apple: "/brand/cryptonova-mark.png",
  },
};

const THEME_BOOT = `(function(){try{var t=localStorage.getItem("cryptonova.theme.v3");var light=t==="light";var d=document.documentElement;d.classList.toggle("light",light);d.classList.toggle("dark",!light);var n=localStorage.getItem("cryptonova.density.v1");if(n==="compact"||n==="comfortable")d.dataset.density=n;}catch(e){}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`dark ${display.variable} ${sans.variable} ${mono.variable}`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT }} />
      </head>
      <body className="font-sans antialiased">
        <TooltipProvider>
          <ThemeSync />
          <AuthProvider>
            <AppShell>{children}</AppShell>
            <Toaster richColors closeButton position="top-right" />
          </AuthProvider>
        </TooltipProvider>
      </body>
    </html>
  );
}
