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
   ▼                                │
模板组合过滤                    可选 Step 6: 情感验证
   │                          (调用 news_sentiment)
   ├──────────────┐
   ▼              ▼
[dev] 策略开发台   [live] 日常盯盘台
开放历史回测       消费定稿 Trial + 每日刷新
```

`analysis` 产出突破和评分，`mining` 挖掘阈值并生成模板回写 configs，其中 `template_validator` 的 OOS 验证流程可选集成情感筛选（直接调用 `news_sentiment` 公共 API）。`dev` 作为策略开发入口驱动全流程；`live` 作为生产盯盘入口消费定稿 Trial，两者共享 `analysis` 扫描器和 `BreakoutStrategy/UI/`（charts + styles）共用 UI 基础设施，但数据目录与状态机独立。策略参数统一由顶层 `BreakoutStrategy/param_loader.py` (SSoT) 加载。

## 模块

| 模块 | 代码目录 | 文档 | 职责 |
|------|---------|------|------|
| 突破扫描 | `BreakoutStrategy/analysis/` | [modules/突破扫描模块.md](modules/突破扫描模块.md) | 凸点识别 + 突破检测 + 多因子质量评分 |
| 数据挖掘 | `BreakoutStrategy/mining/` | [modules/数据挖掘模块.md](modules/数据挖掘模块.md) | 因子阈值优化 + 模板组合生成 + Trial 物化 + 可选情感验证 |
| 新闻情感 | `BreakoutStrategy/news_sentiment/` | [modules/新闻情感分析.md](modules/新闻情感分析.md) | 多源采集 + LLM 分析 + 时间衰减聚合 |
| 开发态 UI (dev) | `BreakoutStrategy/dev/` | [modules/dev.md](modules/dev.md) | 批量扫描、参数编辑、模板过滤、图表浏览（开发态） |
| 日常盯盘 | `BreakoutStrategy/live/` | [modules/live.md](modules/live.md) | 消费定稿 Trial + 每日全市场扫描 + 筛选面板（生产态） |
| 共享 UI | `BreakoutStrategy/UI/` | [modules/UI.md](modules/UI.md) | dev / live 共用的纯 UI 基础设施（charts、styles） |
| 策略参数 SSoT | `BreakoutStrategy/param_loader.py` | — | 统一加载 / 访问 scan_params、quality_scorer 参数 |
| 特征库 | `BreakoutStrategy/feature_library/` | [modules/feature_library.md](modules/feature_library.md) | breakout 样本 → GLM-4V 多图归纳 candidate → Librarian L0 cosine 合并 + Beta-Binomial 累积 P5 |

> 添加/更新模块文档：运行 `update-ai-context` skill。

## 术语

| 术语               | 含义 |
|------------------|------|
| breakout / bo    | 突破点（价格有效穿越阻力位的 K 线） |
| peak / pk        | 凸点，即被识别的阻力位 |
| level            | 因子评级（离散化后的因子档位） |
| factor           | 评分因子（由 `FACTOR_REGISTRY` 统一注册） |
| trial            | 挖掘流水线的一次参数组合实验 |
| sentiment_lift   | 情感筛选前后的 median label 差值 |
| effective_buffer | 因子自身所需最小 lookback，由 `FeatureCalculator._effective_buffer` SSOT；`max_effective_buffer` 聚合为下游 buffer 派生 |
| range_meta       | `df.attrs["range_meta"]`，scanner 写入的三层范围元数据（pkl/scan/compute/label ideal-actual 双值） |
| ChartRangeSpec   | 图表范围契约 dataclass，由 `UI/charts/range_utils.py` 导出，Dev/Live UI 共用降级可视化 |
