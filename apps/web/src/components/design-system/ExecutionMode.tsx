import { StatusBadge, type StatusTone } from "@/components/design-system/StatusBadge";

export type ExecutionModeKind = "paper" | "testnet" | "live" | "blocked";

const MODES: Record<ExecutionModeKind, { label: string; tone: StatusTone }> = {
  paper: { label: "PAPER", tone: "paper" },
  testnet: { label: "TESTNET", tone: "info" },
  live: { label: "LIVE locked", tone: "live" },
  blocked: { label: "BLOCKED", tone: "halted" },
};

/**
 * Text label for an execution lane. Colour is never the only signal.
 *
 * `armed` describes what the backend reports, not what the UI wishes:
 *  - live + armed    → "LIVE armed · Approve per order"
 *  - live + !armed   → "LIVE locked"
 *  - testnet + armed → "TESTNET armed"
 */
export function ExecutionMode({
  mode,
  armed,
  className,
}: {
  mode: ExecutionModeKind;
  armed?: boolean;
  className?: string;
}) {
  const cfg = MODES[mode];
  let label = cfg.label;
  let tone = cfg.tone;
  if (mode === "live") {
    label = armed ? "LIVE armed · Approve per order" : "LIVE locked";
    tone = armed ? "live" : "neutral";
  } else if (mode === "testnet") {
    label = armed ? "TESTNET armed" : "TESTNET off";
    tone = armed ? "info" : "neutral";
  }
  return <StatusBadge label={label} tone={tone} className={className} />;
}
