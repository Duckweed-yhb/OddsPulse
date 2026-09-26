"""Agent 判断层的数据结构：LLM 的返回被解析成 MarketVerdict。"""
from __future__ import annotations

from pydantic import BaseModel


class MarketVerdict(BaseModel):
    """模型对一个市场的综合判断（结构化输出）。"""
    market_id: str
    signal: str          # "watch"（值得关注）| "caution"（信号可疑）| "normal"（正常）
    confidence: float    # 0..1，模型对判断的自信度
    reason: str          # 一句话理由
