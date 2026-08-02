"""Adapter wiring Robinhood's Agentic Trading MCP into TradingGuardrail.

UNVERIFIED: written against the tool names and response shapes publicly
reported for Robinhood's Agentic Trading MCP server
(https://agent.robinhood.com/mcp/trading) - `get_portfolio` returning an
"equity" field, and `place_equity_order` taking symbol/quantity/side. This
environment's connection to that server has not completed OAuth, so none of
this has been checked against the live tool schema. Confirm the real tool
names, arguments, and response shape (e.g. via an authenticated MCP client's
`list_tools()`/`call_tool()`) once the connector is authenticated, and adjust
this file if anything doesn't match.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol

from nando.drawdown_guard import MonthlyDrawdownGuard, TradingGuardrail


class MCPSession(Protocol):
    """Minimal shape needed from an authenticated MCP client session
    connected to the Robinhood trading server."""

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any: ...


class RobinhoodAdapter:
    """Adapts Robinhood's Agentic Trading MCP tools to the get_equity/
    place_order shape TradingGuardrail expects.

    `session` must already be authenticated against
    https://agent.robinhood.com/mcp/trading (e.g. via `claude mcp login
    trading` completing the OAuth flow, or any MCP client that did the same).
    Trades run in Robinhood's isolated agentic account, not the main
    brokerage account.
    """

    def __init__(self, session: MCPSession, account_id: Optional[str] = None):
        self.session = session
        self.account_id = account_id

    def _account_args(self) -> dict[str, Any]:
        return {"account_id": self.account_id} if self.account_id else {}

    def get_equity(self) -> float:
        result = self.session.call_tool("get_portfolio", self._account_args())
        return float(result["equity"])

    def place_order(self, symbol: str, quantity: float, side: str = "buy", **kwargs: Any) -> Any:
        arguments: dict[str, Any] = {
            "symbol": symbol,
            "quantity": quantity,
            "side": side,
            **self._account_args(),
            **kwargs,
        }
        return self.session.call_tool("place_equity_order", arguments)


def build_guardrail(
    session: MCPSession,
    state_path: str,
    limit_pct: float = 0.10,
    account_id: Optional[str] = None,
) -> TradingGuardrail:
    """Wire an authenticated Robinhood MCP session into a drawdown-guarded
    trading interface."""
    adapter = RobinhoodAdapter(session, account_id=account_id)
    guard = MonthlyDrawdownGuard(state_path, limit_pct=limit_pct)
    return TradingGuardrail(
        guard=guard,
        get_equity=adapter.get_equity,
        place_order=adapter.place_order,
    )
