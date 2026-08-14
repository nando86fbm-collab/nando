from nando.drawdown_guard import MonthlyDrawdownGuard
from nando.premarket_check import premarket_check


def test_premarket_check_reports_ok_status(tmp_path):
    guard = MonthlyDrawdownGuard(tmp_path / "state.json")
    guard.evaluate(10_000)  # establishes this month's baseline

    status = premarket_check(guard, get_equity=lambda: 9_500)
    assert status.current_equity == 9_500
    assert status.baseline_equity == 10_000
    assert not status.breached


def test_premarket_check_reports_breach_without_raising(tmp_path):
    guard = MonthlyDrawdownGuard(tmp_path / "state.json")
    guard.evaluate(10_000)  # establishes this month's baseline

    status = premarket_check(guard, get_equity=lambda: 8_500)  # -15%
    assert status.breached
    assert status.drawdown_pct < -0.10


def test_premarket_check_calls_get_equity_exactly_once(tmp_path):
    guard = MonthlyDrawdownGuard(tmp_path / "state.json")
    calls = []

    def get_equity():
        calls.append(1)
        return 10_000

    premarket_check(guard, get_equity)
    assert len(calls) == 1
