"""Telegram Bot API adapter (Prompt 69B). Disabled unless explicitly configured."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class DeliveryOutcome:
    status: str
    confirmed: bool
    error: str | None = None
    provider_message_id: str | None = None
    attempts: int = 0


Transport = Callable[[str, dict[str, Any], float], tuple[int, str]]


def _default_transport(url: str, payload: dict[str, Any], timeout: float) -> tuple[int, str]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — operator URL only
            body = resp.read().decode("utf-8", errors="replace")
            return int(resp.status), body
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return int(exc.code), raw


def format_telegram_text(alert: dict[str, Any]) -> str:
    symbols = ", ".join(alert.get("symbols") or []) or "n/a"
    published = alert.get("published_at_ms")
    stamp = str(published if published is not None else alert.get("detected_at_ms"))
    lines = [
        "CryptoNova news alert",
        f"Severity: {alert.get('severity')}",
        f"Symbol: {symbols}",
        f"Headline: {alert.get('headline')}",
        f"Verification: {alert.get('verification')}",
        f"Timestamp_ms: {stamp}",
        f"Explanation: {alert.get('explanation')}",
        f"Source: {alert.get('source_url') or 'unavailable'}",
        "Advisory only. This message does not place orders.",
    ]
    return "\n".join(lines)[:3500]


class TelegramNotifier:
    def __init__(
        self,
        *,
        enabled: bool,
        token: str | None,
        chat_id: str | None,
        timeout_seconds: float = 8.0,
        max_attempts: int = 3,
        min_interval_seconds: float = 1.0,
        transport: Transport | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self._token = (token or "").strip()
        self._chat_id = (chat_id or "").strip()
        self.enabled = bool(enabled and self._token and self._chat_id)
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max(1, min(max_attempts, 3))
        self.min_interval_seconds = min_interval_seconds
        self._transport = transport or _default_transport
        self._sleep = sleep or time.sleep
        self._last_sent = 0.0

    def redact(self, text: str) -> str:
        if self._token and self._token in text:
            text = text.replace(self._token, "***")
        return text[:400]

    def deliver(self, alert: dict[str, Any]) -> DeliveryOutcome:
        if not self.enabled:
            return DeliveryOutcome(status="skipped", confirmed=False, error="telegram_disabled", attempts=0)
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": format_telegram_text(alert),
            "disable_web_page_preview": True,
        }
        last_error = "telegram_failed"
        for attempt in range(1, self.max_attempts + 1):
            wait = self.min_interval_seconds - (time.monotonic() - self._last_sent)
            if wait > 0:
                self._sleep(wait)
            try:
                status, body = self._transport(url, payload, self.timeout_seconds)
                self._last_sent = time.monotonic()
                if 200 <= status < 300:
                    message_id = None
                    try:
                        parsed = json.loads(body)
                        message_id = str((parsed.get("result") or {}).get("message_id") or "") or None
                    except json.JSONDecodeError:
                        message_id = None
                    return DeliveryOutcome(
                        status="confirmed",
                        confirmed=True,
                        provider_message_id=message_id,
                        attempts=attempt,
                    )
                last_error = self.redact(f"http_{status}")
            except Exception as exc:  # noqa: BLE001
                last_error = self.redact(f"{type(exc).__name__}")
            if attempt < self.max_attempts:
                self._sleep(min(2.0, 0.25 * (2 ** (attempt - 1))))
        return DeliveryOutcome(
            status="failed",
            confirmed=False,
            error=last_error,
            attempts=self.max_attempts,
        )
