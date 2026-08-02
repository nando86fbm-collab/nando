from datetime import datetime, timezone

import pytest

from nando.drawdown_guard import (
    DrawdownLimitBreached,
    MonthlyDrawdownGuard,
    TradingGuardrail,
)


def make_guard(tmp_path, limit_pct=0.10):
    return MonthlyDrawdownGuard(tmp_path / "state.json", limit_pct=limit_pct)


def test_first_call_sets_baseline_with_zero_drawdown(tmp_path):
    guard = make_guard(tmp_path)
    assert guard.evaluate(10_000) == 0.0


def test_no_breach_within_limit(tmp_path):
    guard = make_guard(tmp_path)
    guard.evaluate(10_000)
    assert guard.evaluate(9_100) == pytest.approx(-0.09)
    assert not guard.is_breached(9_100)
    guard.guard(9_100)  # should not raise


def test_breach_exactly_at_limit(tmp_path):
    guard = make_guard(tmp_path)
    guard.evaluate(10_000)
    assert guard.is_breached(9_000)  # exactly -10%
    with pytest.raises(DrawdownLimitBreached):
        guard.guard(9_000)


def test_breach_beyond_limit(tmp_path):
    guard = make_guard(tmp_path)
    guard.evaluate(10_000)
    assert guard.is_breached(8_500)
    with pytest.raises(DrawdownLimitBreached) as exc_info:
        guard.guard(8_500)
    assert exc_info.value.drawdown_pct == pytest.approx(-0.15)
    assert exc_info.value.limit_pct == 0.10


def test_gain_is_not_a_breach(tmp_path):
    guard = make_guard(tmp_path)
    guard.evaluate(10_000)
    assert not guard.is_breached(11_000)


def test_month_rollover_resets_baseline(tmp_path):
    guard = make_guard(tmp_path)
    january = datetime(2026, 1, 15, tzinfo=timezone.utc)
    february = datetime(2026, 2, 1, tzinfo=timezone.utc)

    guard.evaluate(10_000, when=january)
    with pytest.raises(DrawdownLimitBreached):
        guard.guard(8_500, when=january)  # -15% in January

    assert guard.evaluate(8_500, when=february) == 0.0  # new baseline
    guard.guard(8_500, when=february)  # should not raise anymore


def test_breach_persists_across_calls_within_same_month(tmp_path):
    guard = make_guard(tmp_path)
    when = datetime(2026, 3, 1, tzinfo=timezone.utc)
    guard.evaluate(10_000, when=when)

    with pytest.raises(DrawdownLimitBreached):
        guard.guard(8_000, when=datetime(2026, 3, 10, tzinfo=timezone.utc))
    # still breached later in the same month even if equity partially recovers
    # but stays below the limit
    with pytest.raises(DrawdownLimitBreached):
        guard.guard(8_900, when=datetime(2026, 3, 20, tzinfo=timezone.utc))
    # recovering above the limit clears the breach state (not a "halted for
    # the rest of the month" latch - it's a live drawdown check)
    guard.guard(9_200, when=datetime(2026, 3, 25, tzinfo=timezone.utc))


def test_state_persists_across_guard_instances(tmp_path):
    state_path = tmp_path / "state.json"
    when = datetime(2026, 4, 5, tzinfo=timezone.utc)

    guard1 = MonthlyDrawdownGuard(state_path)
    guard1.evaluate(10_000, when=when)

    guard2 = MonthlyDrawdownGuard(state_path)
    assert guard2.evaluate(9_000, when=when) == pytest.approx(-0.10)


def test_rejects_invalid_limit_pct(tmp_path):
    with pytest.raises(ValueError):
        MonthlyDrawdownGuard(tmp_path / "state.json", limit_pct=1.5)
    with pytest.raises(ValueError):
        MonthlyDrawdownGuard(tmp_path / "state.json", limit_pct=0)


def test_trading_guardrail_blocks_order_past_limit(tmp_path):
    guard = make_guard(tmp_path)
    guard.evaluate(10_000)

    equity = {"value": 10_000}
    orders_placed = []

    guardrail = TradingGuardrail(
        guard=guard,
        get_equity=lambda: equity["value"],
        place_order=lambda symbol, qty: orders_placed.append((symbol, qty)),
    )

    guardrail.place_order_if_allowed("AAPL", 10)
    assert orders_placed == [("AAPL", 10)]

    equity["value"] = 8_900  # -11%, past the 10% limit
    with pytest.raises(DrawdownLimitBreached):
        guardrail.place_order_if_allowed("AAPL", 5)
    assert orders_placed == [("AAPL", 10)]  # second order never placed
