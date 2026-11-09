"""Bybit Testnet read-only connectivity preparation.

Never places orders. Uses injectable clients for tests. Live network reads are
operator-gated and still do not submit orders.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol


class TestnetReadClient(Protocol):
    def fetch_account_identity(self) -> dict[str, Any]: ...

    def fetch_instruments(self, symbol: str) -> dict[str, Any]: ...

    def fetch_positions(self, symbol: str) -> dict[str, Any]: ...


@dataclass
class FakeTestnetReadClient:
    mode: str = "ok"  # ok|auth_fail|timeout|wrong_env|malformed
    uid: str = "testnet-uid-2002"

    def fetch_account_identity(self) -> dict[str, Any]:
        if self.mode == "timeout":
            raise TimeoutError("testnet_timeout")
        if self.mode == "auth_fail":
            return {"retCode": 10003, "retMsg": "Invalid API key", "result": {}}
        if self.mode == "malformed":
            return {"retCode": 0, "retMsg": "OK", "result": "bad"}
        if self.mode == "wrong_env":
            return {
                "retCode": 0,
                "retMsg": "OK",
                "result": {"uid": self.uid, "environment": "mainnet", "accountType": "UNIFIED"},
            }
        return {
            "retCode": 0,
            "retMsg": "OK",
            "result": {"uid": self.uid, "environment": "testnet", "accountType": "UNIFIED"},
        }

    def fetch_instruments(self, symbol: str) -> dict[str, Any]:
        if self.mode == "auth_fail":
            return {"retCode": 10003, "retMsg": "Invalid API key", "result": {}}
        return {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "list": [
                    {
                        "symbol": symbol,
                        "lotSizeFilter": {
                            "minOrderQty": "0.01",
                            "qtyStep": "0.01",
                            "minNotionalValue": "5",
                        },
                    }
                ]
            },
        }

    def fetch_positions(self, symbol: str) -> dict[str, Any]:
        if self.mode == "auth_fail":
            return {"retCode": 10003, "retMsg": "Invalid API key", "result": {}}
        return {"retCode": 0, "retMsg": "OK", "result": {"list": []}}


def testnet_env_separated() -> bool:
    testnet = os.getenv("BYBIT_TESTNET", "true").strip().lower() in {"1", "true", "yes"}
    demo = os.getenv("BYBIT_DEMO", "false").strip().lower() in {"1", "true", "yes"}
    mainnet = os.getenv("MAINNET_TRADING_ENABLED", "false").strip().lower() in {"1", "true", "yes"}
    return testnet and not demo and not mainnet


def prepare_testnet_readonly(client: TestnetReadClient, *, symbol: str = "HYPEUSDT") -> dict[str, Any]:
    """Validate read-only private Testnet surfaces. Never submits an order."""
    body: dict[str, Any] = {
        "environment_separated": testnet_env_separated(),
        "order_submission": False,
        "live_orders": False,
        "exchange_order_sent": False,
        "symbol": symbol,
        "checks": {},
    }
    if not body["environment_separated"]:
        body["ok"] = False
        body["error"] = "testnet_environment_not_separated"
        return body

    try:
        identity = client.fetch_account_identity()
    except TimeoutError:
        body["ok"] = False
        body["error"] = "network_timeout"
        return body
    except Exception as exc:  # noqa: BLE001
        body["ok"] = False
        body["error"] = type(exc).__name__
        return body

    if identity.get("retCode") != 0:
        body["ok"] = False
        body["error"] = "authentication_failed"
        body["checks"]["account_read"] = False
        return body
    result = identity.get("result")
    if not isinstance(result, dict):
        body["ok"] = False
        body["error"] = "malformed_exchange_response"
        return body
    if str(result.get("environment") or "").lower() != "testnet":
        body["ok"] = False
        body["error"] = "wrong_environment"
        return body

    instruments = client.fetch_instruments(symbol)
    positions = client.fetch_positions(symbol)
    body["checks"] = {
        "account_read": True,
        "instrument_metadata": instruments.get("retCode") == 0,
        "position_reads": positions.get("retCode") == 0,
        "auth_ok": True,
    }
    body["ok"] = all(body["checks"].values())
    body["account_type"] = result.get("accountType")
    body["uid_fingerprint"] = str(result.get("uid") or "")[:8]
    body["order_lifecycle_plan"] = (
        "docs/implementation/CRYPTONOVA_TESTNET_ORDER_LIFECYCLE_PLAN.md"
    )
    body["note"] = (
        "Read-only preparation only. Separate approval required before any testnet order."
    )
    return body
