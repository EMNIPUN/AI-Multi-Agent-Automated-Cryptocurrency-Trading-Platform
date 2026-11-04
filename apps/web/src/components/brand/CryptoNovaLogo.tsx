import Image from "next/image";

import { cn } from "@/lib/utils";

/** Cropped emblem only (C + ring + candles + bot) — no wordmark. */
const MARK_SRC = "/brand/cryptonova-mark.png";

export function CryptoNovaMark({
  className,
  priority = false,
  alt = "CryptoNova",
}: {
  className?: string;
  priority?: boolean;
  alt?: string;
}) {
  return (
    <Image
      src={MARK_SRC}
      alt={alt}
      width={817}
      height={817}
      priority={priority}
      className={cn("h-auto w-full object-contain", className)}
    />
  );
}

/** @deprecated Prefer CryptoNovaMark — same cropped emblem. */
export function CryptoNovaLogo(props: {
  className?: string;
  priority?: boolean;
  alt?: string;
}) {
  return <CryptoNovaMark {...props} />;
}
