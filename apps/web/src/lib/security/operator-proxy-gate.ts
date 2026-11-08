/** Fail-closed gate for privileged Next.js → FastAPI proxies. */
export function operatorLocalBrowserProxyEnabled(
  env: Record<string, string | undefined> = process.env,
): boolean {
  return env.OPERATOR_LOCAL_BROWSER_PROXY_ENABLED?.trim().toLowerCase() === "true";
}
