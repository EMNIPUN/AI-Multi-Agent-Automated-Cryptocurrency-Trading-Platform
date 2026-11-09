#!/usr/bin/env python
"""Start or resume the HYPEUSDT 48h autonomous PAPER campaign.

Default: start and run until duration elapses (unattended).
Use --max-ticks for local dry runs. Never places exchange orders.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.supervisor.campaign import CampaignConfig, PaperCampaign, default_public_fetcher


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HYPEUSDT 48h paper campaign")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-ticks", type=int, default=None)
    parser.add_argument("--poll-seconds", type=float, default=30.0)
    parser.add_argument("--status-only", action="store_true")
    parser.add_argument(
        "--journal",
        default="data/paper_campaign/hype_48h.sqlite3",
    )
    parser.add_argument(
        "--report",
        default="data/paper_campaign/hype_48h_report.json",
    )
    args = parser.parse_args(argv)
    config = CampaignConfig(
        journal_path=args.journal,
        report_path=args.report,
        poll_seconds=args.poll_seconds,
    )
    campaign = PaperCampaign(config, fetch_candles=default_public_fetcher)
    if args.status_only:
        print(json.dumps(campaign.status(), indent=2))
        return 0
    if args.resume:
        print(json.dumps(campaign.resume_after_restart(), indent=2))
    else:
        print(json.dumps(campaign.start(), indent=2))
    if args.max_ticks == 0:
        return 0
    result = campaign.run_until(max_ticks=args.max_ticks, sleep=args.max_ticks is None)
    print(json.dumps(result, indent=2))
    if result.get("wall_clock_complete"):
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
