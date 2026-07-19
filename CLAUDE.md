# CLAUDE.md

> **项目主线 = path2**（独立多级事件表达框架）。`BreakoutStrategy/` 是其前身突破选股流水线，仅供开发 path2 时参考，基本不用。

## 上下文入口
开始任务前，按需阅读：
- 系统概览（项目定位 / 数据流 / 已实现模块）→ `.claude/docs/system_outline.md`
- 某个已实现的模块的架构意图总结 → `.claude/docs/modules/<模块名>.md`
- 术语表（用语纪律 + path2 分层术语 + BreakoutStrategy）→ `.claude/docs/glossary.md`：**非必读**；当与用户沟通中出现某个项目上下文相关的术语、需确认其确切含义时，再查阅相应节（含「用语纪律」节）
,
注：
**`.claude/docs/` 只存放 system_outline.md、已实现模块架构意图 和 glossary.md（术语表），作为持久化上下文，任何其他内容都不应该放在这里。glossary.md 仅在用户明确指定时追加/修改，update-ai-context 不维护它。**
**`.claude/docs/` 下的文档只反映当前代码状态，不包含开发历史相关信息、不包含未实现的设计。**
**`.claude/docs/` 如果当前代码状态与 `.claude/docs/` 冲突时，以代码为准。永远不要根据 `.claude/docs/` 修改代码。**

需要更新这些文档时，运行 `update-ai-context` skill。
需要生成面向人类阅读的研究报告 / 代码解释 / 临时计划时，运行 `write-user-doc` skill。

## 代码地图

> **本 codebase 的主线功能是 path2**——独立的多级事件表达框架。`BreakoutStrategy/` 是其前身突破选股流水线，仅作开发 path2 时的参考、基本不用；其代码地图见 `.claude/breakout_strategy_map.md`（按需加载）。

### path2（主线）
- `path2/` — 独立事件表达框架（dag 引擎 + 走势-无关 atoms + calc + stdlib）
  - `core.py` / `runner.py` / `config.py` — 协议地基（Event(ABC,frozen) / Detector(Protocol) / class_id 注册表 / run()）
  - `dag/` — go-forward 唯一引擎（nodes/edges/where/spec/result/engine/diagnose；DAG 声明 + 约束求解 + 匹配物化 + per-role 诊断）
  - `atoms/` — 走势-无关 L1 Detector（BO/Trend/Platform/Distribution/Throwback）
  - `calc/` — 纯数值函数（无 Event/Detector） · `stdlib/` — span_id + BarwiseDetector 便利层
- `path2_apps/<走势>/` — 走势-特异应用层，与 path2/ 顶层平级（唯一应用 `bottom_breakout_burst/`，`dag_spec.py` 为核心）
- `path2_web/` — FastAPI 后端（发现 / 扫描 / 序列化 / 诊断，纯投影层） · `path2_web_ui/` — Vue3 前端（类型无关渲染器：K 线 + 拓扑面板 + 诊断侧栏）

> path2 各层架构意图见 `.claude/docs/modules/path2.md` · `path2_apps.md` · `path2_web.md`。

### 共享基础设施
- `configs/` — YAML 配置（`params/`、`scan_config.yaml`、`path2_web.yaml` 等）
- `datasets/pkls/` — 美股历史数据（Pickle）
- `scripts/` — 运行入口脚本（`path2_filter_<走势>.py` 全集扫描、`run_path2_web.py` 前后端启动；无 argparse）

## 开发环境
- 包管理：`uv`（`uv add` / `uv run` / `uv sync`）
- Playwright 卫生：本回合**用过** playwright MCP（截图/快照/console log）的情况下，任务完成时清空 `.playwright-mcp/` 目录（`rm -rf .playwright-mcp/*`，保留目录本身）；本回合**没用**则不动它。该目录是 playwright 临时产物缓存（page-*.yml / console-*.log 等），不入 git、不进 PR、积累后占空间
- Playwright 截图默认参数：调用 `browser_take_screenshot` 前先 `browser_resize(2560, 1440)`，截图统一 `scale="device"`。按场景分两种模式：
  - **整页截图**：`fullPage=True` —— 看整体布局、多组件对照
  - **元素级截图**：`fullPage=False`，并指定 `target=<selector>` —— 放大看单个组件细节、省 token

## 编码规范
- 原则：第一性原理 + 奥卡姆剃刀，反对过度设计
- 语言：界面中文（与项目现有 UI 一致），注释/文档中文
- Docstrings：`__init__.py` 含模块概述；类/函数说明用途、参数、算法逻辑
- 术语与用语纪律 → `.claude/docs/glossary.md`
- 入口脚本：不使用 argparse，参数声明在 `main()` 起始位置
- 读文件省上下文：先 grep/glob 定位，再 Read 用 `offset`/`limit` 只读相关段；勿整文件读取、勿重读已在上下文的文件

## Agent Team vs Subagent 

这是两种完全不同的多代理模式，**不要混淆**：
- **Agent team**：同一会话内用 `Agent` 工具 spawn 多名 teammate（每个起 `name`），他们之间通过 `SendMessage`（按 name 寻址）**互相发消息、共享中间结论、由 leader 协调**。适合需要反复讨论、交叉验证或分工协作的复杂分析。team 自动隐式形成，无需创建/命名/清理步骤；前置条件 `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`（已在用户与项目 settings.json 启用）。
- **多个独立 subagent**：用多次独立的 `Agent` 工具调用派发，**不让他们彼此 `SendMessage` 通信**。每个 subagent 在隔离上下文中执行、只把结果回报给主会话。适合可以完全拆分、无需交叉讨论的并行任务（例如三个互不相关的研究子问题）。**默认使用 `tom` agent**。

当用户说"agent team"、"团队"、"teammates"时，**必须**让 teammate 之间用 `SendMessage` 协作。**绝不**只调几次 `Agent` 而不开通 teammate 间通信——那只是多个独立 subagent，不是 agent team。

**Agent team 默认不进行任何代码实现**，只专注于思考、分析和讨论，最终产出为文档。除非用户明确要求写代码，否则绝不动代码。

两种模式都是高运行成本任务。完成后**默认将最终研究结果沉淀为 markdown 文档并保存至 `docs/research/`**，避免昂贵的推理结果仅存在于对话上下文中丢失。
**所有研究结果相关的文档都放在 `docs/research/`，不要碰 `.claude/`**。

**Agent team 文档归档约定**：每次启用 Agent team 都必须为本次任务在 `docs/research/<日期>_<任务内容>` 下新建专属文件夹、且最终结论报告必须命名 `final_report.md`（中间文档可选）；细则按需阅读 `.claude/rules/agent-team-doc-archival.md`。

**Agent team 完成后主动汇报**：spawn team 时，在 lead（即我自己）的运行协议里写死——当所有 teammate idle 且 `final_report.md` 已落地时，**立刻主动汇报报告要点给用户，不要等用户问**。判定 = 全员 idle + `final_report.md` 存在；汇报内容 = 关键结论摘要 + 文件绝对路径。


## 使用 superpowers

- **brainstorm 提问带倾向**：用 `AskUserQuestion` 提问时，尽量把你自己的倾向性方案作为选项之一，置于首位并在 label 末尾标 `(推荐)`，并在 description 说明推荐理由。
- **永远附 tom 选项**：每个 brainstorm 问题都额外提供一个选项「调用 tom 进行分析」——选中则把该问题派给 `tom` agent 从第一性原理裁定，返回后复述结论再继续。
- **自动模式**：当我说「自动模式」时，brainstorm 期间遇到的任何疑问**不要中断问我**。
  - 如果在多个选项之间，有你倾向性很强的推荐，直接采用推荐选项。
  - 如果在多个选项之间你也很不确定，那么派 `tom` 决定；tom 给方案后你自行 adopt / 让其 redo，仅在 circle 结束或硬阻塞（tom 也无法推进）时才回到我。tom 在 circle 中保存记忆。
  - 未说「自动模式」则按常规逐问确认。
- **subagent 模型选择**：按角色固定模型，不随任务复杂度浮动：
  - **Implementer**（实现）：一律 `sonnet`，禁用 `haiku`。
  - **Reviewer**（Spec / Code Quality / Final）：一律 `opus`。
- **计划自包含**：用 `superpowers:writing-plans` skill 产出的计划必须自包含——不依赖当前对话上下文即可被一个全新 session 直接实施。`superpowers:writing-plans` 结束后给出可供在新 session 中粘贴的执行命令即可，不要自行执行。注意，必须将需要粘贴的内容放在代码块中给出，让我能够将需要粘贴的内容和其他文本区分开。
- **计划路径规范**：plan 里涉及**项目内**的文件/目录一律用**相对 repo root** 的路径（如 `path2/dag/_solve.py`、`docs/research/xxx/final_report.md`），禁止硬编码 `/home/yu/PycharmProjects/Trade_Strategy-*/...` 这类绝对路径。原因：plan 可能在别的 worktree 里被实施，绝对路径会指向源 worktree 造成跨 worktree 污染。为消歧义，plan 顶部 spec 里显式写一句「本 plan 中所有项目内路径均相对 repo root」。**例外**（保持绝对）：与 worktree 无关的系统路径，如 `~/.claude/...`、`/tmp/claude-*/scratchpad`、外部工具、系统级配置——这些绝对路径反而更清晰。
- **executing-plans** 默认在新 session 中使用 subagent-driven 执行 `superpowers:executing-plans`。
- **Plan 尽量不拆分**：默认将 spec 内容写为一份完整 plan、单 session 跑完；只有「前段实施结果大分叉迫使后段重写」才拆段，具体判据 `.claude/rules/plan-execution.md`

