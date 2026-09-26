"""分析框架一：从一堆市场里提取"值得看"的市场。

这是纯函数模块——不碰网络、不碰数据库，输入市场列表就能算。好处：易测试、可复现、
README 里能把打分公式讲清楚。

打分思路（可调整，README 会写明白）：
  - 流动性：成交量越大越可信。volume_score = min(volume / 100_000, 1.0)
  - 不确定性：概率越接近 0.5，结果越不确定、越值得关注。
      uncertainty_score = 1 - abs(probability - 0.5) * 2   （p=0.5 时取 1，p=0/1 时取 0）
  - 综合：interest = 0.6 * volume_score + 0.4 * uncertainty_score
"""
from __future__ import annotations

from ..data.models import Market

VOLUME_NORM = 100_000.0        # 成交量归一化基准（美元）
VOLUME_WEIGHT = 0.6            # 流动性权重
UNCERTAINTY_WEIGHT = 0.4       # 不确定性权重


def volume_score(market: Market) -> float:
    """成交量分：封顶 1.0，防止单个超大市场压过一切。"""
    if VOLUME_NORM <= 0:
        return 0.0
    return min(market.volume / VOLUME_NORM, 1.0)


def uncertainty_score(market: Market) -> float:
    """不确定性分：概率越接近 0.5 越高。"""
    return max(0.0, 1.0 - abs(market.probability - 0.5) * 2.0)


def interest_score(market: Market) -> float:
    """综合关注度。"""
    return (
        VOLUME_WEIGHT * volume_score(market)
        + UNCERTAINTY_WEIGHT * uncertainty_score(market)
    )


def select_interesting_markets(markets: list[Market], top_n: int = 20) -> list[Market]:
    """过滤无效市场，按关注度降序取 top_n。返回原始 Market 列表（排序后）。"""
    valid = [
        m for m in markets
        if 0.0 <= m.probability <= 1.0 and m.volume > 0
    ]
    ranked = sorted(valid, key=interest_score, reverse=True)
    return ranked[: max(0, top_n)]
