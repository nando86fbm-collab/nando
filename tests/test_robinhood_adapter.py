import pytest

from nando.drawdown_guard import DrawdownLimitBreached
from nando.robinhood_adapter import OrderNotConfirmed, RobinhoodAdapter, build_guardrail

ACCOUNT = "505131441"


class FakeSession:
    """Stands in for an authenticated MCP session, so these tests exercise
    the adapter's wiring logic without needing a live Robinhood connection."""

    def __init__(self):
        self.calls = []
        self.total_value = 10_000.0

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "get_portfolio":
            return {"total_value": self.total_value, "equity_value": self.total_value, "cash": "0"}
        if name in ("review_equity_order", "place_equity_order"):
            return {"status": "filled" if name == "place_equity_order" else "reviewed", **arguments}
        raise AssertionError(f"unexpected tool call: {name}")


def test_get_equity_reads_total_value(tmp_path):
    session = FakeSession()
    adapter = RobinhoodAdapter(session, account_number=ACCOUNT)
    assert adapter.get_equity() == 10_000.0
    assert session.calls == [("get_portfolio", {"account_number": ACCOUNT})]


def test_review_order_calls_review_equity_order(tmp_path):
    session = FakeSession()
    adapter = RobinhoodAdapter(session, account_number=ACCOUNT)
    result = adapter.review_order("AAPL", side="buy", type="market", quantity=10)
    assert session.calls == [
        (
            "review_equity_order",
            {
                "account_number": ACCOUNT,
                "symbol": "AAPL",
                "side": "buy",
                "type": "market",
                "quantity": "10",
            },
        )
    ]
    assert result["status"] == "reviewed"


def test_place_order_without_confirm_raises_and_does_not_call_session(tmp_path):
    session = FakeSession()
    adapter = RobinhoodAdapter(session, account_number=ACCOUNT)
    with pytest.raises(OrderNotConfirmed):
        adapter.place_order("AAPL", side="buy", type="market", quantity=10)
    assert session.calls == []  # never reached the real order tool


def test_place_order_with_confirm_calls_place_equity_order(tmp_path):
    session = FakeSession()
    adapter = RobinhoodAdapter(session, account_number=ACCOUNT)
    result = adapter.place_order("AAPL", side="buy", type="market", quantity=10, confirm=True)
    assert session.calls == [
        (
            "place_equity_order",
            {
                "account_number": ACCOUNT,
                "symbol": "AAPL",
                "side": "buy",
                "type": "market",
                "quantity": "10",
            },
        )
    ]
    assert result["status"] == "filled"


def test_place_order_requires_exactly_one_of_quantity_or_dollar_amount(tmp_path):
    session = FakeSession()
    adapter = RobinhoodAdapter(session, account_number=ACCOUNT)
    with pytest.raises(ValueError):
        adapter.place_order("AAPL", side="buy", type="market", confirm=True)
    with pytest.raises(ValueError):
        adapter.place_order(
            "AAPL", side="buy", type="market", quantity=10, dollar_amount=100, confirm=True
        )


def test_place_order_passes_ref_id(tmp_path):
    session = FakeSession()
    adapter = RobinhoodAdapter(session, account_number=ACCOUNT)
    adapter.place_order(
        "AAPL", side="buy", type="market", quantity=10, confirm=True, ref_id="abc-123"
    )
    assert session.calls[0][1]["ref_id"] == "abc-123"


def test_build_guardrail_blocks_orders_past_monthly_limit_even_with_confirm(tmp_path):
    session = FakeSession()
    guardrail = build_guardrail(session, tmp_path / "state.json", account_number=ACCOUNT, limit_pct=0.10)

    guardrail.place_order_if_allowed("AAPL", side="buy", type="market", quantity=10, confirm=True)
    assert ("place_equity_order", {
        "account_number": ACCOUNT, "symbol": "AAPL", "side": "buy", "type": "market", "quantity": "10",
    }) in session.calls

    session.total_value = 8_900.0  # -11%, past the 10% limit
    with pytest.raises(DrawdownLimitBreached):
        guardrail.place_order_if_allowed("AAPL", side="buy", type="market", quantity=5, confirm=True)

    orders_placed = [c for c in session.calls if c[0] == "place_equity_order"]
    assert len(orders_placed) == 1  # the breached order never reached the session


def test_build_guardrail_still_requires_confirm(tmp_path):
    session = FakeSession()
    guardrail = build_guardrail(session, tmp_path / "state.json", account_number=ACCOUNT)

    with pytest.raises(OrderNotConfirmed):
        guardrail.place_order_if_allowed("AAPL", side="buy", type="market", quantity=10)
