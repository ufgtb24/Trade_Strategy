# Impact 参数校准 Pipeline 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 输出 3 个 prompt 文件 + 1 个使用说明 + 1 个验证脚本 + 移除 analyzer.py 的 f_fail 惩罚。

**Architecture:** 所有 Claude Code 任务以 prompt 文件形式交付，用户自行执行。参数校准通过 ralph-loop 迭代完成。f_fail 移除使失败项对公式透明。

**Tech Stack:** Python, Claude Code prompts, ralph-loop

**Spec:** `docs/superpowers/specs/2026-03-25-calibration-pipeline-design.md`

---

### Task 1: 移除 analyzer.py 的 f_fail 惩罚

**Files:**
- Modify: `BreakoutStrategy/news_sentiment/analyzer.py:36,260-262`
- Test: `tests/news_sentiment/test_time_decay.py`

- [ ] **Step 1: 修改 analyzer.py — 移除 _ALPHA 常量**

删除 `analyzer.py:36`:
```python
_ALPHA = 0.5          # 失败惩罚强度
```

- [ ] **Step 2: 修改 analyzer.py — 移除 f_fail 逻辑，n 改为只计有效项**

将 `analyzer.py:180`:
```python
n = len(analyzed_items)
```
改为：
```python
n_total = len(analyzed_items)
```

将 `analyzer.py:260-262`:
```python
        # Step 4: 失败惩罚
        f_fail = 1.0 - (fail_count / n) * _ALPHA if n > 0 else 0.0
        confidence = round(max(0.0, min(1.0, base_conf * f_fail)), 4)
```
改为：
```python
        # Step 4: clamp confidence（失败项已在 Step 0 过滤，不惩罚）
        n = n_p + n_n + n_u  # 有效项数
        confidence = round(max(0.0, min(1.0, base_conf)), 4)
```

- [ ] **Step 3: 修改 analyzer.py — 更新 docstring**

将 `_summarize` docstring 中:
```
        4. 失败惩罚 f_fail
```
改为：
```
        4. clamp confidence（失败项在 Step 0 已过滤，对公式透明）
```

- [ ] **Step 4: 修改 analyzer.py — 更新 _generate_reasoning 和 SummaryResult 中的 n 引用**

`_generate_reasoning` 调用处（约 L270）的 `n` 参数改为 `n_total`（reasoning 需要报告总分析条数）:
```python
        reasoning = self._generate_reasoning(
            ticker, date_from, date_to,
            n_total, n_p, n_n, n_u, w_p, w_n, rho, sentiment,
            confidence, s_score, fail_count, analyzed_items,
        )
```

日志和 SummaryResult 中的 `n` 同样改为 `n_total`（报告总数，含失败项）:
```python
        logger.info(
            f"[Summarize] sentiment_score={s_score:+.4f} "
            f"(rho={rho:+.3f}, conf={confidence:.4f}, "
            f"n={n_total}, p/n/u={n_p}/{n_n}/{n_u})"
        )

        return SummaryResult(
            ...
            total_count=n_total,
            fail_count=fail_count,
            ...
        )
```

- [ ] **Step 5: 修改 api.py — 移除 empty SummaryResult 中的多余注释（如有）**

检查 `api.py:102` 的空输入 SummaryResult 构造，确认不引用 `_ALPHA`。（当前代码不引用，但需确认。）

- [ ] **Step 6: 运行测试**

Run: `uv run pytest tests/news_sentiment/ -v`
Expected: ALL PASS（f_fail 对现有测试影响极小，因为测试中 fail_count=0）

- [ ] **Step 7: Commit**

```bash
git add BreakoutStrategy/news_sentiment/analyzer.py
git commit -m "refactor: remove f_fail penalty — failed items are transparent to aggregation"
```

---

### Task 2: 创建 build_scenarios_prompt.txt

**Files:**
- Create: `scripts/experiments/build_scenarios_prompt.txt`

- [ ] **Step 1: 创建文件**

```
scripts/experiments/build_scenarios_prompt.txt
```

Prompt 内容要点：

1. **任务**：在 `scripts/experiments/impact_scenarios.json` 中生成 35-45 个合成场景
2. **格式**：
```json
[{"id": 1, "name": "Edge: 1P extreme alone", "category": "edge",
  "items": [{"s": "positive", "impact": "extreme"}]}]
```
3. **分层要求**：
   - edge (1-2条, 8-10个场景): 单条 extreme、2P pure、1P+1N、2N pure 等
   - cold (3-5条, 8-10个): 方向一致/冲突/混合 impact、全 negligible
   - medium (7-12条, 10-12个): 多 impact 等级混合、含失败项(impact="")、neutral 多数
   - hot (15-20条, 8-10个): 高 negligible 占比、extreme 单条主导、大量 neutral 稀释
4. **必须覆盖的特有场景**：
   - 单条 extreme positive（测 scarcity n_dir=1）
   - 单条 extreme negative（测 scarcity + 损失厌恶）
   - 5 条 low positive vs 1 条 extreme positive（测 impact 等级区分）
   - 3 条 low positive + 1 条 extreme negative（测不对称冲突）
   - 10 条 negligible positive（应给极低 confidence）
   - 5 条 medium positive + 2 条失败项(impact="")（测失败项透明）
   - 3 neutral + 2 positive(extreme) + 1 negative(negligible)
   - 5P + 5N 全 medium（完美冲突）
   - 15P + 5U 全 low（热门股低 impact）
5. **impact 值域说明**：
   - negligible: <0.5% 股价影响 → 映射 0.05
   - low: 0.5-2% → 映射 0.20
   - medium: 2-5% → 映射 0.50
   - high: 5-15% → 映射 0.80
   - extreme: >15% → 映射 1.00
   - "": 分析失败 → 映射 0.0（被公式过滤，不参与聚合）
6. **输出位置**：`scripts/experiments/impact_scenarios.json`
7. **参考**：已有 confidence 版场景定义在 `.worktrees/news/scripts/experiments/calibration_v2.py`

- [ ] **Step 2: Commit**

```bash
git add scripts/experiments/build_scenarios_prompt.md
git commit -m "docs: add prompt for generating impact calibration scenarios"
```

---

### Task 3: 创建 impact_labeling_prompt.txt

**Files:**
- Create: `scripts/experiments/impact_labeling_prompt.txt`

- [ ] **Step 1: 创建文件**

Prompt 内容要点：

1. **任务**：读取 `scripts/experiments/impact_scenarios.json`，对每个场景生成综合判断
2. **双 Agent 模式**（参考 `.worktrees/news/scripts/experiments/AI标注_prompt.txt`）：
   - Agent 1 (Opus 4.6): 模拟金融分析师，对每个场景评估综合 sentiment 和 sentiment_score
   - Agent 2 (Opus 4.6): 审核 Agent 1 的结果，检查是否符合投资逻辑，不符合则修正
3. **输入格式**：每个场景是 `[{"s": sentiment, "impact": level}, ...]` 的列表（不含新闻内容）
4. **输出格式**：
```json
[{"id": 1, "name": "...", "composition": "2P(high,medium)+0N+0U=2",
  "sentiment": "positive", "sentiment_score": 0.28, "reasoning": "..."}]
```
5. **sentiment_score 定义**：
   - 范围 [-1.0, +1.0]
   - positive → 正值, negative → 负值, neutral → 0
   - 指数饱和曲线自然控制上限（_CAP=1.0）
6. **impact 等级定义**（必须包含在 prompt 中让 AI 理解权重含义）：
   - negligible: 对股价几乎无影响（<0.5%），近乎无贡献
   - low: 轻微影响（0.5-2%）
   - medium: 中等影响（2-5%）
   - high: 重大影响（5-15%）
   - extreme: 剧烈影响（>15%），可改变公司前景
7. **标注原则**（关键，必须包含）：
   - **损失厌恶**：同等 impact 下，负面新闻的影响 > 正面（约 1.5-2x 心理权重）
   - **scarcity 保护**：< 3 条方向性新闻时不给高 confidence（即使方向一致）
   - **impact 主导**：1 条 extreme 新闻的权重应远大于多条 negligible/low
   - **negligible 近乎透明**：10 条 negligible positive 不应给出显著的 sentiment_score
   - **冲突压低**：正负平衡时 sentiment_score ≈ 0，无论 impact 多高
   - **neutral 不稀释**：neutral 新闻是背景噪音，不应降低方向性信号的强度
8. **不要迭代公式设计**：专注模拟投资分析师的认知完成标注
9. **输出文件**：`scripts/experiments/impact_baseline.json`

- [ ] **Step 2: Commit**

```bash
git add scripts/experiments/impact_labeling_prompt.md
git commit -m "docs: add prompt for AI labeling of impact scenarios"
```

---

### Task 4: 创建 calibrate_prompt.txt

**Files:**
- Create: `scripts/experiments/calibrate_prompt.txt`

- [ ] **Step 1: 创建文件**

Prompt 内容要点：

1. **任务说明**：
   - 读取 `scripts/experiments/impact_scenarios.json`（场景定义）
   - 读取 `scripts/experiments/impact_baseline.json`（AI 标注的 ground truth）
   - 读取 `BreakoutStrategy/news_sentiment/analyzer.py` 中的公式和当前参数
   - 通过迭代搜索找到最优的 `_K`, `_GAMMA`, `_OPP_NEG` 三个参数

2. **公式计算要求**（最关键的部分，必须精确复制）：
   - 必须精确复制 `analyzer.py:_summarize` 的逻辑，包括：
     - evidence 归一化：`evidence = (w_p + w_n) / tw_sum_dir`
     - scarcity 保护：`scarcity = min(1.0, n_dir / SCARCITY_N)`
     - 时间权重：合成场景中全部设为 1.0
     - certainty × sufficiency × (1 - opp_penalty) 三分支计算
     - sentiment_score = sign(rho) × confidence
   - 不可使用旧版 `optimize_params.py` 的公式（缺少归一化和 scarcity）
   - 失败项（impact=""）直接跳过，不参与聚合，不惩罚（无 f_fail）

3. **固定参数**（不搜索，直接用当前值）：
   ```
   W0_RHO=0.1, DELTA=0.1, CAP=1.0,
   BETA=2.2, BETA_POS=1.15, LA=1.02,
   K_NEU=2.47, SCARCITY_N=3,
   CONFLICT_POW=3.0, CONFLICT_CAP=0.15
   ```

4. **搜索参数和范围**：
   ```
   _K:      [0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55]  (7 值)
   _GAMMA:  [0.20, 0.25, 0.30, 0.35, 0.40, 0.50]         (6 值)
   _OPP_NEG:[0.10, 0.15, 0.20, 0.25, 0.30]                (5 值)
   ```
   总组合 210 个

5. **评估指标**：
   - `sent_match`: formula sentiment == baseline sentiment 的匹配数
   - `MAD`: mean(|formula_sentiment_score - baseline_sentiment_score|)
   - `severe`: |diff| >= 0.15 的场景数
   - `score = -sent_match * 1000 + MAD * 100 + severe * 10`（越低越好）
   - MAD 基于有符号 sentiment_score，方向错误会被双重惩罚

6. **ralph-loop 要求**：
   - 使用 `/loop` 命令迭代
   - 每轮：选择一组参数 → 对所有场景计算公式输出 → 计算 MAD、sent_match、severe → 报告结果
   - 搜索策略：先粗扫（每个参数取 3-4 个代表值，~60 组合），找到最佳区域后精扫（附近 ±1 步长）
   - 每轮结束报告：当前最优参数、MAD、sent_match、最差 3 个场景

7. **终止条件**：
   - sent_match = 100%（所有场景方向正确）且 MAD < 0.05
   - 或连续 3 轮最优 MAD 无改善（< 0.001 变化）
   - 终止时输出最优参数和完整场景对比表

8. **输出**：
   - 将最优参数写入 `analyzer.py` 的模块级常量（直接编辑 `_K`, `_GAMMA`, `_OPP_NEG` 的值）
   - 输出校准报告到 `scripts/experiments/calibration_report.md`，包含：
     - 最优参数及 MAD
     - 每个场景的 formula vs baseline 对比
     - 最差场景分析
     - 消融分析：逐一恢复到旧值（_K=0.55, _GAMMA=0.40, _OPP_NEG=0.20）的 dMAD

- [ ] **Step 2: Commit**

```bash
git add scripts/experiments/calibrate_prompt.md
git commit -m "docs: add prompt for ralph-loop parameter calibration"
```

---

### Task 5: 创建 collect_validation_data.py

**Files:**
- Create: `scripts/experiments/collect_validation_data.py`

- [ ] **Step 1: 创建文件**

```python
"""
真实数据验证脚本

采集多股票多时段新闻，用校准后参数聚合，验证 sentiment_score 分布合理性。
"""

import dataclasses
import json
import logging
from pathlib import Path

from BreakoutStrategy.news_sentiment.api import analyze


def main():
    # === 参数配置 ===
    tickers = ["AAPL", "TSLA", "NVDA", "META", "AMZN", "JPM", "JNJ", "XOM"]
    periods = [
        ("2025-04-01", "2025-04-14"),
        ("2025-07-01", "2025-07-14"),
        ("2025-10-01", "2025-10-14"),
    ]
    output_dir = Path("datasets/news_sentiment_validation")
    log_level = "INFO"

    # === 初始化 ===
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
        datefmt='%H:%M:%S',
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    # === 采集 + 分析 ===
    all_scores = []
    all_impacts = []
    total_fail = 0
    total_items = 0

    for ticker in tickers:
        for date_from, date_to in periods:
            print(f"\n--- {ticker} {date_from}~{date_to} ---")
            report = analyze(ticker, date_from, date_to)

            # 存储
            d_from = date_from.replace('-', '')
            d_to = date_to.replace('-', '')
            filepath = output_dir / f"{ticker}_{d_from}_{d_to}.json"
            data = dataclasses.asdict(report)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"  Saved to {filepath}")

            # 统计
            s = report.summary
            print(f"  Score: {s.sentiment_score:+.4f} ({s.sentiment})")
            print(f"  Items: {len(report.items)}, fail: {s.fail_count}")
            all_scores.append(s.sentiment_score)
            total_fail += s.fail_count
            total_items += s.total_count
            for item in report.items:
                if item.sentiment.impact:
                    all_impacts.append(item.sentiment.impact)

    # === 汇总验证 ===
    print(f"\n{'='*60}")
    print(f"VALIDATION SUMMARY")
    print(f"{'='*60}")
    print(f"Total reports: {len(tickers) * len(periods)}")
    print(f"Total items: {total_items}, fail: {total_fail} "
          f"({total_fail/total_items*100:.1f}%)" if total_items > 0 else "")

    # sentiment_score 分布
    if all_scores:
        in_range = sum(1 for s in all_scores if -0.50 <= s <= 0.50)
        print(f"\nsentiment_score distribution:")
        print(f"  Range [-0.50, +0.50]: {in_range}/{len(all_scores)} "
              f"({in_range/len(all_scores)*100:.0f}%) — target >80%")
        print(f"  Min: {min(all_scores):+.4f}, Max: {max(all_scores):+.4f}")

    # impact 分布
    if all_impacts:
        from collections import Counter
        counts = Counter(all_impacts)
        total_imp = len(all_impacts)
        low_pct = (counts.get('negligible', 0) + counts.get('low', 0)) / total_imp
        print(f"\nimpact distribution:")
        for level in ['negligible', 'low', 'medium', 'high', 'extreme']:
            c = counts.get(level, 0)
            print(f"  {level:>10}: {c:3d} ({c/total_imp*100:5.1f}%)")
        print(f"  negligible+low: {low_pct*100:.0f}% — target >50%")

    # 失败率
    if total_items > 0:
        fail_rate = total_fail / total_items
        print(f"\nLLM fail rate: {fail_rate*100:.1f}% — target <5%")
        status = "PASS" if fail_rate < 0.05 else "FAIL"
        print(f"  Status: {status}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 运行语法检查**

Run: `uv run python -c "import ast; ast.parse(open('scripts/experiments/collect_validation_data.py').read())"`
Expected: 无输出（无语法错误）

- [ ] **Step 3: Commit**

```bash
git add scripts/experiments/collect_validation_data.py
git commit -m "feat: add real data validation script for impact calibration"
```

---

### Task 6: 创建 CALIBRATION_GUIDE.md

**Files:**
- Create: `scripts/experiments/CALIBRATION_GUIDE.md`

- [ ] **Step 1: 创建文件**

内容结构：

```markdown
# Impact 参数校准操作指南

## 概述
本流程通过 3 个 prompt 文件 + 1 个验证脚本完成 impact 聚合公式的参数校准。
所有 Claude Code 任务以 prompt 形式交付，可自行修改后执行。

## 前置条件
- impact 版本的 SentimentResult 已部署（confidence → impact/impact_value）
- analyzer.py 中 f_fail 惩罚已移除
- DeepSeek API key 已配置

## 步骤

### Step 1: 生成合成场景
**执行**: 在 Claude Code 中粘贴 `build_scenarios_prompt.txt` 的内容
**输入**: 无（prompt 中已包含所有要求）
**输出**: `scripts/experiments/impact_scenarios.json`（35-45 个场景）
**验证**: 检查场景数量、分层覆盖度、impact 等级分布

### Step 2: AI 标注
**执行**: 在 Claude Code 中粘贴 `impact_labeling_prompt.txt` 的内容
**输入**: Step 1 生成的 `impact_scenarios.json`
**输出**: `scripts/experiments/impact_baseline.json`
**验证**: 检查标注数量与场景数一致、sentiment_score 在 [-0.80, 0.80] 范围内

### Step 3: 参数校准
**执行**: 在 Claude Code 中粘贴 `calibrate_prompt.txt` 的内容
**输入**: Step 1 的 `impact_scenarios.json` + Step 2 的 `impact_baseline.json`
**输出**:
  - `analyzer.py` 中 `_K`, `_GAMMA`, `_OPP_NEG` 更新为最优值
  - `scripts/experiments/calibration_report.md` 校准报告
**验证**: MAD < 0.05, sent_match = 100%

### Step 4: 真实数据验证
**执行**: `uv run python scripts/experiments/collect_validation_data.py`
**输入**: Finnhub API + DeepSeek API
**输出**: `datasets/news_sentiment_validation/*.json` + 终端统计
**验证**:
  - sentiment_score >80% 在 [-0.50, +0.50]
  - impact negligible+low > 50%
  - LLM 失败率 < 5%

## 复用指南

业务需求变更时：
- **修改 impact 等级定义** → 修改 `build_scenarios_prompt.txt` 和 `impact_labeling_prompt.txt` 中的定义，从 Step 1 重新执行
- **修改标注原则**（如损失厌恶强度）→ 修改 `impact_labeling_prompt.txt`，从 Step 2 重新执行
- **修改搜索参数范围** → 修改 `calibrate_prompt.txt`，从 Step 3 重新执行
- **修改验证股票/时段** → 修改 `collect_validation_data.py` 中的 main() 参数

## 文件清单

| 文件 | 类型 | 用途 |
|------|------|------|
| `build_scenarios_prompt.txt` | Prompt | 生成合成场景 |
| `impact_labeling_prompt.txt` | Prompt | AI 双 agent 标注 |
| `calibrate_prompt.txt` | Prompt | ralph-loop 参数搜索 |
| `collect_validation_data.py` | Script | 真实数据验证 |
| `impact_scenarios.json` | Data (生成) | 场景定义 |
| `impact_baseline.json` | Data (生成) | 标注结果 |
| `calibration_report.md` | Report (生成) | 校准报告 |
```

- [ ] **Step 2: Commit**

```bash
git add scripts/experiments/CALIBRATION_GUIDE.md
git commit -m "docs: add calibration guide for impact parameter tuning"
```

---

### Task 7: 全局验证

- [ ] **Step 1: 确认所有文件存在**

```bash
ls scripts/experiments/build_scenarios_prompt.md \
   scripts/experiments/impact_labeling_prompt.md \
   scripts/experiments/calibrate_prompt.md \
   scripts/experiments/collect_validation_data.py \
   scripts/experiments/CALIBRATION_GUIDE.md
```

- [ ] **Step 2: 确认 _ALPHA 已移除**

```bash
grep -n '_ALPHA' BreakoutStrategy/news_sentiment/analyzer.py
```
Expected: 无匹配

- [ ] **Step 3: 确认 f_fail 已移除**

```bash
grep -n 'f_fail' BreakoutStrategy/news_sentiment/analyzer.py
```
Expected: 无匹配

- [ ] **Step 4: 运行全套测试**

Run: `uv run pytest tests/news_sentiment/ -v`
Expected: ALL PASS
