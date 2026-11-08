import Image from "next/image";

import { cn } from "@/lib/utils";

/** Theme-aligned emblem (C + amber nova ring + candles) — no wordmark. */
const MARK_SRC = "/brand/cryptonova-mark.png";
/** Horizontal mark + CryptoNova wordmark for hero / marketing surfaces. */
const LOGO_SRC = "/brand/cryptonova-logo.png";

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
      width={1024}
      height={1024}
      priority={priority}
      className={cn("h-auto w-full object-contain", className)}
    />
  );
}

export function CryptoNovaWordmark({
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
      src={LOGO_SRC}
      alt={alt}
      width={1280}
      height={720}
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
