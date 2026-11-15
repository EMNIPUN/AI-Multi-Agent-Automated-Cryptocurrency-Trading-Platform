/**
 * Decimal-string formatting for financial values.
 *
 * Backend DTOs ship decimals as strings (e.g. "1234.56789"). These helpers
 * format them without round-tripping through `Number` where precision matters,
 * so quantities such as "0.00000123" or "12345678.12345678" render exactly.
 */

export type DecimalTone = "profit" | "loss" | "neutral";

const DECIMAL_RE = /^\s*([+-])?(\d+)(?:\.(\d+))?\s*$/;

export type ParsedDecimal = {
  negative: boolean;
  integer: string;
  fraction: string;
  isZero: boolean;
};

/** Parse a decimal string (or number) into sign / integer / fraction parts. */
export function parseDecimal(value: unknown): ParsedDecimal | null {
  if (value === null || value === undefined || value === "" || typeof value === "boolean") return null;
  let text: string;
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return null;
    // Avoid exponent notation for small/large numbers.
    text = Math.abs(value) < 1e-6 || Math.abs(value) >= 1e21 ? value.toFixed(12) : String(value);
  } else {
    text = String(value);
  }
  const match = DECIMAL_RE.exec(text);
  if (!match) {
    const n = Number(text);
    if (!Number.isFinite(n)) return null;
    return parseDecimal(n);
  }
  const [, sign, integer, fraction = ""] = match;
  const isZero = /^0*$/.test(integer) && /^0*$/.test(fraction);
  return {
    negative: sign === "-" && !isZero,
    integer: integer.replace(/^0+(?=\d)/, ""),
    fraction,
    isZero,
  };
}

function groupThousands(integer: string): string {
  return integer.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

/** Round a fraction string to `digits` places using half-up on the string. */
function roundFraction(integer: string, fraction: string, digits: number): { integer: string; fraction: string } {
  if (fraction.length <= digits) {
    return { integer, fraction: fraction.padEnd(digits, "0") };
  }
  const keep = fraction.slice(0, digits);
  const next = fraction.charCodeAt(digits) - 48;
  if (next < 5) return { integer, fraction: keep };
  // Carry the rounding through the kept digits and into the integer part.
  const digitsArr = (integer + keep).split("").map((c) => c.charCodeAt(0) - 48);
  let i = digitsArr.length - 1;
  while (i >= 0) {
    if (digitsArr[i] === 9) {
      digitsArr[i] = 0;
      i -= 1;
    } else {
      digitsArr[i] += 1;
      break;
    }
  }
  if (i < 0) digitsArr.unshift(1);
  const joined = digitsArr.join("");
  const splitAt = joined.length - digits;
  return {
    integer: joined.slice(0, splitAt) || "0",
    fraction: joined.slice(splitAt),
  };
}

export type FormatDecimalOptions = {
  /** Fixed number of fraction digits. When omitted, the source precision is kept (trimmed). */
  digits?: number;
  /** Maximum fraction digits when `digits` is omitted. */
  maxDigits?: number;
  /** Trim trailing zeros from the fraction. */
  trim?: boolean;
  /** Prefix positive numbers with "+". */
  sign?: boolean;
  /** Thousands grouping (default true). */
  grouping?: boolean;
  /** Text shown for null/invalid values. */
  fallback?: string;
};

/** Format a decimal string/number for display. Never throws. */
export function formatDecimal(value: unknown, options: FormatDecimalOptions = {}): string {
  const parsed = parseDecimal(value);
  if (!parsed) return options.fallback ?? "—";
  const { digits, maxDigits, trim = digits === undefined, sign = false, grouping = true } = options;
  let integer = parsed.integer;
  let fraction = parsed.fraction;
  if (digits !== undefined) {
    ({ integer, fraction } = roundFraction(integer, fraction, Math.max(0, digits)));
  } else if (maxDigits !== undefined && fraction.length > maxDigits) {
    ({ integer, fraction } = roundFraction(integer, fraction, Math.max(0, maxDigits)));
  }
  if (trim) fraction = fraction.replace(/0+$/, "");
  const body = `${grouping ? groupThousands(integer) : integer}${fraction ? `.${fraction}` : ""}`;
  const zero = /^0*$/.test(integer) && /^0*$/.test(fraction);
  if (parsed.negative && !zero) return `-${body}`;
  if (sign && !zero) return `+${body}`;
  return body;
}

/** Money with a fixed 2 digits (or more for sub-dollar precision). */
export function formatMoney(value: unknown, digits = 2, options: Omit<FormatDecimalOptions, "digits"> = {}): string {
  return formatDecimal(value, { digits, trim: false, ...options });
}

/** Quantity formatting keeps source precision, trimmed, capped at 8 digits. */
export function formatQuantity(value: unknown, maxDigits = 8): string {
  return formatDecimal(value, { maxDigits, trim: true });
}

/** Price formatting picks precision from magnitude when none is given. */
export function formatPrice(value: unknown, digits?: number): string {
  const parsed = parseDecimal(value);
  if (!parsed) return "—";
  if (digits !== undefined) return formatDecimal(value, { digits, trim: false });
  const magnitude = parsed.integer.replace(/^0+/, "").length;
  const auto = magnitude >= 5 ? 1 : magnitude >= 3 ? 2 : magnitude >= 1 ? 4 : 6;
  return formatDecimal(value, { digits: auto, trim: false });
}

/** Percent from a fraction string ("0.0123" → "1.23%"). */
export function formatFractionPercent(value: unknown, digits = 2, fallback = "—"): string {
  const n = toNumber(value);
  if (n === null) return fallback;
  return `${(n * 100).toFixed(digits)}%`;
}

/** Percent from an already-percent number (12.3 → "12.30%"). */
export function formatPercent(value: unknown, digits = 2, fallback = "—"): string {
  const n = toNumber(value);
  if (n === null) return fallback;
  return `${n.toFixed(digits)}%`;
}

/** Signed tone for PnL-style values. Zero and unknown are neutral. */
export function decimalTone(value: unknown): DecimalTone {
  const parsed = parseDecimal(value);
  if (!parsed || parsed.isZero) return "neutral";
  return parsed.negative ? "loss" : "profit";
}

/** Safe numeric coercion for math (charts, ratios) — not for display precision. */
export function toNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === "" || typeof value === "boolean") return null;
  const n = typeof value === "number" ? value : Number(String(value).trim());
  return Number.isFinite(n) ? n : null;
}

/** Compact large numbers for axis labels / volume (1.2M). Display-only. */
export function formatCompact(value: unknown, digits = 1): string {
  const n = toNumber(value);
  if (n === null) return "—";
  const abs = Math.abs(n);
  if (abs >= 1e9) return `${(n / 1e9).toFixed(digits)}B`;
  if (abs >= 1e6) return `${(n / 1e6).toFixed(digits)}M`;
  if (abs >= 1e3) return `${(n / 1e3).toFixed(digits)}K`;
  return n.toFixed(abs < 1 ? 4 : digits);
}
