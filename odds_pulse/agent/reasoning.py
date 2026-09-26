"""Agent 判断层：把分析信号交给 LLM，产出结构化判断。

设计要点：
  - 无 API key 或调用失败时，回退到确定性启发式判断（heuristic_verdict），
    保证整条 pipeline 在任何环境都能跑通，不会因为 LLM 不可用而崩溃。
  - LLM 返回的文本不保证是合法 JSON，用 Pydantic 解析 + try/except 兜底。
"""
from __future__ import annotations

import json

import httpx

from ..config import Config
from ..data.models import Market, MarketSignal
from .schema import MarketVerdict


def build_prompt(market: Market, signals: list[MarketSignal]) -> str:
    """构造给 LLM 的 prompt：市场信息 + 信号 + 明确的输出格式要求。"""
    signal_lines = "\n".join(f"- {s.kind}: {s.detail}" for s in signals) or "- 无"
    return f"""你是一个预测市场分析助手。请基于给定市场数据与信号，给出一个结构化判断。

市场：{market.question}
来源：{market.source}
当前概率：{market.probability:.3f}
成交量：${market.volume:,.0f}
检测到的信号：
{signal_lines}

请只输出 JSON，字段必须为：
{{"market_id": "{market.market_id}", "signal": "watch|caution|normal",
 "confidence": 0.0 到 1.0 之间的数字, "reason": "一句话中文理由"}}

其中 signal 取值含义：
- watch：值得进一步关注
- caution：信号可能失真或需要人工确认
- normal：无异常
"""


def call_llm(prompt: str, config: Config) -> MarketVerdict:
    """调用兼容 OpenAI 的 Chat Completions 接口，返回结构化判断。"""
    if not config.has_llm_key:
        raise RuntimeError("未设置 OPENAI_API_KEY")

    url = f"{config.llm_base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": config.llm_model,
        "messages": [
            {"role": "system", "content": "你是严谨的预测市场分析助手，只输出 JSON。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {config.openai_api_key}"}

    resp = httpx.post(url, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    # 解析并校验为 MarketVerdict；解析失败抛错，由上层兜底
    return MarketVerdict.model_validate_json(content)


def heuristic_verdict(market: Market, signals: list[MarketSignal]) -> MarketVerdict:
    """无 LLM 时的确定性兜底：根据规则直接给判断。"""
    if any(s.kind == "sharp_move" for s in signals):
        return MarketVerdict(
            market_id=market.market_id,
            signal="watch",
            confidence=0.7,
            reason="检测到概率急变，按规则标记为值得关注",
        )
    if any(s.kind == "volume_spike" for s in signals):
        return MarketVerdict(
            market_id=market.market_id,
            signal="caution",
            confidence=0.5,
            reason="成交量异常，信号可能需要人工确认",
        )
    return MarketVerdict(
        market_id=market.market_id,
        signal="normal",
        confidence=0.9,
        reason="无显著异常信号",
    )


def judge_market(market: Market, signals: list[MarketSignal], config: Config) -> MarketVerdict:
    """对外入口：优先走 LLM，失败/无 key 时回退启发式。"""
    if config.has_llm_key:
        try:
            return call_llm(build_prompt(market, signals), config)
        except Exception as exc:  # 网络 / 解析 / 接口错误一律兜底
            return MarketVerdict(
                market_id=market.market_id,
                signal="normal",
                confidence=0.0,
                reason=f"llm unavailable ({type(exc).__name__})",
            )
    return heuristic_verdict(market, signals)
