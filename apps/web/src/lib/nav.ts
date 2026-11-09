import {
  Activity,
  BarChart3,
  Bell,
  Bot,
  CandlestickChart,
  FlaskConical,
  HeartPulse,
  History,
  List,
  Newspaper,
  Settings,
  ShieldCheck,
  Sparkles,
  Target,
  Users,
  Wallet,
} from "lucide-react";

export const NAV_GROUPS = [
  {
    label: "AI Command Center",
    items: [
      { href: "/orchestrator", label: "AI Orchestrator", icon: Bot },
      { href: "/autonomy", label: "Autonomous Trading", icon: ShieldCheck },
      { href: "/agents", label: "Agent Workspace", icon: Users },
      { href: "/agents/live", label: "Live AI Analysis", icon: Activity },
      { href: "/llm", label: "LLM Intelligence", icon: Sparkles },
    ],
  },
  {
    label: "Trading Desk",
    items: [
      { href: "/markets", label: "Markets", icon: CandlestickChart },
      { href: "/portfolio", label: "Portfolio", icon: Wallet },
      { href: "/positions", label: "Positions & Orders", icon: List },
      { href: "/paper", label: "Paper Trading", icon: FlaskConical },
      { href: "/risk", label: "Risk Center", icon: ShieldCheck },
    ],
  },
  {
    label: "Research & Intelligence",
    items: [
      { href: "/news", label: "News Intelligence", icon: Newspaper },
      { href: "/strategy", label: "Strategy Research", icon: Target },
      { href: "/backtesting", label: "Backtesting", icon: History },
      { href: "/analytics", label: "Analytics", icon: BarChart3 },
    ],
  },
  {
    label: "System",
    items: [
      { href: "/notifications", label: "Notifications", icon: Bell },
      { href: "/settings/exchanges", label: "Exchange Connections", icon: Wallet },
      { href: "/settings", label: "Settings", icon: Settings },
      { href: "/system", label: "System Health", icon: HeartPulse },
    ],
  },
] as const;

/** Flat list for command palette / breadcrumbs. */
export const NAV_FLAT = NAV_GROUPS.flatMap((g) =>
  g.items.map((item) => ({ ...item, group: g.label })),
);

export function crumbForPath(pathname: string): { group: string; label: string; href: string } {
  const hit = NAV_FLAT.find(
    (item) =>
      pathname === item.href ||
      (item.href !== "/orchestrator" &&
        item.href !== "/agents" &&
        pathname.startsWith(`${item.href}/`)) ||
      (item.href === "/agents" && pathname === "/agents"),
  );
  if (hit) return { group: hit.group, label: hit.label, href: hit.href };
  const leaf = pathname.split("/").filter(Boolean).pop()?.replace(/-/g, " ") || "Workspace";
  return { group: "Workspace", label: leaf, href: pathname };
}
