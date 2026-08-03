# System Outline

> 最后更新：2026-08-03

> 本 codebase 的**主线是 path2** —— 独立的多级事件表达框架：把"股票形态"建模为多级不可变事件 + DAG 约束求解。
> `BreakoutStrategy/` 是 path2 的前身突破选股流水线，现仅作参考，日常基本不动。
> 本文档只反映当前代码状态，不含历史演进、不含未实现模块。需要更新时运行 `update-ai-context` skill。

## 主线：path2 事件表达框架

形态用"声明节点 + 类型化边"两步表达，交库引擎求解匹配；与 BreakoutStrategy 的因子 / 选股流水线**零耦合**。

主链路：

```
参数 + K 线 → build_pattern → analyze（跑 detector → 求解约束图 → 物化匹配）→ AnalysisResult → web 投影与渲染
```

| 模块 | 代码目录 | 文档 | 边界 |
|------|---------|------|------|
| path2 框架 | `path2/` | [modules/path2.md](modules/path2.md) | 走势-**无关**的引擎与原子库：事件/检测器协议、DAG 声明与求解、L1 detector、纯数值计算、前瞻收益 / 首次穿越度量与诊断底座。不含任何具体走势 |
| path2 应用层 | `path2_apps/<走势>/` | [modules/path2_apps.md](modules/path2_apps.md) | 走势-**特异**的声明层：一个子包 = 一个形态（拓扑 + where + 参数取值）。不实现 detector、不做求解 |
| path2 web | `path2_web/` + `path2_web_ui/` | [modules/path2_web.md](modules/path2_web.md) | 调试可视化工具（FastAPI + Vue3）：把分析结果投影成 JSON、再渲染成可交互界面。不含任何走势语义 |

> 添加 / 更新模块文档：运行 `update-ai-context` skill。

## 参考：BreakoutStrategy 突破选股流水线

> path2 的设计灵感来源；日常开发主要在 path2。代码地图见 `.claude/breakout_strategy_map.md`。

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
模板组合过滤                    可选：情感验证
   │                          (调用 news_sentiment)
   ├──────────────┐
   ▼              ▼
[dev] 策略开发台   [live] 日常盯盘台
```

| 模块 | 代码目录 | 文档 | 边界 |
|------|---------|------|------|
| 突破扫描 | `BreakoutStrategy/analysis/` | [modules/突破扫描模块.md](modules/突破扫描模块.md) | OHLCV → 带因子与评分的突破事件，含全市场批量扫描与落盘 |
| 数据挖掘 | `BreakoutStrategy/mining/` | [modules/数据挖掘模块.md](modules/数据挖掘模块.md) | 从扫描结果搜索因子阈值组合，产出可直接投产的参数文件 |
| 新闻情感 | `BreakoutStrategy/news_sentiment/` | [modules/新闻情感分析.md](modules/新闻情感分析.md) | 给定股票与时间段产出带 confidence 的情绪结论，只作辅助维度、不独立决策 |
| 开发态 UI (dev) | `BreakoutStrategy/dev/` | [modules/dev.md](modules/dev.md) | 策略开发台：发起扫描、复核 K 线、就地调参看图 |
| 日常盯盘 (live) | `BreakoutStrategy/live/` | [modules/live.md](modules/live.md) | 只读盯盘台：每日跑一次全市场，把候选投到筛选面板 |
| 共享 UI | `BreakoutStrategy/UI/` | [modules/UI.md](modules/UI.md) | dev 与 live 共享的绘图基础设施；不得反向依赖应用层 |
| 因子注册表 | `BreakoutStrategy/factor_registry.py` | — | 因子清单与元数据的唯一权威，analysis / mining 均从此消费 |
| 策略参数 SSoT | `BreakoutStrategy/param_loader.py` | — | 突破流水线的参数加载单一入口 |

## 共享基础设施

- `configs/` — YAML 配置（web 服务、扫描、突破流水线因子参数等）。注意 path2 各 app 的 `params.yaml` **不在**这里，随各自子包走。
- `scripts/` — 运行入口脚本：不使用 argparse，参数声明在 `main()` 起始处。
- `tests/` — 按包镜像的测试树（`tests/path2/`、`tests/path2_web/` 等）；`BreakoutStrategy/` 另有自带测试目录。
