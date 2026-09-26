"""分析框架二：追踪概率变化。

输入是"每个市场的一段历史概率序列"（最早 → 最新），输出该市场在一段时间内的变化量。
纯函数，便于测试。
"""
from __future__ import annotations

from typing import Sequence


def compute_change(history: Sequence[float], window: int | None = None) -> float:
    """返回历史序列在最近 window 条内的变化量（最新 - 基线）。

    基线取窗口内最早一条；若数据不足一条，返回 0.0。
    """
    seq = list(history)
    if not seq:
        return 0.0
    if window is not None and window > 0:
        seq = seq[-window:]
    if len(seq) < 1:
        return 0.0
    return seq[-1] - seq[0]


def has_enough_history(history: Sequence[float], min_points: int = 2) -> bool:
    """数据点是否足够用于变化检测（默认至少 2 个时间点）。"""
    return len(history) >= min_points
