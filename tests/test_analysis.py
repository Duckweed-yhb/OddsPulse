"""分析框架的单元测试：全部用合成数据，不依赖网络。"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from odds_pulse.analysis import compute_change, detect_anomalies, has_enough_history, select_interesting_markets
from odds_pulse.data import Market

NOW = datetime.now(timezone.utc)


def _market(prob: float, volume: float, market_id: str = "m1") -> Market:
    return Market(
        source="sample", market_id=market_id, question="测试市场",
        probability=prob, volume=volume, captured_at=NOW,
    )


# ---- extract ----
def test_select_sorts_by_volume_and_uncertainty():
    markets = [
        _market(0.9, 50_000, "high_prob_high_vol"),
        _market(0.5, 200_000, "mid_uncertain_high_vol"),
        _market(0.5, 1000, "low_vol"),
    ]
    top = select_interesting_markets(markets, top_n=10)
    # 成交量高 + 概率接近 0.5 的应排最前
    assert top[0].market_id == "mid_uncertain_high_vol"


def test_select_filters_zero_volume():
    markets = [_market(0.5, 0, "zero_vol"), _market(0.5, 100, "ok")]
    top = select_interesting_markets(markets, top_n=10)
    assert all(m.volume > 0 for m in top)
    assert len(top) == 1


def test_select_top_n_limit():
    markets = [_market(0.5, 1000 * i, f"m{i}") for i in range(1, 8)]
    assert len(select_interesting_markets(markets, top_n=3)) == 3


# ---- trend ----
def test_compute_change_basic():
    assert compute_change([0.5, 0.55, 0.62]) == pytest.approx(0.12)


def test_compute_change_window():
    assert compute_change([0.5, 0.6, 0.7], window=2) == pytest.approx(0.1)


def test_compute_change_empty():
    assert compute_change([]) == 0.0


def test_has_enough_history():
    assert has_enough_history([0.5, 0.6]) is True
    assert has_enough_history([0.5]) is False


# ---- anomaly ----
def test_detect_sharp_move():
    histories = {"m1": [0.40, 0.50, 0.48]}
    signals = detect_anomalies([_market(0.48, 1000, "m1")], histories, threshold=0.05)
    kinds = {s.kind for s in signals}
    assert "sharp_move" in kinds


def test_detect_no_signal_when_stable():
    histories = {"m1": [0.5, 0.5, 0.5]}
    signals = detect_anomalies([_market(0.5, 1000, "m1")], histories, threshold=0.05)
    assert all(s.kind != "sharp_move" for s in signals)


def test_detect_ignores_insufficient_history():
    # 只有 1 个点 → 不下结论
    histories = {"m1": [0.4]}
    signals = detect_anomalies([_market(0.9, 1000, "m1")], histories, threshold=0.05)
    assert signals == []
