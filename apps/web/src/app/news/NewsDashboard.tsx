"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  BellOff,
  Database,
  ExternalLink,
  Newspaper,
  Radio,
  RefreshCw,
  ShieldAlert,
} from "lucide-react";

import {
  DataFreshnessBadge,
  EmptyState,
  ErrorState,
  LoadingState,
  StatusBadge,
  type StatusTone,
} from "@/components/design-system";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  NEWS_ADVISORY_LABEL,
  filterNewsRows,
  formatNewsTime,
  friendlySchedulerNote,
  isStaleNews,
  newsViewState,
  severityBadge,
  type NewsFilters,
} from "@/lib/news/news-format";
import { cn } from "@/lib/utils";

type AnyRow = Record<string, unknown>;

type NewsListRow = {
  symbols?: string[];
  assets?: string[];
  asset_hints?: string[];
  severity?: string;
  category?: string;
  verification?: string;
  published_at_ms?: number | null;
  available_at_ms?: number | null;
  detected_at_ms?: number | null;
  first_observed_at_ms?: number | null;
  status?: string;
  alert_id?: string;
  event_id?: string;
  headline?: string;
  sentiment?: string;
  warnings?: string[];
  freshness?: string;
  explanation?: string;
  summary?: string;
  source_url?: string;
};

const EMPTY_FILTERS: NewsFilters = {
  symbol: "ALL",
  severity: "ALL",
  category: "ALL",
  verification: "ALL",
  fromMs: null,
  toMs: null,
};

const SYMBOL_CHIPS = [
  { value: "ALL", label: "All" },
  { value: "BTCUSDT", label: "BTC" },
  { value: "ETHUSDT", label: "ETH" },
  { value: "SOLUSDT", label: "SOL" },
] as const;

const SEVERITIES = ["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL", "UNKNOWN"] as const;
const CATEGORIES = [
  "ALL",
  "SECURITY_INCIDENT",
  "NETWORK_OUTAGE",
  "REGULATORY",
  "EXCHANGE_OPS",
  "STABLECOIN",
  "PROTOCOL_EXPLOIT",
  "DELISTING",
  "GENERAL",
] as const;
const VERIFICATIONS = [
  "ALL",
  "OFFICIAL_SOURCE",
  "CORROBORATED",
  "SINGLE_SOURCE",
  "UNVERIFIED",
  "UNKNOWN",
] as const;

function labelCategory(value: string) {
  if (value === "ALL") return "All categories";
  return value
    .toLowerCase()
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function labelVerification(value: string) {
  if (value === "ALL") return "All sources";
  return value
    .toLowerCase()
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function labelSeverity(value: string) {
  if (value === "ALL") return "All severities";
  return value.charAt(0) + value.slice(1).toLowerCase();
}

function storageLabel(kind: unknown) {
  const raw = String(kind || "unknown");
  if (raw.includes("supabase")) return "Cloud database";
  if (raw.includes("sqlite")) return "Local database";
  if (raw.includes("postgres")) return "Postgres";
  return raw.replace(/_/g, " ");
}

async function readJson(path: string) {
  const res = await fetch(path, { cache: "no-store" });
  const body = (await res.json().catch(() => ({}))) as AnyRow;
  return { res, body };
}

function StatusTile({
  icon: Icon,
  label,
  value,
  tone,
  hint,
}: {
  icon: typeof Radio;
  label: string;
  value: string;
  tone: StatusTone;
  hint?: string;
}) {
  return (
    <div className="cn-metric flex min-h-[5.5rem] flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <span className="inline-flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          <Icon className="h-3.5 w-3.5" aria-hidden />
          {label}
        </span>
        <StatusBadge label={value} tone={tone} />
      </div>
      {hint ? <p className="text-xs leading-relaxed text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

export function NewsDashboard() {
  const [loading, setLoading] = useState(true);
  const [disabled, setDisabled] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<AnyRow | null>(null);
  const [articles, setArticles] = useState<AnyRow[]>([]);
  const [events, setEvents] = useState<AnyRow[]>([]);
  const [alerts, setAlerts] = useState<AnyRow[]>([]);
  const [health, setHealth] = useState<AnyRow[]>([]);
  const [filters, setFilters] = useState<NewsFilters>(EMPTY_FILTERS);
  const [selected, setSelected] = useState<NewsListRow | null>(null);
  const [ackNote, setAckNote] = useState<string | null>(null);
  const [showTech, setShowTech] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    setAckNote(null);
    try {
      const st = await readJson("/api/news/status");
      if (st.res.status === 503 || st.body.enabled === false) {
        setDisabled(true);
        setStatus(st.body);
        setArticles([]);
        setEvents([]);
        setAlerts([]);
        setHealth([]);
        setLoading(false);
        return;
      }
      if (!st.res.ok) {
        setError("Could not load news status from the API.");
        setLoading(false);
        return;
      }
      setDisabled(false);
      setStatus(st.body);
      const [arts, evs, als, hp] = await Promise.all([
        readJson("/api/news/articles?limit=50"),
        readJson("/api/news/events?limit=50"),
        readJson("/api/news/alerts?limit=50"),
        readJson("/api/news/providers/health"),
      ]);
      setArticles(Array.isArray(arts.body.items) ? (arts.body.items as AnyRow[]) : []);
      setEvents(Array.isArray(evs.body.items) ? (evs.body.items as AnyRow[]) : []);
      setAlerts(
        als.body.enabled === false || !Array.isArray(als.body.items)
          ? []
          : (als.body.items as AnyRow[]),
      );
      setHealth(Array.isArray(hp.body.items) ? (hp.body.items as AnyRow[]) : []);
      if (!arts.res.ok && arts.res.status !== 503) setError("Article feed is temporarily unavailable.");
    } catch {
      setError("News API is unreachable. Check that the backend is running.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const filteredEvents = useMemo(
    () => filterNewsRows(events as NewsListRow[], filters),
    [events, filters],
  );
  const filteredAlerts = useMemo(
    () => filterNewsRows(alerts as NewsListRow[], filters),
    [alerts, filters],
  );
  const stale = [...filteredEvents, ...filteredAlerts].some((row) => isStaleNews(row));
  const view = newsViewState({
    loading,
    disabled,
    error: Boolean(error),
    count: filteredEvents.length + filteredAlerts.length + articles.length,
    stale,
  });

  const scheduler = friendlySchedulerNote(status?.scheduler_note);
  const collectionOn = Boolean(status?.collection_enabled);
  const autoOn = Boolean(status?.auto_collection_enabled);
  const storageOk = Boolean(status?.storage_available);
  const alertsOn = Boolean(status?.alert_engine_enabled);
  const telegramOn = Boolean(status?.telegram_enabled);

  async function acknowledge(alertId: string) {
    setAckNote(null);
    const res = await fetch(`/api/news/alerts/${alertId}/acknowledge`, { method: "POST" });
    if (!res.ok) {
      setAckNote("Could not acknowledge this alert. The alert engine may be off.");
      return;
    }
    setAckNote("Alert marked as acknowledged in-app.");
    await load();
  }

  const filtersActive =
    filters.symbol !== "ALL" ||
    filters.severity !== "ALL" ||
    filters.category !== "ALL" ||
    filters.verification !== "ALL" ||
    filters.fromMs != null ||
    filters.toMs != null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border bg-muted/30 px-4 py-3">
        <div className="min-w-0">
          <p className="text-sm font-medium text-foreground">Advisory feed only</p>
          <p className="text-xs text-muted-foreground">
            {NEWS_ADVISORY_LABEL}. Never places orders or changes strategy.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {view === "stale" ? <DataFreshnessBadge at={Date.now() - 120_000} label="Delayed" /> : null}
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="rounded-full"
            onClick={() => void load()}
            disabled={loading}
          >
            <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
            Refresh
          </Button>
        </div>
      </div>

      {view === "loading" ? <LoadingState label="Loading news…" rows={2} /> : null}
      {view === "disabled" ? (
        <EmptyState
          title="News API is turned off"
          badge="Unavailable"
          description="An operator must enable the news read API on the server before articles appear here."
          action={
            <Button type="button" variant="outline" size="sm" onClick={() => void load()}>
              Retry
            </Button>
          }
        />
      ) : null}
      {view === "error" && error ? (
        <ErrorState title="News unavailable" description={error} onRetry={() => void load()} />
      ) : null}

      {view !== "loading" && view !== "disabled" ? (
        <>
          <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <StatusTile
              icon={Radio}
              label="Collection"
              value={collectionOn ? (autoOn ? "Auto" : "Manual") : "Off"}
              tone={collectionOn ? (autoOn ? "ok" : "warn") : "danger"}
              hint={
                collectionOn
                  ? autoOn
                    ? "Server collects news automatically."
                    : "Waiting for a manual collect run."
                  : "Collection is disabled on the server."
              }
            />
            <StatusTile
              icon={Database}
              label="Storage"
              value={storageOk ? "Ready" : "Down"}
              tone={storageOk ? "ok" : "danger"}
              hint={`${storageLabel(status?.storage_kind)} · ${storageOk ? "connected" : "not reachable"}`}
            />
            <StatusTile
              icon={alertsOn ? ShieldAlert : BellOff}
              label="Alerts"
              value={alertsOn ? "On" : "Off"}
              tone={alertsOn ? "ok" : "neutral"}
              hint={
                alertsOn
                  ? telegramOn
                    ? "In-app alerts on · Telegram configured"
                    : "In-app alerts on · Telegram not configured"
                  : "Critical alert engine is disabled."
              }
            />
            <StatusTile
              icon={AlertTriangle}
              label="Freshness"
              value={view === "stale" ? "Delayed" : "OK"}
              tone={view === "stale" ? "stale" : "ok"}
              hint={scheduler.summary}
            />
          </section>

          {scheduler.detail ? (
            <details
              className="rounded-xl border border-border bg-card px-4 py-3 text-sm"
              open={showTech}
              onToggle={(e) => setShowTech((e.target as HTMLDetailsElement).open)}
            >
              <summary className="cursor-pointer select-none text-muted-foreground hover:text-foreground">
                Technical details for operators
              </summary>
              <p className="mt-2 font-mono text-xs leading-relaxed text-muted-foreground whitespace-pre-wrap">
                {scheduler.detail}
              </p>
            </details>
          ) : null}

          <section className="cn-panel space-y-4 p-4">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2 className="text-sm font-medium text-foreground">Filters</h2>
                <p className="text-xs text-muted-foreground">Narrow the feed by coin, severity, and date.</p>
              </div>
              {filtersActive ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="rounded-full"
                  onClick={() => setFilters(EMPTY_FILTERS)}
                >
                  Clear filters
                </Button>
              ) : null}
            </div>

            <div className="flex flex-wrap gap-2" role="group" aria-label="Coin filter">
              {SYMBOL_CHIPS.map((chip) => (
                <Button
                  key={chip.value}
                  type="button"
                  size="sm"
                  variant={filters.symbol === chip.value ? "brand" : "outline"}
                  className="rounded-full"
                  onClick={() => setFilters((f) => ({ ...f, symbol: chip.value }))}
                >
                  {chip.label}
                </Button>
              ))}
            </div>

            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              <div className="space-y-1.5">
                <Label htmlFor="news-severity">Severity</Label>
                <Select
                  value={filters.severity}
                  onValueChange={(severity) => setFilters((f) => ({ ...f, severity }))}
                >
                  <SelectTrigger id="news-severity" className="bg-background">
                    <SelectValue placeholder="Severity" />
                  </SelectTrigger>
                  <SelectContent>
                    {SEVERITIES.map((s) => (
                      <SelectItem key={s} value={s}>
                        {labelSeverity(s)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="news-category">Category</Label>
                <Select
                  value={filters.category}
                  onValueChange={(category) => setFilters((f) => ({ ...f, category }))}
                >
                  <SelectTrigger id="news-category" className="bg-background">
                    <SelectValue placeholder="Category" />
                  </SelectTrigger>
                  <SelectContent>
                    {CATEGORIES.map((s) => (
                      <SelectItem key={s} value={s}>
                        {labelCategory(s)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="news-verification">Source quality</Label>
                <Select
                  value={filters.verification}
                  onValueChange={(verification) => setFilters((f) => ({ ...f, verification }))}
                >
                  <SelectTrigger id="news-verification" className="bg-background">
                    <SelectValue placeholder="Source quality" />
                  </SelectTrigger>
                  <SelectContent>
                    {VERIFICATIONS.map((s) => (
                      <SelectItem key={s} value={s}>
                        {labelVerification(s)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="news-from">From</Label>
                <input
                  id="news-from"
                  type="date"
                  className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm"
                  onChange={(e) =>
                    setFilters((f) => ({
                      ...f,
                      fromMs: e.target.value ? Date.parse(`${e.target.value}T00:00:00Z`) : null,
                    }))
                  }
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="news-to">To</Label>
                <input
                  id="news-to"
                  type="date"
                  className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm"
                  onChange={(e) =>
                    setFilters((f) => ({
                      ...f,
                      toMs: e.target.value ? Date.parse(`${e.target.value}T23:59:59Z`) : null,
                    }))
                  }
                />
              </div>
            </div>
          </section>

          {view === "empty" ? (
            <EmptyState
              icon={<Newspaper className="h-4 w-4 text-muted-foreground" />}
              title="No news stored yet"
              badge="Empty"
              description="The API is online but returned no articles or alerts. Run a manual collect, or wait until auto-collection is enabled."
              action={
                <Button type="button" variant="outline" size="sm" onClick={() => void load()}>
                  Refresh feed
                </Button>
              }
            />
          ) : null}

          <div className="grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
            <section className="cn-panel flex min-h-[22rem] flex-col overflow-hidden">
              <header className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
                <div>
                  <h2 className="text-sm font-medium text-foreground">News feed</h2>
                  <p className="text-xs text-muted-foreground">Latest stored headlines</p>
                </div>
                <Badge variant="outline" className="rounded-full">
                  {articles.length}
                </Badge>
              </header>
              <div className="cn-thin-scroll flex-1 space-y-2 overflow-y-auto p-3">
                {articles.length === 0 ? (
                  <EmptyState
                    title="No headlines"
                    badge="Empty"
                    description="Nothing matched this response. Try clearing filters or refreshing."
                    className="border-0 bg-transparent"
                  />
                ) : (
                  articles.slice(0, 30).map((article) => (
                    <article
                      key={String(article.content_hash || article.url || article.title)}
                      className="rounded-xl border border-border bg-card/60 p-3 transition-colors hover:border-brand/40 hover:bg-muted/40"
                    >
                      <p className="text-sm font-medium leading-snug text-foreground">
                        {String(article.title || "Untitled")}
                      </p>
                      <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                        <span>{String(article.source_name || "Unknown source")}</span>
                        <span aria-hidden>·</span>
                        <span className="font-mono">
                          {(article.asset_hints as string[] | undefined)?.join(", ") || "No coin tag"}
                        </span>
                        <span aria-hidden>·</span>
                        <span>{formatNewsTime(article.published_at_ms as number | null)}</span>
                      </div>
                      {article.url ? (
                        <a
                          className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-brand hover:underline"
                          href={String(article.url)}
                          target="_blank"
                          rel="noreferrer"
                        >
                          Open source
                          <ExternalLink className="h-3 w-3" aria-hidden />
                        </a>
                      ) : null}
                    </article>
                  ))
                )}
              </div>
            </section>

            <section className="cn-panel flex min-h-[22rem] flex-col overflow-hidden">
              <header className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
                <div>
                  <h2 className="text-sm font-medium text-foreground">Critical alerts</h2>
                  <p className="text-xs text-muted-foreground">
                    {alertsOn ? "Filtered in-app alerts" : "Alert engine is currently off"}
                  </p>
                </div>
                <Badge variant="outline" className="rounded-full">
                  {filteredAlerts.length}
                </Badge>
              </header>
              <div className="cn-thin-scroll flex-1 space-y-2 overflow-y-auto p-3">
                {filteredAlerts.length === 0 ? (
                  <EmptyState
                    title={alertsOn ? "No alerts matched" : "Alerts unavailable"}
                    badge={alertsOn ? "Clear" : "Off"}
                    description={
                      alertsOn
                        ? "Nothing matched your filters. Try All coins or clear severity."
                        : "The backend alert engine is disabled, so this list stays empty on purpose."
                    }
                    className="border-0 bg-transparent"
                  />
                ) : (
                  filteredAlerts.map((alert) => (
                    <article
                      key={String(alert.alert_id)}
                      className="rounded-xl border border-border bg-card/60 p-3"
                    >
                      <div className="mb-2 flex flex-wrap gap-1.5">
                        <Badge variant={severityBadge(String(alert.severity))}>
                          {String(alert.severity)}
                        </Badge>
                        <Badge variant="outline" className="rounded-full">
                          {alert.status === "OPEN" ? "Unread" : String(alert.status)}
                        </Badge>
                      </div>
                      <p className="text-sm font-medium leading-snug text-foreground">
                        {String(alert.headline)}
                      </p>
                      <p className="mt-1 text-[11px] text-muted-foreground">
                        {(alert.symbols as string[] | undefined)?.join(", ") || "No symbols"} ·{" "}
                        {formatNewsTime(alert.published_at_ms as number | null)}
                      </p>
                      <div className="mt-3 flex flex-wrap gap-2">
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          className="rounded-full"
                          onClick={() => setSelected(alert)}
                        >
                          Details
                        </Button>
                        {alert.status === "OPEN" ? (
                          <Button
                            type="button"
                            size="sm"
                            variant="brand"
                            className="rounded-full"
                            onClick={() => void acknowledge(String(alert.alert_id))}
                          >
                            Acknowledge
                          </Button>
                        ) : null}
                      </div>
                    </article>
                  ))
                )}
                {ackNote ? <p className="px-1 text-xs text-muted-foreground">{ackNote}</p> : null}
              </div>
            </section>
          </div>

          <section className="cn-panel overflow-hidden">
            <header className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
              <div>
                <h2 className="text-sm font-medium text-foreground">Classified events</h2>
                <p className="text-xs text-muted-foreground">Severity and category from the classifier</p>
              </div>
              <Badge variant="outline" className="rounded-full">
                {filteredEvents.length}
              </Badge>
            </header>
            <div className="cn-thin-scroll max-h-72 space-y-1 overflow-y-auto p-3">
              {filteredEvents.length === 0 ? (
                <p className="px-1 py-6 text-center text-sm text-muted-foreground">No classified events yet.</p>
              ) : (
                filteredEvents.slice(0, 40).map((event) => (
                  <div
                    key={String(event.event_id)}
                    className="flex flex-wrap items-center gap-2 rounded-lg border border-transparent px-2 py-2 text-sm hover:border-border hover:bg-muted/40"
                  >
                    <Badge variant={severityBadge(String(event.severity))}>
                      {String(event.severity || "UNKNOWN")}
                    </Badge>
                    <span className="text-xs text-muted-foreground">
                      {labelCategory(String(event.category || "UNKNOWN"))}
                    </span>
                    {event.sentiment ? (
                      <span className="text-xs text-muted-foreground">{String(event.sentiment)}</span>
                    ) : null}
                    <span className="min-w-0 flex-1 truncate text-foreground">
                      {String(event.headline || "Untitled event")}
                    </span>
                  </div>
                ))
              )}
            </div>
          </section>

          <details className="cn-panel px-4 py-3">
            <summary className="cursor-pointer select-none text-sm font-medium text-foreground">
              Provider health
              <span className="ml-2 text-xs font-normal text-muted-foreground">
                {health.length} check{health.length === 1 ? "" : "s"}
              </span>
            </summary>
            <div className="mt-3 space-y-1.5 text-sm">
              {health.length === 0 ? (
                <p className="text-muted-foreground">No provider health checks stored.</p>
              ) : (
                health.slice(0, 12).map((row, idx) => (
                  <div
                    key={`${String(row.provider_id)}-${idx}`}
                    className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border bg-muted/30 px-3 py-2"
                  >
                    <span className="font-mono text-xs text-foreground">{String(row.provider_id)}</span>
                    <div className="flex items-center gap-2">
                      <StatusBadge label={row.ok ? "OK" : "Error"} tone={row.ok ? "ok" : "danger"} />
                      <span className="text-[11px] text-muted-foreground">
                        {formatNewsTime(row.checked_ms as number)}
                      </span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </details>
        </>
      ) : null}

      <Sheet open={Boolean(selected)} onOpenChange={(open) => !open && setSelected(null)}>
        <SheetContent className="w-full sm:max-w-md">
          <SheetHeader>
            <SheetTitle>Alert detail</SheetTitle>
            <SheetDescription>Advisory context only — not an execution instruction.</SheetDescription>
          </SheetHeader>
          {selected ? (
            <div className="mt-6 space-y-4 text-sm">
              <div className="flex flex-wrap gap-1.5">
                <Badge variant={severityBadge(String(selected.severity))}>
                  {String(selected.severity || "UNKNOWN")}
                </Badge>
                <Badge variant="outline" className="rounded-full">
                  {String(selected.verification || "UNKNOWN")}
                </Badge>
              </div>
              <p className="text-base font-medium leading-snug text-foreground">
                {String(selected.headline)}
              </p>
              <p className="leading-relaxed text-muted-foreground">
                {String(selected.explanation || selected.summary || "No additional explanation stored.")}
              </p>
              <dl className="space-y-2 rounded-xl border border-border bg-muted/30 p-3 text-xs">
                <div className="flex justify-between gap-3">
                  <dt className="text-muted-foreground">Published</dt>
                  <dd className="font-mono text-foreground">
                    {formatNewsTime(selected.published_at_ms)}
                  </dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="text-muted-foreground">Freshness</dt>
                  <dd className="text-foreground">{String(selected.freshness || "unknown")}</dd>
                </div>
              </dl>
              {selected.source_url ? (
                <a
                  className="inline-flex items-center gap-1 font-medium text-brand hover:underline"
                  href={String(selected.source_url)}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open source
                  <ExternalLink className="h-3.5 w-3.5" aria-hidden />
                </a>
              ) : (
                <p className="text-muted-foreground">Source link unavailable</p>
              )}
              <p className="text-xs text-muted-foreground">
                Acknowledging an alert only updates the in-app record. It does not confirm Telegram delivery.
              </p>
            </div>
          ) : null}
        </SheetContent>
      </Sheet>
    </div>
  );
}
