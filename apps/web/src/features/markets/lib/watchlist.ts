import { DEFAULT_WATCHLIST } from "@/lib/market/types";

export const WATCHLIST_KEY = "cryptonova.markets.watchlist.v1";
export const FAVORITES_KEY = "cryptonova.markets.favorites.v1";
export const SYMBOL_RE = /^[A-Z0-9]{2,16}USDT$/;

export function normalizeSymbol(raw: string): string | null {
  const s = raw.trim().toUpperCase().replace(/[\s/-]/g, "");
  const full = s.endsWith("USDT") ? s : `${s}USDT`;
  return SYMBOL_RE.test(full) ? full : null;
}

export function readList(key: string, fallback: readonly string[]): string[] {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return [...fallback];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [...fallback];
    const clean = parsed.map(String).filter((s) => SYMBOL_RE.test(s));
    return clean.length ? Array.from(new Set(clean)) : [...fallback];
  } catch {
    return [...fallback];
  }
}

export function writeList(key: string, list: readonly string[]): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(Array.from(new Set(list)).slice(0, 24)));
  } catch {
    /* storage unavailable */
  }
}

export function defaultWatchlist(): string[] {
  return [...DEFAULT_WATCHLIST];
}
