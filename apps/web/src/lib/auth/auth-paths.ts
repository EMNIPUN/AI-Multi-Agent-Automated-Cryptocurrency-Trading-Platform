/** Paths that use the minimal Auth chrome (no trading shell). */
export const AUTH_ROUTE_PREFIXES = [
  "/login",
  "/signup",
  "/forgot-password",
  "/reset-password",
] as const;

/** Public marketing surfaces (no trading shell, no RequireAuth). */
export const MARKETING_ROUTE_EXACT = ["/"] as const;

/** App routes that require a Supabase browser session (UI gate only). */
export const PROTECTED_ROUTE_PREFIXES = [
  "/dashboard",
  "/agents",
  "/markets",
  "/portfolio",
  "/positions",
  "/paper",
  "/risk",
  "/analytics",
  "/backtesting",
  "/settings",
  "/notifications",
  "/news",
  "/llm",
] as const;

export function pathStartsWith(pathname: string, prefixes: readonly string[]): boolean {
  return prefixes.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}
