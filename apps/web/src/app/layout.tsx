import type { Metadata } from "next";
import { IBM_Plex_Mono, Plus_Jakarta_Sans } from "next/font/google";

import { AuthProvider } from "@/components/auth/AuthProvider";
import { AppShell } from "@/components/layout/AppShell";
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

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`dark ${display.variable} ${sans.variable} ${mono.variable}`}>
      <body className="font-sans antialiased">
        <TooltipProvider>
          <AuthProvider>
            <AppShell>{children}</AppShell>
            <Toaster richColors closeButton position="top-right" />
          </AuthProvider>
        </TooltipProvider>
      </body>
    </html>
  );
}
