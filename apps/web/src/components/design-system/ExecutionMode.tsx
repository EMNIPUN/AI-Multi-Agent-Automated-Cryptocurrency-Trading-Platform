import { StatusBadge, type StatusTone } from "@/components/design-system/StatusBadge";

const MODES = {
  paper: { label: "PAPER", tone: "paper" },
  testnet: { label: "TESTNET", tone: "info" },
  live: { label: "LIVE gated", tone: "live" },
  blocked: { label: "BLOCKED", tone: "halted" },
} as const satisfies Record<string, { label: string; tone: StatusTone }>;

/** Text label for an execution mode. Color is never the only signal. */
export function ExecutionMode({ mode }: { mode: keyof typeof MODES }) {
  const cfg = MODES[mode];
  return <StatusBadge label={cfg.label} tone={cfg.tone} />;
}
