"use client";

import Link from "next/link";
import { motion } from "motion/react";
import type { ReactNode } from "react";

import { CryptoNovaMark } from "@/components/brand/CryptoNovaLogo";
import { BorderBeam } from "@/components/magicui/border-beam";
import { Particles } from "@/components/magicui/particles";

export function AuthShell({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden px-4 py-10">
      <div aria-hidden className="pointer-events-none absolute inset-0 horizon-glow opacity-80" />
      <Particles className="opacity-50" quantity={60} />

      <motion.div
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: "easeOut" }}
        className="relative z-10 w-full max-w-[420px]"
      >
        <div className="mb-8 flex flex-col items-center text-center">
          <Link href="/" className="mb-4 block w-16" aria-label="CryptoNova home">
            <CryptoNovaMark priority className="h-16 w-16" />
          </Link>
          <p className="text-2xl font-medium tracking-tight text-white/90">CryptoNova</p>
          <p className="mt-1 text-xs uppercase tracking-[0.18em] text-amber-200/70">
            Intelligent Trading. Disciplined Execution.
          </p>
        </div>

        <div className="relative overflow-hidden rounded-2xl border border-white/10 bg-white/[0.03] p-6 shadow-[var(--panel-shadow)] backdrop-blur-xl md:p-7">
          <BorderBeam size={180} duration={10} colorFrom="#f59e0b" colorTo="#ffffff" />
          <div className="mb-6">
            <h1 className="text-metallic text-xl font-medium tracking-tight md:text-2xl">
              {title}
            </h1>
            <p className="mt-1.5 text-sm text-muted-foreground">{subtitle}</p>
          </div>
          {children}
        </div>

        {footer ? (
          <div className="mt-5 text-center text-sm text-muted-foreground">{footer}</div>
        ) : null}
      </motion.div>
    </div>
  );
}
