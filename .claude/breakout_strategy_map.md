# BreakoutStrategy 代码地图（参考实现）

> `BreakoutStrategy/` 是 path2 的前身突破选股流水线，现作为开发 path2 时的参考，**基本不再使用**。
> 各模块架构意图详见 `.claude/docs/modules/` 下对应文档；系统级数据流见 `.claude/docs/system_outline.md`。

- `analysis/` — 突破检测、因子计算、质量评分 → [docs/modules/突破扫描模块.md](docs/modules/突破扫描模块.md)
- `mining/` — 因子阈值挖掘 + 模板组合生成 → [docs/modules/数据挖掘模块.md](docs/modules/数据挖掘模块.md)
- `news_sentiment/` — 新闻情感分析 → [docs/modules/新闻情感分析.md](docs/modules/新闻情感分析.md)
- `dev/` — 开发态 UI（批量扫描、参数编辑、图表浏览、模板生成工作流） → [docs/modules/dev.md](docs/modules/dev.md)
- `live/` — 实盘盯盘应用（UI + pipeline） → [docs/modules/live.md](docs/modules/live.md)
- `UI/` — dev / live 共享的纯 UI 基础设施（charts、styles） → [docs/modules/UI.md](docs/modules/UI.md)
- `param_loader.py`（顶层）— 策略参数 SSoT
- `factor_registry.py`（顶层）— 因子元数据
