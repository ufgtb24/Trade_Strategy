# System Outline

> 突破选股策略系统 — 美股量化交易，自动识别阻力位突破并驱动观察/交易流程。
>
> 本文档只反映当前代码状态。不含历史演进、不含未实现模块。需要更新时运行 `update-ai-context` skill。

## 核心数据流

```
历史 K 线
   │
   ▼
[analysis] 凸点识别 → 突破检测 → 多因子质量评分
   │                                ↑
   │                          因子阈值 + 模板
   │                                │
   │                   [mining] 因子阈值挖掘 + 模板组合生成 + OOS 验证
   ▼
模板组合过滤（用 mining 产出的模板对 analysis 的突破打分过滤）
   │
   ▼
[cascade] 级联验证：top-K 模板命中样本 → 批量情感分析 → 筛选 + 统计报告
   │                                          ↑
   │                                   [news_sentiment] 情感分析引擎
   ▼
[UI] 展示股票 + 批量扫描 + 模板过滤操作
```

`analysis` 产出突破和评分，`mining` 挖掘阈值并生成模板回写 configs，`cascade` 桥接 mining 输出与 news_sentiment 进行级联情感筛选，`UI` 作为用户入口驱动全流程。

## 模块

| 模块 | 代码目录 | 文档 | 职责 |
|------|---------|------|------|
| 突破扫描 | `BreakoutStrategy/analysis/` | [modules/突破扫描模块.md](modules/突破扫描模块.md) | 凸点识别 + 突破检测 + 多因子质量评分 |
| 数据挖掘 | `BreakoutStrategy/mining/` | [modules/数据挖掘模块.md](modules/数据挖掘模块.md) | 因子阈值优化 + 模板组合生成 + Trial 物化 |
| 新闻情感 | `BreakoutStrategy/news_sentiment/` | [modules/新闻情感分析.md](modules/新闻情感分析.md) | 多源采集 + LLM 分析 + 时间衰减聚合 |
| 级联验证 | `BreakoutStrategy/cascade/` | [modules/级联验证模块.md](modules/级联验证模块.md) | 桥接 mining→sentiment 的批量情感筛选 + 统计报告 |
| 交互式 UI | `BreakoutStrategy/UI/` | [modules/交互式UI.md](modules/交互式UI.md) | 批量扫描、参数编辑、模板过滤、图表浏览 |

> 添加/更新模块文档：运行 `update-ai-context` skill。

## 术语

| 术语 | 含义 |
|------|------|
| breakout / bo | 突破点（价格有效穿越阻力位的 K 线） |
| peak / pk | 凸点，即被识别的阻力位 |
| level | 因子评级（离散化后的因子档位） |
| factor | 评分因子（由 `FACTOR_REGISTRY` 统一注册） |
| trial | 挖掘流水线的一次参数组合实验 |
| cascade | 级联验证（模板筛选 + 情感过滤的联合流程） |
| cascade_lift | 情感筛选前后的 median label 差值 |
