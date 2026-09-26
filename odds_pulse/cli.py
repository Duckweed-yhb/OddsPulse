"""OddsPulse 命令行入口。

用法示例（在项目根目录、激活 venv 后）：
  python -m odds_pulse.cli run --source sample        # 全流程（离线示例数据）
  python -m odds_pulse.cli run --source polymarket    # 全流程（真实数据，需网络）
  python -m odds_pulse.cli extract --source sample
  python -m odds_pulse.cli signals --source sample
  python -m odds_pulse.cli verdict --source sample
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .analysis import detect_anomalies, select_interesting_markets
from .agent import judge_market
from .config import Config, DB_PATH
from .data import make_source
from .storage import MarketStore


def _load_histories(store: MarketStore, markets: list, limit: int = 30) -> dict[str, list[float]]:
    """为每个市场从库里加载概率历史（market_id -> [oldest...newest]）。"""
    histories: dict[str, list[float]] = {}
    for m in markets:
        history = store.get_history(m.source, m.market_id, limit=limit)
        histories[m.market_id] = [h.probability for h in history]
    return histories


def _pipeline(source_name: str, config: Config) -> dict:
    """数据接入 → 存储 → 提取 → 追踪/异常 → Agent 判断。返回可序列化的结果字典。"""
    source = make_source(source_name)
    store = MarketStore(config.db_path)
    store.init_db()

    markets = source.fetch_markets(limit=config.default_limit)
    store.save_markets(markets)

    # 提取值得关注的市场
    interesting = select_interesting_markets(markets, top_n=10)

    # 基于历史做变化与异常检测
    histories = _load_histories(store, markets)
    signals = detect_anomalies(interesting, histories)

    # Agent 判断（无 key 时自动回退启发式）
    verdicts = [judge_market(m, [s for s in signals if s.market_id == m.market_id], config)
                for m in interesting]

    return {
        "source": source_name,
        "fetched": len(markets),
        "interesting_top_n": len(interesting),
        "signals": [s.model_dump(mode="json") for s in signals],
        "verdicts": [v.model_dump(mode="json") for v in verdicts],
        "generated_at": __import__("datetime").datetime.now().isoformat(),
    }


def cmd_run(args, config: Config) -> int:
    result = _pipeline(args.source, config)
    # 终端打印简洁摘要
    print(f"[OddsPulse] 数据源={result['source']} 拉取={result['fetched']} 市场 "
          f"值得关注={result['interesting_top_n']}")
    print(f"[OddsPulse] 信号 {len(result['signals'])} 条：")
    for s in result["signals"]:
        print(f"  - {s['kind']}: {s['detail']}")
    print(f"[OddsPulse] Agent 判断（前 {min(5, len(result['verdicts']))} 个）：")
    for v in result["verdicts"][:5]:
        print(f"  - {v['market_id']}: signal={v['signal']} conf={v['confidence']:.2f} | {v['reason']}")

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[OddsPulse] 完整结果已写入 {args.out}")
    return 0


def cmd_fetch(args, config: Config) -> int:
    source = make_source(args.source)
    store = MarketStore(config.db_path)
    store.init_db()
    markets = source.fetch_markets(limit=config.default_limit)
    store.save_markets(markets)
    print(f"[OddsPulse] 拉取 {len(markets)} 个市场，已入库 {config.db_path}")
    for m in markets[:5]:
        print(f"  - {m.question[:40]} | p={m.probability:.3f} | vol=${m.volume:,.0f}")
    return 0


def cmd_extract(args, config: Config) -> int:
    markets = make_source(args.source).fetch_markets(limit=config.default_limit)
    interesting = select_interesting_markets(markets, top_n=args.top)
    print(f"[OddsPulse] 提取 {len(interesting)} 个值得关注的市场：")
    for m in interesting:
        print(f"  - {m.question[:44]} | p={m.probability:.3f} | vol=${m.volume:,.0f}")
    return 0


def cmd_signals(args, config: Config) -> int:
    source = make_source(args.source)
    store = MarketStore(config.db_path)
    store.init_db()
    markets = source.fetch_markets(limit=config.default_limit)
    store.save_markets(markets)
    interesting = select_interesting_markets(markets, top_n=args.top)
    histories = _load_histories(store, markets)
    signals = detect_anomalies(interesting, histories)
    print(f"[OddsPulse] 异常信号 {len(signals)} 条：")
    for s in signals:
        print(f"  - {s.kind}: {s.detail}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="OddsPulse", description="预测市场数据源 + 分析框架")
    sub = p.add_subparsers(dest="command", required=True)

    for name, fn, help_text in [
        ("run", cmd_run, "全流程：拉取→入库→提取→信号→Agent判断"),
        ("fetch", cmd_fetch, "拉取并入库"),
        ("extract", cmd_extract, "提取值得关注的市场"),
        ("signals", cmd_signals, "追踪变化并检测异常信号"),
    ]:
        sp = sub.add_parser(name, help=help_text)
        sp.add_argument("--source", default="sample", choices=["polymarket", "kalshi", "sample"])
        sp.add_argument("--top", type=int, default=10)
        if name == "run":
            sp.add_argument("--out", default=None, help="把完整结果写入 JSON 文件路径")
        sp.set_defaults(func=fn)
    return p


def main() -> int:
    args = build_parser().parse_args()
    config = Config()
    try:
        return args.func(args, config)
    except Exception as exc:
        print(f"[OddsPulse] 错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
