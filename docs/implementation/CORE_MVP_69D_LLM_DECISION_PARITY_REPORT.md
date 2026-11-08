# CryptoNova — 69D Decision Parity

The LLM service runs only after `SignalPipeline.evaluate` returns. It does not import into Market, Trend, Momentum, Coordinator, or Risk calculation methods.

Parity check in `tests/test_core_llm_69d.py`:

1. Evaluate the bullish fixture with advisory news off.
2. Record action, risk verdict, position notional, signal strength, and `execution_allowed`.
3. Ask the scripted model for `ABSTAIN`.
4. Read the same decision object again.

The recorded fields matched. `llm_changed_decision` was false. A second pipeline evaluation with the same candles produced the same action, verdict, and notional.

A provider timeout, rate limit, budget refusal, or storage outage returns an advisory status and leaves the technical decision untouched.

`execution_allowed` on the public comparison is false. The package does not call an exchange order method.
