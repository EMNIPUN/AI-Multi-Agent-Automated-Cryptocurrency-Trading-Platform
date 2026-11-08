# CryptoNova — 69E LLM Shadow Evaluation

Mode C does not call OpenAI.

A shadow comparison may use a `RecordedLlmAdvice` row only when:

- `completed_at_ms` is at or before the candle clock
- `retrospective` is false
- `validation_result` is `accepted`

A row marked `retrospective=True` is counted as a retrospective experiment. It is not treated as a signal that existed during the historical bar. A row completed after the bar is excluded.

`NEWS_LLM_ENABLED` stays false. The 69D budget guard is in-process memory. It is not shared across processes and it is not restored after a restart. Idempotent audit rows require migration `20261108_0009`, which is not applied. Because 69E makes no model calls, that gap does not spend money. It does block any future paid retrospective run until a durable budget exists and an operator approves a bounded call.

Agreement, disagreement, and abstention rates describe stored advice. They are not returns, and model text is not a probability.

`llm_changed_decision` is false. The Coordinator action, Risk verdict, and position notional stay on the technical result.
