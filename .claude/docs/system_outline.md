# System Outline

> 本 codebase 的**主线功能是 path2** —— 独立的多级事件表达框架：把"股票形态"建模为多级不可变事件 + DAG 约束求解。
> `BreakoutStrategy/` 是 path2 的前身突破选股流水线，现作为开发 path2 时的参考，基本不再使用。
>
> 本文档只反映当前代码状态。不含历史演进、不含未实现模块。需要更新时运行 `update-ai-context` skill。

## 主线：path2 事件表达框架

path2 把"股票形态"建模为多级不可变事件；形态用"声明节点 + 类型化边"两步表达，交库引擎求解匹配。与 BreakoutStrategy 因子 / 选股流水线**零耦合**。

| 模块 | 代码目录 | 文档 | 职责 |
|------|---------|------|------|
| path2 框架 | `path2/` | [modules/path2.md](modules/path2.md) | 协议地基 + dag 引擎 + 走势-无关 atoms + calc + stdlib + eval |
| path2 应用层 | `path2_apps/<走势>/` | [modules/path2_apps.md](modules/path2_apps.md) | 走势-特异形态声明（唯一应用 `bottom_breakout_burst`） |
| path2 web | `path2_web/` + `path2_web_ui/` | [modules/path2_web.md](modules/path2_web.md) | 调试可视化：多 pattern 缓冲扫描 + 前瞻收益 label + K 线 + 拓扑面板 + 漏检 3 web 入口诊断（FastAPI + Vue3） |

> 添加 / 更新模块文档：运行 `update-ai-context` skill。

## 参考：BreakoutStrategy 突破选股流水线

> 现状为参考实现（path2 的设计灵感来源），日常开发主要在 path2。代码地图见 `.claude/breakout_strategy_map.md`。

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
```

| 模块 | 代码目录 | 文档 |
|------|---------|------|
| 突破扫描 | `BreakoutStrategy/analysis/` | [modules/突破扫描模块.md](modules/突破扫描模块.md) |
| 数据挖掘 | `BreakoutStrategy/mining/` | [modules/数据挖掘模块.md](modules/数据挖掘模块.md) |
| 新闻情感 | `BreakoutStrategy/news_sentiment/` | [modules/新闻情感分析.md](modules/新闻情感分析.md) |
| 开发态 UI (dev) | `BreakoutStrategy/dev/` | [modules/dev.md](modules/dev.md) |
| 日常盯盘 (live) | `BreakoutStrategy/live/` | [modules/live.md](modules/live.md) |
| 共享 UI | `BreakoutStrategy/UI/` | [modules/UI.md](modules/UI.md) |
| 策略参数 SSoT | `BreakoutStrategy/param_loader.py` | — |
