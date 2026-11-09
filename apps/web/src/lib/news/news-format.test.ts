import { describe, expect, it } from "vitest";

import { isAllowedPublicNewsPath, isAllowedPublicNewsPostPath, isAllowedPublicNewsPutPath } from "@/lib/security/public-news-proxy";
import {
  NEWS_ADVISORY_LABEL,
  filterNewsRows,
  formatNewsTime,
  friendlySchedulerNote,
  newsViewState,
  severityBadge,
} from "@/lib/news/news-format";

describe("news dashboard state", () => {
  it("keeps disabled, empty, error and stale distinct", () => {
    expect(newsViewState({ loading: true, disabled: false, error: false, count: 0, stale: false })).toBe(
      "loading",
    );
    expect(newsViewState({ loading: false, disabled: true, error: false, count: 0, stale: false })).toBe(
      "disabled",
    );
    expect(newsViewState({ loading: false, disabled: false, error: true, count: 3, stale: false })).toBe(
      "error",
    );
    expect(newsViewState({ loading: false, disabled: false, error: false, count: 0, stale: false })).toBe(
      "empty",
    );
    expect(newsViewState({ loading: false, disabled: false, error: false, count: 2, stale: true })).toBe(
      "stale",
    );
  });

  it("filters by symbol and severity without inventing rows", () => {
    const rows = filterNewsRows(
      [
        { symbols: ["BTCUSDT"], severity: "CRITICAL", category: "SECURITY_INCIDENT", verification: "SINGLE_SOURCE" },
        { symbols: ["ETHUSDT"], severity: "LOW", category: "GENERAL", verification: "UNVERIFIED" },
      ],
      {
        symbol: "BTCUSDT",
        severity: "CRITICAL",
        category: "ALL",
        verification: "ALL",
        fromMs: null,
        toMs: null,
      },
    );
    expect(rows).toHaveLength(1);
    expect(severityBadge("CRITICAL")).toBe("danger");
  });

  it("states that news does not change trading decisions", () => {
    expect(NEWS_ADVISORY_LABEL).toBe("News Advisory Only — Trading Decisions Unchanged");
  });

  it("formats relative news times and friendly scheduler notes", () => {
    expect(formatNewsTime(null)).toBe("Unknown time");
    expect(formatNewsTime(Date.now() - 90_000)).toMatch(/m ago/);
    const note = friendlySchedulerNote(
      "Manual collection required until NEWS_AUTO_COLLECTION_ENABLED=true",
    );
    expect(note.summary.toLowerCase()).toContain("automatic collection");
    expect(note.detail).toContain("NEWS_AUTO_COLLECTION_ENABLED");
  });

  it("allows only news alert proxy paths", () => {
    expect(isAllowedPublicNewsPath("/api/v1/news/alerts")).toBe(true);
    expect(isAllowedPublicNewsPath("/api/v1/news/alerts/nal_abc123")).toBe(true);
    expect(isAllowedPublicNewsPostPath("/api/v1/news/alerts/nal_abc123/acknowledge")).toBe(true);
    expect(isAllowedPublicNewsPutPath("/api/v1/news/alert-settings")).toBe(true);
    expect(isAllowedPublicNewsPath("/api/v1/orders")).toBe(false);
  });
});
