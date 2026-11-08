import {
  Activity,
  BarChart3,
  CandlestickChart,
  FlaskConical,
  History,
  LayoutGrid,
  Newspaper,
  Sparkles,
  List,
  Settings,
  ShieldCheck,
  Wallet,
} from "lucide-react";

export const NAV_GROUPS = [
  {
    label: "Watch",
    items: [
      { href: "/dashboard", label: "Overview", icon: LayoutGrid },
      { href: "/agents/live", label: "Live AI Analysis", icon: Activity },
      { href: "/markets", label: "Markets & Charts", icon: CandlestickChart },
      { href: "/news", label: "News", icon: Newspaper },
      { href: "/llm", label: "LLM Intelligence", icon: Sparkles },
    ],
  },
  {
    label: "Money",
    items: [
      { href: "/portfolio", label: "Portfolio", icon: Wallet },
      { href: "/positions", label: "Positions", icon: List },
      { href: "/paper", label: "Paper Trading", icon: FlaskConical },
    ],
  },
  {
    label: "Tools",
    items: [
      { href: "/risk", label: "Risk Center", icon: ShieldCheck },
      { href: "/analytics", label: "Analytics", icon: BarChart3 },
      { href: "/backtesting", label: "Backtesting", icon: History },
      { href: "/settings", label: "Settings", icon: Settings },
      { href: "/settings/exchanges", label: "Exchanges", icon: Wallet },
    ],
  },
] as const;
