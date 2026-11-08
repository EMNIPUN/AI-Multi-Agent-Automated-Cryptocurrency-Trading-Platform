export function formatLocalAndUtc(iso: string | null | undefined): { local: string; utc: string } {
  if (!iso) return { local: "unavailable", utc: "unavailable" };
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return { local: iso, utc: iso };
  return {
    local: date.toLocaleString(),
    utc: date.toISOString(),
  };
}

export function formatAge(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "n/a";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "n/a";
  const sec = Math.max(0, Math.floor((now - t) / 1000));
  if (sec < 60) return `${sec}s ago`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
  return `${Math.floor(sec / 3600)}h ago`;
}
