# News Safety Policy (69)

- No live orders; no private Bybit trading; no news-triggered execution.
- LLM optional and OFF by default; no tool/trade authority.
- External article text is untrusted (prompt-injection detection).
- Severity ≠ sentiment; never invent verification.
- No lookahead: `available_at` gates historical visibility.
- Feature flags default OFF.
- Collection only via explicit gated POST (loopback), never GET.
- Do not bypass risk engine; advisory must not weaken controls.
- SQLite paper/backtest journals untouched by news milestone.
