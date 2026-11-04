"""Offline unit tests for fail-closed get_position()."""

from __future__ import annotations

from unittest.mock import MagicMock

from agent.market_data import PositionStatus, get_position


SYMBOL = "HYPEUSDT"


def _session_with_positions(response=None, *, side_effect=None) -> MagicMock:
    session = MagicMock()
    if side_effect is not None:
        session.get_positions.side_effect = side_effect
    else:
        session.get_positions.return_value = response
    return session


def test_valid_empty_position_list_is_flat() -> None:
    session = _session_with_positions(
        {"retCode": 0, "retMsg": "OK", "result": {"list": []}}
    )
    snap = get_position(session, "linear", SYMBOL)
    assert snap.status is PositionStatus.FLAT
    assert snap.position is None
    session.get_positions.assert_called_once()


def test_valid_zero_size_rows_are_flat() -> None:
    session = _session_with_positions(
        {
            "retCode": 0,
            "result": {
                "list": [
                    {"symbol": SYMBOL, "side": "Buy", "size": "0", "avgPrice": "0"}
                ]
            },
        }
    )
    snap = get_position(session, "linear", SYMBOL)
    assert snap.status is PositionStatus.FLAT


def test_valid_open_position() -> None:
    session = _session_with_positions(
        {
            "retCode": 0,
            "result": {
                "list": [
                    {
                        "symbol": SYMBOL,
                        "side": "Buy",
                        "size": "1.5",
                        "avgPrice": "10.2",
                        "unrealisedPnl": "0.3",
                    }
                ]
            },
        }
    )
    snap = get_position(session, "linear", SYMBOL)
    assert snap.status is PositionStatus.OPEN
    assert snap.position is not None
    assert snap.position["side"] == "Buy"
    assert snap.position["size"] == 1.5
    assert snap.position["avgPrice"] == 10.2


def test_timeout_is_unknown_not_flat() -> None:
    session = _session_with_positions(side_effect=TimeoutError("timed out"))
    snap = get_position(session, "linear", SYMBOL)
    assert snap.status is PositionStatus.UNKNOWN
    assert "timeout" in snap.reason.lower()


def test_http_oserror_is_unknown() -> None:
    session = _session_with_positions(side_effect=OSError("connection reset"))
    snap = get_position(session, "linear", SYMBOL)
    assert snap.status is PositionStatus.UNKNOWN
    assert "network" in snap.reason.lower() or "OSError" in snap.reason


def test_api_error_retcode_is_unknown() -> None:
    session = _session_with_positions(
        {"retCode": 10003, "retMsg": "Invalid request", "result": {}}
    )
    snap = get_position(session, "linear", SYMBOL)
    assert snap.status is PositionStatus.UNKNOWN
    assert "10003" in snap.reason
    assert "Invalid request" in snap.reason


def test_auth_style_api_error_is_unknown() -> None:
    session = _session_with_positions(
        {"retCode": 10005, "retMsg": "Permission denied", "result": None}
    )
    snap = get_position(session, "linear", SYMBOL)
    assert snap.status is PositionStatus.UNKNOWN
    assert snap.status is not PositionStatus.FLAT


def test_malformed_non_dict_response_is_unknown() -> None:
    session = _session_with_positions(["not", "a", "dict"])
    snap = get_position(session, "linear", SYMBOL)
    assert snap.status is PositionStatus.UNKNOWN
    assert "malformed" in snap.reason.lower()


def test_missing_result_object_is_unknown() -> None:
    session = _session_with_positions({"retCode": 0, "retMsg": "OK"})
    snap = get_position(session, "linear", SYMBOL)
    assert snap.status is PositionStatus.UNKNOWN
    assert "result" in snap.reason.lower()


def test_missing_result_list_is_unknown() -> None:
    session = _session_with_positions({"retCode": 0, "result": {}})
    snap = get_position(session, "linear", SYMBOL)
    assert snap.status is PositionStatus.UNKNOWN
    assert "list" in snap.reason.lower()


def test_result_list_not_a_list_is_unknown() -> None:
    session = _session_with_positions({"retCode": 0, "result": {"list": {"x": 1}}})
    snap = get_position(session, "linear", SYMBOL)
    assert snap.status is PositionStatus.UNKNOWN


def test_malformed_position_row_invalid_side_is_unknown() -> None:
    session = _session_with_positions(
        {
            "retCode": 0,
            "result": {"list": [{"side": "Long", "size": "2", "avgPrice": "1"}]},
        }
    )
    snap = get_position(session, "linear", SYMBOL)
    assert snap.status is PositionStatus.UNKNOWN
    assert "side" in snap.reason.lower()


def test_malformed_position_row_invalid_size_is_unknown() -> None:
    session = _session_with_positions(
        {
            "retCode": 0,
            "result": {"list": [{"side": "Buy", "size": "abc", "avgPrice": "1"}]},
        }
    )
    snap = get_position(session, "linear", SYMBOL)
    assert snap.status is PositionStatus.UNKNOWN
    assert "size" in snap.reason.lower()


def test_empty_or_missing_expected_data_none_result_is_unknown() -> None:
    session = _session_with_positions({"retCode": 0, "result": None})
    snap = get_position(session, "linear", SYMBOL)
    assert snap.status is PositionStatus.UNKNOWN


def test_spot_valid_zero_inventory_is_flat() -> None:
    session = MagicMock()
    session.get_wallet_balance.return_value = {
        "retCode": 0,
        "result": {"list": [{"coin": [{"coin": "HYPE", "walletBalance": "0"}]}]},
    }
    snap = get_position(session, "spot", SYMBOL)
    assert snap.status is PositionStatus.FLAT


def test_spot_open_inventory() -> None:
    session = MagicMock()
    session.get_wallet_balance.return_value = {
        "retCode": 0,
        "result": {"list": [{"coin": [{"coin": "HYPE", "walletBalance": "12.5"}]}]},
    }
    snap = get_position(session, "spot", SYMBOL)
    assert snap.status is PositionStatus.OPEN
    assert snap.position is not None
    assert snap.position["size"] == 12.5
    assert snap.position["side"] == "Buy"


def test_spot_api_error_is_unknown() -> None:
    session = MagicMock()
    session.get_wallet_balance.return_value = {
        "retCode": 10001,
        "retMsg": "fail",
        "result": {},
    }
    snap = get_position(session, "spot", SYMBOL)
    assert snap.status is PositionStatus.UNKNOWN


def test_spot_empty_account_list_is_unknown_not_flat() -> None:
    session = MagicMock()
    session.get_wallet_balance.return_value = {
        "retCode": 0,
        "result": {"list": []},
    }
    snap = get_position(session, "spot", SYMBOL)
    assert snap.status is PositionStatus.UNKNOWN


def test_generic_exception_is_unknown_without_raising() -> None:
    session = _session_with_positions(side_effect=RuntimeError("boom"))
    snap = get_position(session, "linear", SYMBOL)
    assert snap.status is PositionStatus.UNKNOWN
    assert "RuntimeError" in snap.reason
