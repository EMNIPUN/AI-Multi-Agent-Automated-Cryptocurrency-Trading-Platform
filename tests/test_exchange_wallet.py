"""Offline tests for read-only Bybit wallet dashboard contract."""

from __future__ import annotations

from fastapi.testclient import TestClient

from apps.api.app.auth.jwt_verifier import StaticMappingVerifier
from apps.api.app.auth.principal import AuthenticatedPrincipal
from apps.api.app.config import ApiSettings, clear_settings_cache
from apps.api.app.exchange.wallet import parse_unified_wallet_response
from apps.api.app.factory import create_app


def _settings(**kwargs) -> ApiSettings:
    base = dict(
        _env_file=None,
        api_host="127.0.0.1",
        cors_origins=[],
        database_url=None,
        private_data_reads_enabled=False,
        exchange_wallet_reads_enabled=True,
        observability_fixture_mode=True,
        supabase_url="https://example.supabase.co",
        auth_jwt_mode="hs256",
        supabase_jwt_secret="test-only-hs256-secret-not-for-production-32b+",
        supabase_jwt_audience="authenticated",
        supabase_jwt_issuer="https://example.supabase.co/auth/v1",
    )
    base.update(kwargs)
    return ApiSettings(**base)


class _FakeWallet:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls = 0

    def get_wallet_balance(self, **kwargs):
        self.calls += 1
        assert kwargs.get("accountType") == "UNIFIED"
        return self.payload


SAMPLE = {
    "retCode": 0,
    "retMsg": "OK",
    "result": {
        "list": [
            {
                "totalEquity": "5.3291948",
                "totalWalletBalance": "5.3291948",
                "totalAvailableBalance": "",
                "totalPerpUPL": "0",
                "coin": [
                    {
                        "coin": "USDT",
                        "walletBalance": "5.25782276",
                        "availableToWithdraw": "5.25782276",
                        "equity": "5.25782276",
                        "unrealisedPnl": "0",
                    },
                    {
                        "coin": "BTC",
                        "walletBalance": "0.00000094",
                        "equity": "0.00000094",
                        "unrealisedPnl": "0",
                    },
                    {
                        "coin": "ZERO",
                        "walletBalance": "0",
                        "equity": "0",
                        "unrealisedPnl": "0",
                    },
                ],
            }
        ]
    },
}


def test_parse_unified_wallet_filters_zero_coins() -> None:
    snap = parse_unified_wallet_response(
        SAMPLE, env_label="Mainnet", is_mainnet=True
    )
    assert snap.total_equity == "5.3291948"
    coins = {c.coin for c in snap.coins}
    assert coins == {"USDT", "BTC"}
    assert "ZERO" not in coins
    assert any("MAINNET" in n for n in snap.notes)


def test_wallet_endpoint_uses_injected_client() -> None:
    clear_settings_cache()
    app = create_app(_settings())
    fake = _FakeWallet(SAMPLE)
    app.state.bybit_wallet_client = fake
    client = TestClient(app)
    resp = client.get("/api/v1/exchange/wallet")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_equity"] == "5.3291948"
    assert body["coins"][0]["coin"] in {"USDT", "BTC"}
    assert "api_key" not in resp.text.lower()
    assert "secret" not in resp.text.lower()
    assert fake.calls == 1


def test_wallet_endpoint_disabled() -> None:
    clear_settings_cache()
    app = create_app(_settings(exchange_wallet_reads_enabled=False))
    app.state.bybit_wallet_client = _FakeWallet(SAMPLE)
    resp = TestClient(app).get("/api/v1/exchange/wallet")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "exchange_wallet_reads_disabled"


def test_wallet_endpoint_bybit_error() -> None:
    clear_settings_cache()
    app = create_app(_settings())
    app.state.bybit_wallet_client = _FakeWallet(
        {"retCode": 10001, "retMsg": "param error", "result": {}}
    )
    resp = TestClient(app).get("/api/v1/exchange/wallet")
    assert resp.status_code == 503
    assert resp.json()["detail"] == "bybit_wallet_unavailable"


def test_wallet_rejects_user_jwt_and_forwarded_client() -> None:
    clear_settings_cache()
    app = create_app(_settings())
    app.state.bybit_wallet_client = _FakeWallet(SAMPLE)
    principal = AuthenticatedPrincipal(
        user_id="11111111-1111-1111-1111-111111111111",
        role="authenticated",
    )
    app.state.token_verifier = StaticMappingVerifier({"good": principal})
    client = TestClient(app)
    denied = client.get(
        "/api/v1/exchange/wallet",
        headers={"Authorization": "Bearer good"},
    )
    assert denied.status_code == 403
    # JWT path never falls through to operator-local diagnostics.
    assert denied.json()["detail"] == "ownership_schema_required"
    forwarded = client.get(
        "/api/v1/exchange/wallet",
        headers={"X-Forwarded-For": "8.8.8.8"},
    )
    assert forwarded.status_code == 403
    assert forwarded.json()["detail"] == "operator_diagnostic_proxy_forward_rejected"
