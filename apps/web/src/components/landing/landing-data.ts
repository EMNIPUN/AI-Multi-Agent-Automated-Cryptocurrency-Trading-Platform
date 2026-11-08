export const NAV_LINKS = [
  { href: "#features", label: "Features" },
  { href: "#how-it-works", label: "How it works" },
  { href: "#pricing", label: "Pricing" },
  { href: "#faq", label: "FAQ" },
] as const;

export const HERO_PILLS = [
  "Multi-Agent Signals",
  "Paper Execution",
  "Risk Guards",
  "Live Markets",
] as const;

export const TRUST_LOGOS = [
  "Bybit",
  "Supabase",
  "Next.js",
  "FastAPI",
  "TradingView",
  "OpenAI",
] as const;

export const FEATURES = [
  {
    id: "agents",
    title: "Coordinate specialist trading agents",
    body: "Research, risk, and execution agents collaborate on every thesis so no single model trades alone.",
    points: [
      "Signal consensus across agent roles",
      "Live agent studio with graph workflows",
      "Paper-first execution with labeled fixtures",
    ],
  },
  {
    id: "risk",
    title: "Discipline before size",
    body: "Hard risk rails and read-only live monitoring keep the platform SAMPLE-safe while you validate edge.",
    points: [
      "Position and drawdown snapshots",
      "Trading routes stay off until gated",
      "Audit-friendly activity timelines",
    ],
  },
  {
    id: "markets",
    title: "Public markets, private reads gated",
    body: "Stream public USDT perps, candles, and order books while private wallet reads stay behind auth.",
    points: [
      "Public ticker and candle streams",
      "Same-origin market proxies",
      "Clear data-path labels (live / simulated)",
    ],
  },
] as const;

export const STEPS = [
  {
    title: "Create your operator account",
    body: "Sign up and enter the command dashboard. No exchange keys required to explore paper mode.",
  },
  {
    title: "Connect markets and agents",
    body: "Watch public quotes, configure agent roles, and review signal history before any live path opens.",
  },
  {
    title: "Paper trade with discipline",
    body: "Run multi-agent workflows against paper equity. Upgrade only when risk and edge prove out.",
  },
] as const;

export const TESTIMONIALS = [
  {
    quote:
      "CryptoNova’s agent studio finally made our research → risk → paper loop visible. We ship ideas faster without skipping guards.",
    name: "A. Menon",
    role: "Quant lead, DeltaForge",
  },
  {
    quote:
      "The SAMPLE-safe defaults are the point. We validate strategies in paper with real market context before touching size.",
    name: "Jordan Lee",
    role: "Founder, Northbook Capital",
  },
  {
    quote:
      "Public market streams plus gated private reads is exactly the architecture we needed for a multi-agent desk.",
    name: "Priya Shah",
    role: "CTO, Lattice Markets",
  },
  {
    quote:
      "Border-beam activity feeds and risk snapshots keep the whole desk aligned without another spreadsheet.",
    name: "Chris Okonkwo",
    role: "Trader, Helix Desk",
  },
  {
    quote:
      "We went from scattered scripts to one operator terminal. Agents argue; risk still wins.",
    name: "Sofia Alvarez",
    role: "Head of Systems, Orbit Labs",
  },
  {
    quote:
      "Paper equity, signal history, and agent live views in one place — this is how disciplined AI trading should feel.",
    name: "Ethan Park",
    role: "Research PM, Signalworks",
  },
] as const;

export const PRICING = [
  {
    name: "Paper",
    price: "$0",
    period: "/month",
    blurb: "Explore the operator terminal with public markets and paper workflows.",
    featured: false,
    cta: "Start free",
    href: "/signup",
    perks: [
      "Public market streams",
      "Paper portfolio & positions",
      "Agent studio (read + paper)",
      "Risk snapshot panels",
    ],
  },
  {
    name: "Pro",
    price: "$49",
    period: "/month",
    blurb: "For desks validating multi-agent edge with deeper analytics.",
    featured: true,
    cta: "Upgrade to Pro",
    href: "/signup",
    perks: [
      "Everything in Paper",
      "Advanced analytics & backtesting",
      "Priority signal history retention",
      "Exchange connection workspace",
      "Notification routing",
    ],
  },
  {
    name: "Enterprise",
    price: "Custom",
    period: "",
    blurb: "Dedicated rails, SSO, and operator controls for larger teams.",
    featured: false,
    cta: "Contact sales",
    href: "/signup",
    perks: [
      "Everything in Pro",
      "SSO & role controls",
      "Custom agent policies",
      "Dedicated support window",
      "On-prem / VPC options",
    ],
  },
] as const;

export const FAQS = [
  {
    q: "What is CryptoNova?",
    a: "CryptoNova is a multi-agent cryptocurrency trading platform focused on intelligent monitoring, paper execution, and disciplined risk — with live trading routes gated off until you are ready.",
  },
  {
    q: "Is live trading enabled?",
    a: "No by default. The product ships SAMPLE-safe: public markets and paper workflows are available; live order routes stay off behind explicit gates.",
  },
  {
    q: "Do I need exchange API keys to start?",
    a: "Not for paper mode and public market data. Exchange connections live under Settings when you are ready to attach private reads.",
  },
  {
    q: "How do the AI agents work together?",
    a: "Specialist agents (research, risk, execution) collaborate in the agent studio. Consensus and risk guards shape signals before paper execution.",
  },
  {
    q: "Is there a free trial?",
    a: "The Paper plan is free. Pro unlocks deeper analytics and retention when your desk outgrows the free workspace.",
  },
  {
    q: "How is my data secured?",
    a: "Auth is handled via Supabase sessions. Private market and wallet endpoints are proxied same-origin and require a signed-in session.",
  },
] as const;
