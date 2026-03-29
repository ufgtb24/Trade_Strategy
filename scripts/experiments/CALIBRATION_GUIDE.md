# Impact 参数校准操作指南

## 概述

本流程通过 4 个 prompt 文件 + 1 个验证脚本完成 impact 聚合公式的参数校准。
所有 Claude Code 任务以 prompt 形式交付，可自行修改后执行。

## 前置条件

- impact 版本的 SentimentResult 已部署（confidence → impact/impact_value）
- analyzer.py 中 f_fail 惩罚已移除
- DeepSeek API key 已配置
- Finnhub API key 已配置（Step 5 验证用）

## 步骤

### Step 1: 生成合成场景

**执行**: 在 Claude Code 中粘贴 `build_scenarios_prompt.txt` 的内容
**输入**: 无（prompt 中已包含所有要求）
**输出**: `scripts/experiments/impact_scenarios.json`（35-45 个场景）
**验证**: 检查场景数量、分层覆盖度、impact 等级分布

### Step 2: AI 标注

**执行**: 在 Claude Code 中粘贴 `impact_labeling_prompt.md` 的内容
**输入**: Step 1 生成的 `impact_scenarios.json`
**输出**: `scripts/experiments/impact_baseline.json`
**验证**: 检查标注数量与场景数一致、sentiment_score 在 [-1.0, 1.0] 范围内

### Step 3: 标注差异分析

**执行**: 在 Claude Code 中粘贴 `analysis_prompt.md` 的内容
**输入**: Step 1 的 `impact_scenarios.json` + Step 2 的 `impact_baseline.json` + `analyzer.py`
**输出**: `scripts/experiments/labeling_analysis.md`
**验证**: 阅读报告，了解当前公式与标注的差异方向

### Step 4: 公式校准

**执行**: 在 Claude Code 中粘贴 `calibrate_prompt.md` 的内容，使用 `/loop` 迭代
**输入**: Step 1-3 的所有产出 + `analyzer.py` 源码 + 已有研究文档
**输出**:
  - `BreakoutStrategy/news_sentiment/analyzer.py` 的 `_summarize` 逻辑改进
  - `scripts/experiments/calibration_report.md` 校准/诊断报告
**验证**: sent_match = 100%, MAD < 0.08, 理论属性不退化
**注意**: AI 拥有完全自主权，可能调整参数、修改公式结构、或两者兼做。红线约束见 prompt。

### Step 5: 真实数据验证

**执行**: `uv run python scripts/experiments/collect_validation_data.py`
**输入**: Finnhub API + DeepSeek API
**输出**: `datasets/news_sentiment_validation/*.json` + 终端统计
**验证**:
  - sentiment_score >80% 在 [-0.50, +0.50]
  - impact negligible+low > 50%
  - LLM 失败率 < 5%

## 复用指南

业务需求变更时，只需修改对应的 prompt 文件：

| 变更类型 | 修改文件 | 从哪步重新执行 |
|---------|---------|--------------|
| 修改 impact 等级定义 | `build_scenarios_prompt.txt` + `impact_labeling_prompt.md` | Step 1 |
| 修改标注原则（如损失厌恶强度） | `impact_labeling_prompt.md` | Step 2 |
| 修改搜索参数范围 | `calibrate_prompt.txt` | Step 4 |
| 修改验证股票/时段 | `collect_validation_data.py` 中 main() 参数 | Step 5 |
| 修改聚合公式结构 | 所有 prompt 文件 | Step 1 |

## 文件清单

| 文件 | 类型 | 用途 |
|------|------|------|
| `build_scenarios_prompt.txt` | Prompt | 生成合成场景 |
| `impact_labeling_prompt.md` | Prompt | AI 双 agent 标注 |
| `analysis_prompt.md` | Prompt | 标注 vs 公式差异分析 |
| `calibrate_prompt.txt` | Prompt | ralph-loop 参数搜索 |
| `collect_validation_data.py` | Script | 真实数据验证 |
| `impact_scenarios.json` | Data (生成) | 场景定义 |
| `impact_baseline.json` | Data (生成) | 标注结果 |
| `labeling_analysis.md` | Report (生成) | 差异分析报告 |
| `calibration_report.md` | Report (生成) | 校准报告 |

## 注意事项

- 每个 prompt 文件是自包含的，可以独立修改和执行
- 生成的 JSON 文件可以多次用于实验（修改 prompt 后重新执行即可）
- 校准完成后的参数会直接写入 `analyzer.py`，运行测试确认无回归
- Step 5 验证会使用 cache，重跑不会重复调用 LLM（除非清空 cache）
- AI 标注和公式输出的 score 范围均为 [-1.0, +1.0]
