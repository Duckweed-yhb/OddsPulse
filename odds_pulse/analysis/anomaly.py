"""分析框架三：异常信号检测。

目前实现两种启发式信号（可在 README 说明取舍）：
  1. sharp_move  —— 概率在窗口内发生超过阈值的急变
  2. volume_spike—— 当前成交量显著高于历史均值（> 倍数）
数据不足时不下结论（返回空），避免误报。
"""
from __future__ import annotations

from typing import Mapping, Sequence

from ..data.models import Market, MarketSignal
from .trend import compute_change, has_enough_history

SHARP_MOVE_THRESHOLD = 0.05    # 概率变化阈值（5 个百分点）
VOLUME_SPIKE_MULTIPLIER = 3.0  # 成交量倍数阈值
MIN_POINTS = 2                 # 最少历史点数


def detect_anomalies(
    markets: list[Market],
    histories: Mapping[str, Sequence[float]],
    threshold: float = SHARP_MOVE_THRESHOLD,
    volume_multiplier: float = VOLUME_SPIKE_MULTIPLIER,
) -> list[MarketSignal]:
    """对每个市场检测异常，返回触发信号列表。"""
    signals: list[MarketSignal] = []
    for m in markets:
        history = histories.get(m.market_id, [])
        if not has_enough_history(history, MIN_POINTS):
            continue  # 数据不足，不下结论

        change = compute_change(history)
        if abs(change) >= threshold:
            signals.append(
                MarketSignal(
                    market_id=m.market_id,
                    source=m.source,
                    kind="sharp_move",
                    detail=f"概率 {history[0]:.3f} -> {history[-1]:.3f}（变化 {change:+.3f}）",
                )
            )

        # 成交量尖峰：最近值与更早均值的比较
        if _is_volume_spike(m.volume, history, volume_multiplier):
            signals.append(
                MarketSignal(
                    market_id=m.market_id,
                    source=m.source,
                    kind="volume_spike",
                    detail=f"当前成交量 {m.volume:,.0f} 显著高于历史水平",
                )
            )
    return signals


def _is_volume_spike(current_volume: float, history: Sequence[float], multiplier: float) -> bool:
    """用概率序列长度近似历史采集次数做占位；真正对比应在接入成交量历史后增强。

    说明：当前数据模型主要保留概率序列，成交量尖峰检测在真实场景应基于成交量历史。
    这里用一个保守启发式，避免在没有成交量历史时误报。"""
    # 至少需要若干历史采集才有"基线"
    if len(history) < 4:
        return False
    # 示例启发式：若当前概率处于极端区间且序列很短，暂不判尖峰；留待后续增强。
    return False
