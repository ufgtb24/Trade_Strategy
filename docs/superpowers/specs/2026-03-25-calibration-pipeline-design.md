# Design: Impact 参数校准 Pipeline

## Context

news_sentiment 模块已从 confidence 切换到 impact。聚合公式结构不变，但加权因子从 confidence 变为 impact_value（离散 5 档映射）。impact 分布（均值 ~0.33）远低于 confidence（均值 ~0.70），3 个参数（`_K`, `_GAMMA`, `_OPP_NEG`）需要重新校准。

校准完全在 Claude Code 中完成，不写 Python 优化脚本。

## 设计决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 校准执行 | Claude Code + ralph-loop | 无需写优化脚本，Claude 直接计算公式 + 调参 |
| 标注执行 | 手动 prompt + 固化 JSON | 用户偏好，可控性强 |
| 场景/标注存储 | JSON 文件 | 可复用、prompt 不臃肿 |
| MAD 目标 | sentiment_score（有符号） | 同时惩罚方向错误和幅度偏差 |
| `compute_summary` | 复制当前 `analyzer.py` | 含归一化 evidence + scarcity |

## 交付文件

```
scripts/experiments/
├── CALIBRATION_GUIDE.md           # 使用说明书：按顺序执行各 prompt 的完整流程
├── build_scenarios_prompt.txt     # Prompt: 生成 impact_scenarios.json
├── impact_labeling_prompt.txt     # Prompt: 生成 impact_baseline.json
├── calibrate_prompt.txt           # Prompt: ralph-loop 校准（含终止条件）
└── collect_validation_data.py     # Part B: 真实数据验证脚本
```

**设计原则**：所有 Claude Code 任务只输出 prompt 文件，不直接执行。用户可自行修改 prompt 内容后再执行。

### 工作流

```
1. 本次任务输出 3 个 prompt 文件 + 1 个 Python 脚本 + analyzer.py f_fail 移除
2. 用户执行 build_scenarios_prompt.txt → 生成 impact_scenarios.json
3. 用户执行 impact_labeling_prompt.txt → 生成 impact_baseline.json
4. 用户执行 calibrate_prompt.txt → ralph-loop 自动迭代校准 → 更新 analyzer.py 参数
5. 用户运行 collect_validation_data.py → 验证
```

## Part A: 参数校准

### 1. `impact_scenarios.json` — 合成场景

35-45 个场景，按新闻数量分 4 层：

| 层级 | 条数 | 场景数 | 覆盖重点 |
|------|------|--------|---------|
| edge | 1-2 | 8-10 | 单条 extreme、2P pure、1P+1N 等 |
| cold | 3-5 | 8-10 | 方向一致/冲突/混合 impact 等级 |
| medium | 7-12 | 10-12 | 多 impact 等级混合、含失败项 |
| hot | 15-20 | 8-10 | 高 negligible 占比、extreme 单条等 |

格式：
```json
[
    {
        "id": 1,
        "name": "Edge: 1P extreme alone",
        "category": "edge",
        "items": [{"s": "positive", "impact": "extreme"}]
    }
]
```

必须覆盖的 impact 特有场景：
- 单条场景（n_dir=1，测 scarcity）
- 含失败项（impact=""，测 f_fail）
- extreme 单条 vs 多条 low（同方向）
- impact 不对称冲突（3 low positive + 1 extreme negative）
- 全 negligible（应给极低 confidence）
- 混合 neutral + 方向性 + 不同 impact 等级

### 2. `impact_labeling_prompt.txt` — AI 标注 Prompt

双 agent 模式：Agent1 评估 + Agent2 审核。

输入：`impact_scenarios.json` 中的场景列表
输出：每个场景的 `(sentiment, sentiment_score)`

Prompt 要点：
- sentiment_score = sign × confidence ∈ [-1.0, +1.0]
- 明确 impact 等级定义（百分比锚点）
- 关键原则：损失厌恶、scarcity 保护、negligible 近乎无贡献

### 3. `impact_baseline.json` — 标注结果（用户生成）

```json
[
    {
        "id": 1,
        "name": "Edge: 1P extreme alone",
        "sentiment": "positive",
        "sentiment_score": 0.22,
        "reasoning": "..."
    }
]
```

### 4. `calibrate_prompt.txt` — Claude Code 校准 Prompt

这是用户在 Claude Code 中执行的完整指令，包含：

1. **任务说明**：读 `impact_scenarios.json` + `impact_baseline.json` + `analyzer.py` 参数
2. **公式计算要求**：必须精确复制 `analyzer.py:_summarize` 的逻辑（含归一化 evidence、scarcity、时间权重全设 1.0）
3. **固定参数**：`_BETA`=2.2, `_BETA_POS`=1.15, `_LA`=1.02 等（不搜索）
4. **搜索参数和范围**：`_K` ∈ [0.25, 0.55], `_GAMMA` ∈ [0.20, 0.50], `_OPP_NEG` ∈ [0.10, 0.30]
5. **评估指标**：MAD(formula_sentiment_score, ai_sentiment_score) + sent_match + severe count
6. **ralph-loop 要求**：使用 `/loop` 命令迭代，每轮尝试一组参数 → 计算全场景 MAD → 报告结果 → 调整参数
7. **终止条件**：MAD < 0.05 且 sent_match = 100%，或连续 3 轮无改善
8. **输出**：最优参数写入 `analyzer.py` 的模块级常量

## Part B: 真实数据验证

### `collect_validation_data.py`

```python
def main():
    tickers = ["AAPL", "TSLA", "NVDA", "META", "AMZN", "JPM", "JNJ", "XOM"]
    periods = [
        ("2025-04-01", "2025-04-14"),
        ("2025-07-01", "2025-07-14"),
        ("2025-10-01", "2025-10-14"),
    ]
    output_dir = "datasets/news_sentiment_validation"
```

流程：顺序调用 `api.analyze()` → `dataclasses.asdict()` 序列化 → 存 JSON → 汇总统计

验证标准：
- sentiment_score >80% 落在 [-0.50, +0.50]
- impact negligible + low > 50%
- LLM 解析失败率 < 5%

## analyzer.py 改动：移除 f_fail 惩罚

失败项（impact_value=0.0）是 LLM API 层面的问题，不应影响聚合结果。当前 `f_fail = 1.0 - (fail_count / n) * _ALPHA` 将基础设施噪声混入业务逻辑。

改动：
- 移除 `_ALPHA` 常量
- 移除 `f_fail` 计算和应用（`confidence = base_conf * f_fail` → `confidence = base_conf`）
- `fail_count` 保留用于日志和 SummaryResult 报告，但不参与 confidence 计算
- `n` 改为只计有效项（当前 `n = len(analyzed_items)` 包含失败项）

## 不变的部分

- `analyzer.py` 公式结构不改（校准后只更新 3 个常量值）
- 现有 cache / api / filter 不改
