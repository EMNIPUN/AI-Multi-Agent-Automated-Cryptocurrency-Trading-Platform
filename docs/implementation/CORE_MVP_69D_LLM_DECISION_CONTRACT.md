# CryptoNova — 69D LLM Decision Contract

Schema `69D.1.0`. Prompt template `69D.prompt.1`.

The model may return only:

- `suggested_action`: `BUY`, `SELL`, `HOLD`, or `ABSTAIN`
- `technical_bias`, `news_bias`
- `conflict_detected`
- a short `reason`
- `risk_warnings`
- `evidence_event_ids` that were present in the input
- `uncertainty`
- `abstain`

`ABSTAIN` is required when the model says evidence is inadequate. Abstain with another action is rejected.

The server rejects malformed JSON, unknown actions, unknown event ids, oversized text, a mismatched symbol, and any field that tries to set execution, position size, or a risk bypass.

Sentiment is not a trade. Model text is not a calibrated probability and is not a verified profitable signal.

Every stored comparison keeps:

- `llm_changed_decision = false`
- `execution_allowed = false`
- `places_orders = false`

The deterministic Coordinator action, Risk verdict, and position notional are copied into the audit row. They are not replaced by the suggestion.
