"""Bybit signed-request clock skew correction (no live credentials required)."""

from __future__ import annotations

from apps.api.app.exchange import bybit_clock


def test_synced_timestamp_applies_offset(monkeypatch) -> None:
    monkeypatch.setattr(bybit_clock, "_offset_ms", -2500)
    monkeypatch.setattr(bybit_clock.time, "time", lambda: 1_000_000.0)
    assert bybit_clock.synced_timestamp_ms() == 1_000_000_000 - 2500


def test_sync_bybit_clock_sets_negative_offset_when_local_ahead(monkeypatch) -> None:
    class _Resp:
        def json(self):
            return {"retCode": 0, "result": {"timeSecond": "1000", "timeNano": "1000000000000"}}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            assert "market/time" in url
            return _Resp()

    monkeypatch.setattr(bybit_clock.httpx, "Client", _Client)
    monkeypatch.setattr(bybit_clock.time, "time", lambda: 1003.0)  # 3s ahead
    monkeypatch.setattr(bybit_clock, "_last_sync_mono", 0.0)
    offset = bybit_clock.sync_bybit_clock(force=True)
    assert offset == -3000
    assert bybit_clock.get_time_offset_ms() == -3000
