# BreakoutStrategy 代码地图（参考实现）

> `BreakoutStrategy/` 是 path2 的前身突破选股流水线，现作为开发 path2 时的参考，**基本不再使用**。
> 它的词汇（factor / trial / 模板组合）不属于 path2 的任何上下文，别与 path2 的同名词（bo / pk）混淆。
> path2 主线的代码地图见根目录 `CLAUDE.md`。

数据流：`历史 K 线 → [analysis] 凸点识别 → 突破检测 → 多因子评分 → 模板组合过滤 → [dev] 开发台 / [live] 盯盘台`；
其中因子阈值与模板组合由 `[mining]` 搜索产出，`news_sentiment` 只作可选的辅助维度、不独立决策。

- `analysis/` — 突破检测、因子计算、质量评分
- `mining/` — 因子阈值挖掘 + 模板组合生成 + OOS 验证
- `news_sentiment/` — 新闻情感分析（带 confidence，辅助维度）
- `dev/` — 开发态 UI（批量扫描、参数编辑、图表浏览、模板生成工作流）
- `live/` — 实盘盯盘应用（UI + pipeline）
- `UI/` — dev / live 共享的纯 UI 基础设施（charts、styles），不得反向依赖应用层
- `param_loader.py`（顶层）— 策略参数 SSoT
- `factor_registry.py`（顶层）— 因子清单与元数据的唯一权威，analysis / mining 均从此消费
