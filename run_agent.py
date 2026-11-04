"""CLI entry for the rule-based Bybit trading agent."""

from agent.config import load_settings
from agent.runner import AgentRunner
from agent.telemetry_ledger import TelemetryLedger
from bot.client import create_session
from bot.config import API_KEY, API_SECRET


def main() -> None:
    if not API_KEY or not API_SECRET:
        print("Missing BYBIT_API_KEY / BYBIT_API_SECRET in .env")
        return

    settings = load_settings()
    if not settings.enabled:
        print("AGENT_ENABLED=false — enable it in .env to run the agent.")
        return

    import os

    ledger_path = os.getenv("OBSERVABILITY_LEDGER_PATH", "data/observability_ledger.sqlite")
    telemetry = TelemetryLedger(ledger_path)
    session = create_session()
    AgentRunner(session, settings, telemetry=telemetry).run_forever()


if __name__ == "__main__":
    main()
