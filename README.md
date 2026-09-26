# OddsPulse

**预测市场数据源 + 分析框架。** 接入 [Polymarket](https://polymarket.com) 与 [Kalshi](https://kalshi.com) 的公开预测市场数据，统一数据结构后，做市场提取、概率变化追踪与异常信号检测，并接入一个基于 LLM 的 Agent 判断层。参考 [TradingAgents](https://github.com/tauricresearch/tradingagents) 的思路，但只保留最简、可复现的一层。

## 架构

```
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│ Polymarket API│   │  Kalshi API   │   │  SampleSource │  ← 离线示例数据（演示/CI）
└───────┬───────┘   └───────┬───────┘   └───────┬───────┘
        │                  │                    │
        └────────┬─────────┴─────────┬──────────┘
                 ▼                   │
        ┌────────────────┐           │
        │  data/ 数据接入层 │           │
        │ 统一成 Market 模型│           │
        └───────┬────────┘           │
                ▼                    │
        ┌──────────────┐             │
        │ storage/SQLite│◄───────────┘  每次采集存快照，供追踪变化
        └───────┬──────┘
                ▼
        ┌───────────────────────┐
        │ analysis/ 分析框架      │
        │ 提取 → 追踪变化 → 异常检测 │
        └───────┬───────────────┘
                ▼
        ┌───────────────────────┐
        │ agent/ LLM 判断层       │
        │ prompt + 结构化输出      │
        └───────┬───────────────┘
                ▼
        cli.py 编排 · examples/sample_output.json 样例输出
```

核心设计：**所有数据源归一成同一个 `Market` 模型**（`odds_pulse/data/models.py`），下游（存储、分析、Agent）只依赖这套抽象，不依赖任何具体数据源。新增数据源时只需实现 `MarketSource` 接口。

## 数据结构

### `Market`（统一的市场模型，`odds_pulse/data/models.py`）

| 字段 | 类型 | 说明 |
|---|---|---|
| `source` | str | 数据源标识：`polymarket` / `kalshi` / `sample` |
| `market_id` | str | 该数据源下的唯一市场标识 |
| `question` | str | 市场问题，如"特朗普会赢得 2028 大选吗" |
| `probability` | float | 当前概率（0..1，代表 YES/事件发生） |
| `volume` | float | 累计成交量（美元） |
| `captured_at` | datetime | 采集时间 |
| `notes` | str | 备注/原始标识 |

### `market_snapshots`（SQLite 表，`odds_pulse/storage/db.py`）

| 列 | 类型 | 说明 |
|---|---|---|
| source / market_id / captured_at | 主键组合 | 同市场同时间只存一条，避免重复 |
| question / probability / volume | | 该时点的市场快照 |
| notes | | 备注 |

主键 `(source, market_id, captured_at)` 保证每次采集都是"追加一条历史"，这是"追踪概率变化"的数据基础。

## 框架设计

各模块职责与关键取舍（均可用 `pytest` 测试，纯函数模块不依赖网络）：

### 1. 数据接入层 `data/`
- `base.MarketSource`：抽象接口，`fetch_markets() -> list[Market]`。
- `polymarket.py`：`GET gamma-api.polymarket.com/markets`，把 `outcomePrices[0]` 转成概率、`volumeNum` 转成成交量。
- `kalshi.py`：`GET api.elections.kalshi.com/trade-api/v2/markets`，Kalshi 用美分报价，`yes_ask/100` 转概率；可选 `KALSHI_API_KEY`。
- `sample.py`：**离线合成示例数据**（基线确定 + 每次采集小幅扰动），用于离线/CI/演示，字段与真实数据一致。**非真实市场数据。**

### 2. 存储层 `storage/`
- 每次采集写入 `market_snapshots`，为变化追踪保留历史；所有 SQL 使用参数化查询。

### 3. 分析框架 `analysis/`（纯函数，可测）
- **提取** `extract.py`：给每个市场算 `interest_score`：
  `interest = 0.6 * min(volume/100_000, 1) + 0.4 * (1 - |probability-0.5|*2)`
  —— 权重 0.6/0.4 代表"更看重流动性、其次不确定性"，取 top N。
- **追踪变化** `trend.py`：`compute_change(history, window)` 返回窗口内概率变化量；数据不足不下结论。
- **异常检测** `anomaly.py`：`sharp_move`（窗口内概率变化 ≥ 5 个百分点）、`volume_spike`（占位启发式）。阈值在文件常量中，README 写明取值。

### 4. Agent 判断层 `agent/`
- `build_prompt` 把"市场 + 信号"拼成 prompt，要求 LLM 只输出 JSON。
- `schema.MarketVerdict`（Pydantic）：`market_id / signal / confidence / reason`，结构化输出。
- **降级设计**：无 `OPENAI_API_KEY` 或调用失败时，回退到确定性 `heuristic_verdict`，保证整条 pipeline 不会因 LLM 不可用而崩溃。

## 快速开始

```bash
# 1. 克隆并进入
git clone <your-repo-url> && cd OddsPulse

# 2. 创建虚拟环境并安装依赖
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
pip install -r requirements-dev.txt

# 3. 全流程（离线示例数据，无需网络）
python -m odds_pulse.cli run --source sample --out examples/sample_output.json

# 4. 单元测试
pytest

# 5. 真实数据（需要能访问到对应站点，或配置代理）
python -m odds_pulse.cli run --source polymarket
python -m odds_pulse.cli run --source kalshi
```

子命令：`run`（全流程） / `fetch`（拉取入库） / `extract`（提取） / `signals`（信号）。

### 启用真实 LLM Agent 层（可选）

设置环境变量后，`run` 会自动调用 LLM 返回结构化判断；未设置时自动使用启发式兜底，不影响运行：

```bash
export OPENAI_API_KEY=sk-...            # 必填
export LLM_BASE_URL=https://api.openai.com/v1   # 可选，兼容 OpenAI 的地址
export LLM_MODEL=gpt-4o-mini           # 可选
```

> ⚠️ API key 只从环境变量读取，写入 `.env` 并确保被 `.gitignore` 忽略，**绝不提交到仓库**。

## 样例输出

`examples/sample_output.json` 是 `run` 的真实输出（示例数据源），示例如下：

```json
{
  "source": "sample",
  "fetched": 40,
  "interesting_top_n": 10,
  "signals": [
    {
      "market_id": "sample-035",
      "source": "sample",
      "kind": "sharp_move",
      "detail": "概率 0.580 -> 0.523（变化 -0.057）"
    }
  ],
  "verdicts": [
    {
      "market_id": "sample-035",
      "signal": "watch",
      "confidence": 0.7,
      "reason": "检测到概率急变，按规则标记为值得关注"
    }
  ],
  "generated_at": "2026-09-26T17:07:49.797777"
}
```

> 该文件为合成示例数据的真实运行结果，用于演示 pipeline；接入真实数据源后重新运行即可得到真实输出。

## 技术栈与依赖

- **语言**：Python 3.10+（本仓库在 3.14 验证）
- **依赖**：`httpx`（HTTP）、`pydantic`（数据模型/结构化输出）；开发 `pytest`
- **存储**：SQLite（标准库 `sqlite3`），可平滑替换为 PostgreSQL

## 未来方向

- 接入 WebSocket 实时行情，支持增量更新
- 成交量历史入库，完善 `volume_spike` 检测
- 将存储替换为 PostgreSQL/Supabase，支持更大规模
- Agent 层增加多市场聚合判断与可解释性

## 说明

- `sample` 为合成示例数据，仅用于演示与开发；真实数据来自 Polymarket/Kalshi 公开接口。
- 打分权重、异常阈值均为启发式取值，见各模块常量，可随业务调整。
