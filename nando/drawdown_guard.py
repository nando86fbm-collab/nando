"""Monthly max-drawdown guardrail for trading actions.

Halts trading once account equity falls more than a configured percentage
below the equity recorded at the start of the current calendar month.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional


class DrawdownLimitBreached(Exception):
    """Raised when an action is blocked by the monthly drawdown limit."""

    def __init__(self, drawdown_pct: float, limit_pct: float, month: str):
        self.drawdown_pct = drawdown_pct
        self.limit_pct = limit_pct
        self.month = month
        super().__init__(
            f"Monthly drawdown {drawdown_pct:.2%} exceeds -{limit_pct:.0%} limit "
            f"for {month}; trading halted until next month."
        )


class MonthlyDrawdownGuard:
    """Tracks equity against a rolling calendar-month baseline.

    The baseline (start-of-month equity) is captured the first time `evaluate`
    is called in a given month and persisted to `state_path` so it survives
    restarts. Once equity drops `limit_pct` or more below that baseline, the
    guard reports a breach until the calendar month rolls over.
    """

    def __init__(self, state_path: str | Path, limit_pct: float = 0.10):
        if not 0 < limit_pct < 1:
            raise ValueError("limit_pct must be between 0 and 1 (e.g. 0.10 for 10%)")
        self.state_path = Path(state_path)
        self.limit_pct = limit_pct
        self._state: dict = self._load_state()

    def _load_state(self) -> dict:
        if self.state_path.exists():
            return json.loads(self.state_path.read_text())
        return {}

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(self._state))

    @staticmethod
    def _month_key(when: datetime) -> str:
        return when.strftime("%Y-%m")

    def _baseline_equity(self, equity: float, when: datetime) -> float:
        key = self._month_key(when)
        if self._state.get("month") != key:
            self._state = {"month": key, "start_equity": equity}
            self._save_state()
        return self._state["start_equity"]

    def evaluate(self, equity: float, when: Optional[datetime] = None) -> float:
        """Return the current month's drawdown as a fraction (negative = loss).

        Rolls the baseline over to a new month if `when` falls in a month not
        yet seen. Calling this establishes the baseline, so call it once per
        equity update even if you don't need the return value.
        """
        when = when or datetime.now(timezone.utc)
        baseline = self._baseline_equity(equity, when)
        if baseline == 0:
            return 0.0
        return (equity - baseline) / baseline

    def is_breached(self, equity: float, when: Optional[datetime] = None) -> bool:
        return self.evaluate(equity, when) <= -self.limit_pct

    def guard(self, equity: float, when: Optional[datetime] = None) -> None:
        """Raise DrawdownLimitBreached if this month's loss limit has been hit."""
        when = when or datetime.now(timezone.utc)
        drawdown = self.evaluate(equity, when)
        if drawdown <= -self.limit_pct:
            raise DrawdownLimitBreached(drawdown, self.limit_pct, self._month_key(when))


@dataclass
class TradingGuardrail:
    """Wraps a trade-execution callable so it refuses to run past the monthly
    drawdown limit.

    `get_equity` and `place_order` are expected to be thin adapters over
    whatever trading MCP/API is actually connected (e.g. Robinhood's agentic
    trading tools) - this class has no dependency on any specific broker.
    """

    guard: MonthlyDrawdownGuard
    get_equity: Callable[[], float]
    place_order: Callable[..., object]

    def place_order_if_allowed(self, *args, **kwargs):
        equity = self.get_equity()
        self.guard.guard(equity)
        return self.place_order(*args, **kwargs)
