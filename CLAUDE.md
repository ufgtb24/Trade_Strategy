# CLAUDE.md

## 上下文入口
开始任务前，按需阅读：
- 系统概览（项目定位 / 数据流 / 已实现模块 / 术语表）→ `.claude/docs/system_outline.md`
- 某个模块的架构意图 → `.claude/docs/modules/<模块名>.md`

注：`.claude/docs/` 下的文档只反映当前代码状态，不含历史、不含未实现模块。
需要更新这些文档时，运行 `update-ai-context` skill。
需要生成面向人类阅读的研究报告 / 代码解释 / 临时计划时，运行 `write-user-doc` skill。

## 代码地图
- `BreakoutStrategy/` — 核心策略包
  - `analysis/` — 突破检测、因子计算、质量评分
  - `mining/` — 因子阈值挖掘 + 模板组合生成
  - `news_sentiment/` — 新闻情感分析
  - `UI/` — 交互式界面（批量扫描、参数编辑、图表浏览）
- `configs/` — YAML 配置（`params/`, `scan_config.yaml`, `ui_config.yaml`, `news_sentiment.yaml`, `api_keys.yaml`）
- `datasets/pkls/` — 美股历史数据（Pickle）
- `scripts/` — 运行入口脚本

## 开发环境
- 包管理：`uv`（`uv add` / `uv run` / `uv sync`）

## 编码规范
- 原则：第一性原理 + 奥卡姆剃刀，反对过度设计
- 语言：界面英文，注释/文档中文
- Docstrings：`__init__.py` 含模块概述；类/函数说明用途、参数、算法逻辑
- 术语：breakout/bo（突破点）, peak/pk（峰值/凸点）
- 入口脚本：不使用 argparse，参数声明在 `main()` 起始位置

## Subagent vs Agent Team

这是两种完全不同的多代理模式，**不要混淆**：

- **多个独立 subagent**：用多次独立的 `Task` 工具调用派发。每个 subagent 在隔离上下文中执行，**彼此之间无法通信**。适合可以完全拆分、无需交叉讨论的并行任务（例如三个互不相关的研究子问题）。**默认使用 `tom` agent**。
- **Agent team**：用 `TeamCreate` 创建可互相通信的 teammate 群。成员在执行过程中能**互相发消息、共享中间结论、由 leader 协调**。适合需要反复讨论、交叉验证或分工协作的复杂分析。

当用户说"agent team"、"团队"、"teammates"时，**必须**用 `TeamCreate`。**绝不**把多个独立的 `Task` 调用当作 agent team。

两种模式都是高运行成本任务。完成后**默认将最终研究结果沉淀为 markdown 文档并保存至 `docs/research/`**（通过 `write-user-doc` skill 生成），避免昂贵的推理结果仅存在于对话上下文中丢失。
