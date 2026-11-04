import { PIPELINE_STEPS, type PipelineStep } from "@/lib/observability/types";

const ORDER = PIPELINE_STEPS.map((s) => s.id);

function rank(step: PipelineStep): number {
  if (step === "blocked" || step === "halted" || step === "unknown") return -1;
  return ORDER.indexOf(step as (typeof ORDER)[number]);
}

export function PipelineViz({
  current,
  blocked,
  blockReason,
}: {
  current: PipelineStep;
  blocked: boolean;
  blockReason?: string | null;
}) {
  const currentRank = rank(current);
  return (
    <section className="panel" aria-label="Trading pipeline">
      <h2>Workflow</h2>
      <p className="muted" style={{ marginTop: 0 }}>
        Market Data → Confirmed Candle → Strategy → Signal → Risk → Intent →
        Reconciliation → Position
      </p>
      <div className="pipeline" role="list">
        {PIPELINE_STEPS.map((step, i) => {
          let state = "";
          if (blocked && (current === "blocked" || current === "halted")) {
            state = i <= Math.max(currentRank, 3) ? "done" : "";
            if (step.id === "risk" || step.id === "intent") state = "blocked";
          } else if (step.id === current) {
            state = "active";
          } else if (currentRank >= 0 && i < currentRank) {
            state = "done";
          }
          if (current === "halted") state = "halted";
          return (
            <div key={step.id} className={`pipe-step ${state}`} role="listitem">
              {step.label}
            </div>
          );
        })}
      </div>
      {(blocked || current === "unknown" || current === "halted") && (
        <p className="badge danger" style={{ margin: 0 }}>
          {current.toUpperCase()}
          {blockReason ? ` — ${blockReason}` : ""}
        </p>
      )}
    </section>
  );
}
