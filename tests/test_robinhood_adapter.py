import pytest

from nando.drawdown_guard import DrawdownLimitBreached
from nando.robinhood_adapter import RobinhoodAdapter, build_guardrail


class FakeSession:
    """Stands in for an authenticated MCP session, so these tests exercise
    the adapter's wiring logic without needing a live Robinhood connection."""

    def __init__(self):
        self.calls = []
        self.equity = 10_000.0

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "get_portfolio":
            return {"equity": self.equity}
        if name == "place_equity_order":
            return {"status": "filled", **arguments}
        raise AssertionError(f"unexpected tool call: {name}")


def test_get_equity_calls_get_portfolio(tmp_path):
    session = FakeSession()
    adapter = RobinhoodAdapter(session)
    assert adapter.get_equity() == 10_000.0
    assert session.calls == [("get_portfolio", {})]


def test_get_equity_scopes_to_account_id(tmp_path):
    session = FakeSession()
    adapter = RobinhoodAdapter(session, account_id="agentic-1")
    adapter.get_equity()
    assert session.calls == [("get_portfolio", {"account_id": "agentic-1"})]


def test_place_order_calls_place_equity_order(tmp_path):
    session = FakeSession()
    adapter = RobinhoodAdapter(session)
    result = adapter.place_order("AAPL", 10, side="buy")
    assert session.calls == [
        ("place_equity_order", {"symbol": "AAPL", "quantity": 10, "side": "buy"})
    ]
    assert result["status"] == "filled"


def test_build_guardrail_blocks_orders_past_monthly_limit(tmp_path):
    session = FakeSession()
    guardrail = build_guardrail(session, tmp_path / "state.json", limit_pct=0.10)

    guardrail.place_order_if_allowed("AAPL", 10)
    assert ("place_equity_order", {"symbol": "AAPL", "quantity": 10, "side": "buy"}) in session.calls

    session.equity = 8_900.0  # -11%, past the 10% limit
    with pytest.raises(DrawdownLimitBreached):
        guardrail.place_order_if_allowed("AAPL", 5)

    orders_placed = [c for c in session.calls if c[0] == "place_equity_order"]
    assert len(orders_placed) == 1  # the breached order never reached the session
