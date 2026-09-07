# Context Map

本仓库有两个上下文：事件表达框架本身，和它的调试可视化工具。两者说的不是一门语言，所以分开。

## Contexts

- [path2](./path2/CONTEXT.md)：事件表达框架与走势词汇——把股票走势建模成多级不可变事件，再用 DAG 约束求解出命中。覆盖 `path2/` 与 `path2_apps/`。
- [path2_web](./path2_web/CONTEXT.md)：调试可视化工具的词汇——事件在图上怎么摆、显示到哪一档、参数怎么试。覆盖 `path2_web/`（FastAPI 后端）与 `path2_web_ui/`（Vue3 前端）。

## Relationships

- **path2 → path2_web**：path2_web 是 path2 的纯投影层，它渲染的对象就是 path2 里的 event / node / match。读 web 词条时如果碰到核心词，以 `path2/CONTEXT.md` 那份为准。
- **path2_web 不含走势语义**：界面不知道 bo 和 burst 各是什么，只按 node 分轨、按 where 分列。

## 不在本 map 内

`BreakoutStrategy/` 是 path2 的前身突破选股流水线、日常不动，它的词汇（factor / trial / 模板组合）不属于以上任何上下文；代码地图见 `.claude/breakout_strategy_map.md`。
