"use client";

import { useEffect, useMemo, useState } from "react";

import { LogoLoader } from "@/components/brand/LogoLoader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  NEWS_ADVISORY_LABEL,
  filterNewsRows,
  formatMs,
  isStaleNews,
  newsViewState,
  severityBadge,
  type NewsFilters,
} from "@/lib/news/news-format";

type AnyRow = Record<string, unknown>;

const EMPTY_FILTERS: NewsFilters = {
  symbol: "ALL",
  severity: "ALL",
  category: "ALL",
  verification: "ALL",
  fromMs: null,
  toMs: null,
};

async function readJson(path: string) {
  const res = await fetch(path, { cache: "no-store" });
  const body = (await res.json().catch(() => ({}))) as AnyRow;
  return { res, body };
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
  const [selected, setSelected] = useState<AnyRow | null>(null);
  const [ackNote, setAckNote] = useState<string | null>(null);

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
        setError("News status failed");
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
      setAlerts(als.body.enabled === false || !Array.isArray(als.body.items) ? [] : (als.body.items as AnyRow[]));
      setHealth(Array.isArray(hp.body.items) ? (hp.body.items as AnyRow[]) : []);
      if (!arts.res.ok && arts.res.status !== 503) setError("Article feed unavailable");
    } catch {
      setError("News API unreachable");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const filteredEvents = useMemo(
    () => filterNewsRows(events as never[], filters),
    [events, filters],
  );
  const filteredAlerts = useMemo(
    () => filterNewsRows(alerts as never[], filters),
    [alerts, filters],
  );
  const stale = [...filteredEvents, ...filteredAlerts].some((row) => isStaleNews(row as never));
  const view = newsViewState({
    loading,
    disabled,
    error: Boolean(error),
    count: filteredEvents.length + filteredAlerts.length + articles.length,
    stale,
  });

  async function acknowledge(alertId: string) {
    setAckNote(null);
    const res = await fetch(`/api/news/alerts/${alertId}/acknowledge`, { method: "POST" });
    if (!res.ok) {
      setAckNote("Acknowledge failed. Alert engine may be disabled or storage is unavailable.");
      return;
    }
    setAckNote("Alert acknowledged. No external delivery was implied.");
    await load();
  }

  return (
    <div className="space-y-5 pb-10">
      <div>
        <h1 className="text-2xl font-medium tracking-tight">News</h1>
        <p className="text-sm text-white/55">
          {NEWS_ADVISORY_LABEL}. This page does not place orders or change strategy.
        </p>
      </div>

      {view === "loading" ? <LogoLoader label="Loading news…" /> : null}
      {view === "disabled" ? (
        <Card>
          <CardHeader>
            <CardTitle>News read API is off</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-white/70">
            Set NEWS_READ_API_ENABLED=true on the local API to load stored articles. No sample alerts are shown.
          </CardContent>
        </Card>
      ) : null}
      {view === "error" ? (
        <Card>
          <CardHeader>
            <CardTitle>News unavailable</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-white/70">{error}</CardContent>
        </Card>
      ) : null}

      <section className="grid gap-3 md:grid-cols-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Collection</CardTitle>
          </CardHeader>
          <CardContent className="text-sm">
            {status?.collection_enabled ? "Enabled" : "Disabled"} · auto{" "}
            {status?.auto_collection_enabled ? "on" : "off (manual)"}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Storage</CardTitle>
          </CardHeader>
          <CardContent className="text-sm">
            {String(status?.storage_kind || "unknown")} ·{" "}
            {status?.storage_available ? "available" : "unavailable"}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Alert engine</CardTitle>
          </CardHeader>
          <CardContent className="text-sm">
            {status?.alert_engine_enabled ? "Enabled" : "Disabled"} · Telegram{" "}
            {status?.telegram_enabled ? "configured" : "off"}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Freshness</CardTitle>
          </CardHeader>
          <CardContent className="text-sm">
            {view === "stale" ? "Stale or delayed feed" : "No stale flag on the loaded page"}
            <p className="mt-1 text-xs text-white/45">{String(status?.scheduler_note || "")}</p>
          </CardContent>
        </Card>
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Filters</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          {["ALL", "BTCUSDT", "ETHUSDT", "SOLUSDT"].map((symbol) => (
            <Button
              key={symbol}
              type="button"
              variant={filters.symbol === symbol ? "default" : "outline"}
              onClick={() => setFilters((f) => ({ ...f, symbol }))}
            >
              {symbol === "ALL" ? "All coins" : symbol.replace("USDT", "")}
            </Button>
          ))}
          <select
            className="rounded-md border border-white/15 bg-transparent px-2 py-1 text-sm"
            value={filters.severity}
            onChange={(e) => setFilters((f) => ({ ...f, severity: e.target.value }))}
            aria-label="Severity"
          >
            {["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL", "UNKNOWN"].map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
          <select
            className="rounded-md border border-white/15 bg-transparent px-2 py-1 text-sm"
            value={filters.category}
            onChange={(e) => setFilters((f) => ({ ...f, category: e.target.value }))}
            aria-label="Category"
          >
            {[
              "ALL",
              "SECURITY_INCIDENT",
              "NETWORK_OUTAGE",
              "REGULATORY",
              "EXCHANGE_OPS",
              "STABLECOIN",
              "PROTOCOL_EXPLOIT",
              "DELISTING",
              "GENERAL",
            ].map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
          <select
            className="rounded-md border border-white/15 bg-transparent px-2 py-1 text-sm"
            value={filters.verification}
            onChange={(e) => setFilters((f) => ({ ...f, verification: e.target.value }))}
            aria-label="Verification"
          >
            {["ALL", "OFFICIAL_SOURCE", "CORROBORATED", "SINGLE_SOURCE", "UNVERIFIED", "UNKNOWN"].map(
              (s) => (
                <option key={s}>{s}</option>
              ),
            )}
          </select>
          <input
            type="date"
            aria-label="From date"
            className="rounded-md border border-white/15 bg-transparent px-2 py-1 text-sm"
            onChange={(e) =>
              setFilters((f) => ({
                ...f,
                fromMs: e.target.value ? Date.parse(`${e.target.value}T00:00:00Z`) : null,
              }))
            }
          />
          <input
            type="date"
            aria-label="To date"
            className="rounded-md border border-white/15 bg-transparent px-2 py-1 text-sm"
            onChange={(e) =>
              setFilters((f) => ({
                ...f,
                toMs: e.target.value ? Date.parse(`${e.target.value}T23:59:59Z`) : null,
              }))
            }
          />
        </CardContent>
      </Card>

      {view === "empty" ? (
        <Card>
          <CardHeader>
            <CardTitle>No stored news yet</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-white/70">
            The read API is on and returned no articles, events, or alerts. Collection stays manual unless auto
            collection is explicitly enabled.
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>News feed</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {articles.length === 0 ? <p className="text-sm text-white/50">No articles in this response.</p> : null}
            {articles.slice(0, 20).map((article) => (
              <article key={String(article.content_hash)} className="rounded-xl border border-white/10 p-3">
                <p className="text-sm font-medium">{String(article.title || "Untitled")}</p>
                <p className="text-xs text-white/50">
                  {String(article.source_name || "unknown source")} ·{" "}
                  {(article.asset_hints as string[] | undefined)?.join(", ") || "no coin tag"}
                </p>
                <p className="text-xs text-white/40">Published {formatMs(article.published_at_ms as number | null)}</p>
                {article.url ? (
                  <a className="text-xs underline" href={String(article.url)} target="_blank" rel="noreferrer">
                    Source
                  </a>
                ) : null}
              </article>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Critical alerts</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {filteredAlerts.length === 0 ? (
              <p className="text-sm text-white/50">No alerts matched. Disabled engines return an empty real list.</p>
            ) : null}
            {filteredAlerts.map((alert) => (
              <article key={String(alert.alert_id)} className="rounded-xl border border-white/10 p-3">
                <div className="mb-1 flex flex-wrap gap-2">
                  <Badge variant={severityBadge(String(alert.severity))}>{String(alert.severity)}</Badge>
                  <Badge variant="outline">{alert.status === "OPEN" ? "Unread" : String(alert.status)}</Badge>
                </div>
                <p className="text-sm font-medium">{String(alert.headline)}</p>
                <p className="text-xs text-white/50">{(alert.symbols as string[] | undefined)?.join(", ")}</p>
                <p className="text-xs text-white/40">
                  Published {formatMs(alert.published_at_ms as number | null)} · observed{" "}
                  {formatMs(alert.first_observed_at_ms as number | null)} · detected{" "}
                  {formatMs(alert.detected_at_ms as number | null)}
                </p>
                <p className="text-xs text-white/50">Verification {String(alert.verification)}</p>
                <div className="mt-2 flex gap-2">
                  <Button type="button" variant="outline" onClick={() => setSelected(alert)}>
                    Details
                  </Button>
                  {alert.status === "OPEN" ? (
                    <Button type="button" onClick={() => void acknowledge(String(alert.alert_id))}>
                      Acknowledge
                    </Button>
                  ) : null}
                </div>
              </article>
            ))}
            {ackNote ? <p className="text-xs text-white/60">{ackNote}</p> : null}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Classified events</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {filteredEvents.slice(0, 20).map((event) => (
            <div key={String(event.event_id)} className="flex flex-wrap items-center gap-2 text-sm">
              <Badge variant={severityBadge(String(event.severity))}>{String(event.severity || "UNKNOWN")}</Badge>
              <span>{String(event.category || "UNKNOWN")}</span>
              <span className="text-white/50">{String(event.sentiment || "")}</span>
              <span className="text-white/70">{String(event.headline)}</span>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Provider health</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1 text-sm">
          {health.length === 0 ? <p className="text-white/50">No provider checks stored.</p> : null}
          {health.slice(0, 10).map((row, idx) => (
            <p key={`${String(row.provider_id)}-${idx}`}>
              {String(row.provider_id)} · {row.ok ? "ok" : "error"} · {formatMs(row.checked_ms as number)}
            </p>
          ))}
        </CardContent>
      </Card>

      {selected ? (
        <Card>
          <CardHeader>
            <CardTitle>Alert detail</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p>{String(selected.headline)}</p>
            <p className="text-white/70">{String(selected.explanation || selected.summary || "")}</p>
            <p>Verification {String(selected.verification)} · freshness {String(selected.freshness || "unknown")}</p>
            {selected.source_url ? (
              <a className="underline" href={String(selected.source_url)} target="_blank" rel="noreferrer">
                Source link
              </a>
            ) : (
              <p className="text-white/50">Source link unavailable</p>
            )}
            <p className="text-xs text-white/40">
              In-app recording is not an external delivery confirmation. Telegram stays unconfirmed until the provider
              accepts the message.
            </p>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
