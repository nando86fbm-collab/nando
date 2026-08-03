"""Adapter wiring Robinhood's Agentic Trading MCP into TradingGuardrail.

Verified against the live tool schema (mcp__robinhood__*) on 2026-08-02:
- `get_portfolio` returns `total_value`/`equity_value`/`cash`/`buying_power`,
  not a bare `equity` field.
- `place_equity_order` requires `account_number` (not `account_id`) and a
  required `type` ('market' | 'limit' | 'stop_market' | 'stop_limit').
- `place_equity_order` places a REAL order with REAL money. Robinhood's own
  tool contract expects `review_equity_order` to be called first and the
  order confirmed explicitly - this adapter enforces that: `place_order`
  raises `OrderNotConfirmed` unless called with `confirm=True`, and callers
  are expected to have shown the user the `review_order()` result first.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol

from nando.drawdown_guard import MonthlyDrawdownGuard, TradingGuardrail


class OrderNotConfirmed(Exception):
    """Raised when place_order is called without confirm=True.

    Robinhood's place_equity_order executes with real money; this adapter
    requires the caller to have reviewed the order (via review_order) and
    explicitly opted in before it will place anything.
    """


class MCPSession(Protocol):
    """Minimal shape needed from an authenticated MCP client session
    connected to the Robinhood trading server."""

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any: ...


class RobinhoodAdapter:
    """Adapts Robinhood's Agentic Trading MCP tools to the get_equity/
    place_order shape TradingGuardrail expects.

    `session` must already be authenticated against
    https://agent.robinhood.com/mcp/trading. `account_number` must be an
    agentic_allowed=true account (get_accounts) - Robinhood rejects orders
    against the main brokerage account.
    """

    def __init__(self, session: MCPSession, account_number: str):
        self.session = session
        self.account_number = account_number

    def get_equity(self) -> float:
        result = self.session.call_tool(
            "get_portfolio", {"account_number": self.account_number}
        )
        return float(result["total_value"])

    def _order_args(
        self,
        symbol: str,
        side: str,
        type: str,
        quantity: Optional[float],
        dollar_amount: Optional[float],
        **kwargs: Any,
    ) -> dict[str, Any]:
        if (quantity is None) == (dollar_amount is None):
            raise ValueError("provide exactly one of quantity or dollar_amount")
        arguments: dict[str, Any] = {
            "account_number": self.account_number,
            "symbol": symbol,
            "side": side,
            "type": type,
            **kwargs,
        }
        if quantity is not None:
            arguments["quantity"] = str(quantity)
        else:
            arguments["dollar_amount"] = str(dollar_amount)
        return arguments

    def review_order(
        self,
        symbol: str,
        side: str,
        type: str = "market",
        quantity: Optional[float] = None,
        dollar_amount: Optional[float] = None,
        **kwargs: Any,
    ) -> Any:
        """Simulate an order without placing it - current quote plus
        pre-trade alerts (buying power, PDT, halts, etc.). Call this and
        show the result to the user before place_order(confirm=True)."""
        arguments = self._order_args(symbol, side, type, quantity, dollar_amount, **kwargs)
        return self.session.call_tool("review_equity_order", arguments)

    def place_order(
        self,
        symbol: str,
        side: str,
        type: str = "market",
        quantity: Optional[float] = None,
        dollar_amount: Optional[float] = None,
        confirm: bool = False,
        ref_id: Optional[str] = None,
        **kwargs: Any,
    ) -> Any:
        """Place a real order with real money. Raises OrderNotConfirmed
        unless confirm=True - review_order() first and get the user's
        explicit go-ahead before setting it."""
        if not confirm:
            raise OrderNotConfirmed(
                f"Refusing to place {side} {symbol} without confirm=True. "
                "Call review_order() first, show the user the estimated "
                "cost and any alerts, and only pass confirm=True after they "
                "explicitly agree."
            )
        arguments = self._order_args(symbol, side, type, quantity, dollar_amount, **kwargs)
        if ref_id is not None:
            arguments["ref_id"] = ref_id
        return self.session.call_tool("place_equity_order", arguments)


def build_guardrail(
    session: MCPSession,
    state_path: str,
    account_number: str,
    limit_pct: float = 0.10,
) -> TradingGuardrail:
    """Wire an authenticated Robinhood MCP session into a drawdown-guarded
    trading interface. `place_order_if_allowed(...)` still requires
    confirm=True to actually place anything - the monthly drawdown check
    and the per-order confirmation gate are independent safeguards."""
    adapter = RobinhoodAdapter(session, account_number=account_number)
    guard = MonthlyDrawdownGuard(state_path, limit_pct=limit_pct)
    return TradingGuardrail(
        guard=guard,
        get_equity=adapter.get_equity,
        place_order=adapter.place_order,
    )
