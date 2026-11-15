import type { ReactNode } from "react";

import { decimalTone, formatDecimal, type FormatDecimalOptions } from "@/lib/formatting/decimal";
import { cn } from "@/lib/utils";

export type FinancialValueProps = {
  /** Decimal string or number from the API. Null/invalid renders the fallback. */
  value: unknown;
  /** Fixed fraction digits. Omit to keep source precision (trimmed). */
  digits?: number;
  /** Cap fraction digits when `digits` is omitted. */
  maxDigits?: number;
  /** Currency or unit label rendered after the number. */
  unit?: string;
  /** Colour by sign (profit/loss). Zero stays neutral. */
  signed?: boolean;
  /** Prefix "+" on positive values (implies signed colouring). */
  showPlus?: boolean;
  /** Visual size. */
  size?: "xs" | "sm" | "md" | "lg" | "xl";
  /** Fallback text for missing values. */
  fallback?: string;
  /** Extra classes on the wrapper span. */
  className?: string;
  /** Replace the leading content (e.g. an icon). */
  prefix?: ReactNode;
  /** Accessible label override. */
  "aria-label"?: string;
};

const SIZE: Record<NonNullable<FinancialValueProps["size"]>, string> = {
  xs: "text-xs",
  sm: "text-sm",
  md: "text-base",
  lg: "text-xl md:text-2xl",
  xl: "text-2xl md:text-[1.75rem]",
};

const UNIT_SIZE: Record<NonNullable<FinancialValueProps["size"]>, string> = {
  xs: "text-[10px]",
  sm: "text-[11px]",
  md: "text-xs",
  lg: "text-sm",
  xl: "text-sm",
};

/**
 * Precise financial number: mono, tabular, optional sign colour and unit.
 * Formats decimal strings without float precision loss.
 */
export function FinancialValue({
  value,
  digits,
  maxDigits,
  unit,
  signed = false,
  showPlus = false,
  size = "md",
  fallback = "—",
  className,
  prefix,
  "aria-label": ariaLabel,
}: FinancialValueProps) {
  const opts: FormatDecimalOptions = { digits, maxDigits, sign: showPlus, fallback };
  const text = formatDecimal(value, opts);
  const tone = signed || showPlus ? decimalTone(value) : "neutral";
  const missing = text === fallback;
  return (
    <span
      className={cn(
        "inline-flex items-baseline gap-1 font-mono tabular-nums tracking-tight",
        SIZE[size],
        missing ? "text-muted-foreground" : tone === "profit" ? "text-profit" : tone === "loss" ? "text-loss" : "text-foreground",
        className,
      )}
      aria-label={ariaLabel}
    >
      {prefix}
      <span>{text}</span>
      {unit && !missing ? <span className={cn("font-sans text-muted-foreground", UNIT_SIZE[size])}>{unit}</span> : null}
    </span>
  );
}
