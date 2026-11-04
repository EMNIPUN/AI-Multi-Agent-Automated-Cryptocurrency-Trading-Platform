import csv
from datetime import datetime, timezone
from pathlib import Path


class TradeJournal:
    def __init__(self, log_dir: str | Path = "logs") -> None:
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        day = datetime.now(timezone.utc).strftime("%Y%m%d")
        self.path = self.log_dir / f"agent_{day}.csv"
        self._ensure_header()

    def _ensure_header(self) -> None:
        if self.path.exists() and self.path.stat().st_size > 0:
            return
        with self.path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(
                [
                    "utc_time",
                    "event",
                    "symbol",
                    "category",
                    "side",
                    "qty",
                    "price",
                    "dry_run",
                    "reason",
                    "order_id",
                    "equity",
                    "details",
                ]
            )

    def write(
        self,
        event: str,
        *,
        symbol: str = "",
        category: str = "",
        side: str = "",
        qty: str = "",
        price: str = "",
        dry_run: bool = True,
        reason: str = "",
        order_id: str = "",
        equity: str = "",
        details: str = "",
    ) -> None:
        with self.path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(
                [
                    datetime.now(timezone.utc).isoformat(),
                    event,
                    symbol,
                    category,
                    side,
                    qty,
                    price,
                    "1" if dry_run else "0",
                    reason,
                    order_id,
                    equity,
                    details,
                ]
            )
