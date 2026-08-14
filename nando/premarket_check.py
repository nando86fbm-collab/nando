"""Pre-market drawdown status check.

A read-only companion to `MonthlyDrawdownGuard`/`TradingGuardrail`: fetches
current equity and reports where it stands against the monthly drawdown
limit, without placing or blocking any orders. Meant to be run once before
market open so the drawdown state is visible ahead of the trading session.
"""

from __future__ import annotations

from typing import Callable

from nando.drawdown_guard import DrawdownStatus, MonthlyDrawdownGuard


def premarket_check(
    guard: MonthlyDrawdownGuard, get_equity: Callable[[], float]
) -> DrawdownStatus:
    """Fetch current equity and return the drawdown status against `guard`.

    Unlike `guard.guard()`, this never raises on a breach - it just reports
    it, so it's safe to run purely for visibility (e.g. a pre-market
    routine) before any trading decision is made.
    """
    equity = get_equity()
    return guard.status(equity)
