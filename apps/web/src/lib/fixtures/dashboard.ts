/** Explicit SAMPLE fixtures for premium UI — never treat as live exchange authority. */

export const dashboardFixture = {
  data_mode: "fixture" as const,
  notes: [
    "Equity/PnL metrics below are SAMPLE placeholders unless live wallet API responds.",
    "PRIVATE_DATA_READS_ENABLED=false — catalog private streams remain gated.",
    "Live trading HTTP remains disabled.",
  ],
  agent: {
    status: "OFFLINE" as const,
    heartbeat_stale: true,
    strategy: "EMA/RSI",
    symbol: "BTCUSDT",
    interval: "15",
  },
  risk: {
    verdict: "N/A",
    daily_loss_limit: "2%",
    halted: false,
    reasons: ["No live risk snapshot until worker publisher is wired"],
  },
  paper: {
    equity: 10000,
    cash: 9420.55,
    unrealized: 42.1,
    realized: -18.25,
  },
  activity: [
    {
      id: "1",
      title: "Worker offline",
      detail: "No heartbeat within stale window",
      at: "SAMPLE",
    },
    {
      id: "2",
      title: "Fixture snapshot loaded",
      detail: "Command Center using labeled SAMPLE data",
      at: "SAMPLE",
    },
    {
      id: "3",
      title: "Trading HTTP disabled",
      detail: "No place/cancel/leverage routes exposed",
      at: "SAMPLE",
    },
  ],
};

export const analyticsFixture = {
  equityCurve: [
    { t: "Mon", equity: 10000 },
    { t: "Tue", equity: 10040 },
    { t: "Wed", equity: 9980 },
    { t: "Thu", equity: 10055 },
    { t: "Fri", equity: 10042 },
  ],
  winRate: 0.0,
  maxDrawdown: 0.0,
  trades: 0,
  note: "Analytics are SAMPLE until journal APIs + ownership are live.",
};
