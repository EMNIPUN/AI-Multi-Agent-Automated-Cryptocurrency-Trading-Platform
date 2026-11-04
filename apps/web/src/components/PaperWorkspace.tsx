"use client";

import { useEffect, useState } from "react";

import { LogoLoader } from "@/components/brand/LogoLoader";
import { SampleBanner } from "@/components/SampleBanner";
import { localPaperFixture } from "@/lib/fixtures/agentSnapshot";
import type { PaperWorkspaceSnapshot } from "@/lib/observability/types";

export function PaperWorkspace() {
  const [snap, setSnap] = useState<PaperWorkspaceSnapshot | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/observability/paper", { cache: "no-store" });
        if (!res.ok) throw new Error("fail");
        const data = (await res.json()) as PaperWorkspaceSnapshot;
        if (!cancelled) setSnap(data);
      } catch {
        if (!cancelled) setSnap(localPaperFixture());
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (!snap) {
    return <LogoLoader fullScreen label="Loading paper workspace…" />;
  }

  return (
    <div>
      <SampleBanner dataMode={snap.data_mode} notes={snap.notes} />
      <div className="meta-row">
        <div className="metric">
          <span className="label">Virtual equity</span>
          <div className="value">{snap.virtual_equity.toFixed(2)}</div>
        </div>
        <div className="metric">
          <span className="label">Cash</span>
          <div className="value">{snap.cash.toFixed(2)}</div>
        </div>
        <div className="metric">
          <span className="label">Unrealized PnL</span>
          <div className="value">{snap.unrealized_pnl.toFixed(2)}</div>
        </div>
        <div className="metric">
          <span className="label">Realized PnL</span>
          <div className="value">{snap.realized_pnl.toFixed(2)}</div>
        </div>
      </div>

      <div className="grid-main">
        <section className="panel">
          <h2>
            Positions <span className="badge sample">SAMPLE</span>
          </h2>
          <table className="table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Side</th>
                <th>Qty</th>
                <th>Entry</th>
                <th>Mark</th>
                <th>SL</th>
                <th>TP</th>
              </tr>
            </thead>
            <tbody>
              {snap.positions.map((p, i) => (
                <tr key={i}>
                  <td>{String(p.symbol)}</td>
                  <td>{String(p.side)}</td>
                  <td>{String(p.qty)}</td>
                  <td>{String(p.entry)}</td>
                  <td>{String(p.mark)}</td>
                  <td>{String(p.sl)}</td>
                  <td>{String(p.tp)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        <section className="panel">
          <h2>Simulated orders</h2>
          <table className="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Symbol</th>
                <th>Side</th>
                <th>State</th>
              </tr>
            </thead>
            <tbody>
              {snap.simulated_orders.map((o, i) => (
                <tr key={i}>
                  <td>{String(o.id)}</td>
                  <td>{String(o.symbol)}</td>
                  <td>{String(o.side)}</td>
                  <td>{String(o.state)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p style={{ marginTop: "1rem" }}>
            <button type="button" disabled aria-disabled="true">
              Submit paper order (disabled)
            </button>
          </p>
          <p className="muted">
            broker_implemented={String(snap.broker_implemented)} ·
            submit_controls_enabled={String(snap.submit_controls_enabled)}.
            Simulated orders never reach Bybit.
          </p>
        </section>
      </div>
    </div>
  );
}
