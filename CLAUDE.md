# CLAUDE.md

> **项目主线 = path2**（独立多级事件表达框架）。`BreakoutStrategy/` 是其前身突破选股流水线，仅供开发 path2 时参考，基本不用。

## 工作原则

**第一性原理**——不限于编码：分析、设计、方案取舍、评审、写文档同样先回到问题本身推导，别靠惯例和类比堆结构。

**奥卡姆剃刀 / 反对过度设计**——砍的是**结论与产出物**的复杂度，不是思考过程的宽度：
- 分析阶段先宽后窄：假设、对照、反例先枚举全，收敛时才动剃刀。「最简单的解释」必须是搜完之后剩下的那个，不是没搜就先挑的那个。
- 仅在解释力 / 需求覆盖相同时才用它择优；覆盖不同就不归剃刀管，老实说清取舍代价。

## 简称约定
聊天中常用以下简称，遇到时按全称理解：
- bb → `path2_apps/bottom_burst/`（path2 当前唯一的应用层走势 app）
- cc -> claude code
- bs -> BreakoutStrategy

## 上下文入口
开始任务前，按需阅读：
- 系统概览（项目定位 / 数据流 / 已实现模块）→ `.claude/docs/system_outline.md`
- 某个已实现的模块的架构意图总结 → `.claude/docs/modules/<模块名>.md`
- 术语表（用语纪律 + path2 分层术语 + BreakoutStrategy）→ `.claude/docs/glossary.md`：**非必读**；当与用户沟通中出现某个项目上下文相关的术语、需确认其确切含义时，再查阅相应节（含「用语纪律」节）

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
- `path2_apps/<走势>/` — 走势-特异应用层，与 path2/ 顶层平级（唯一应用 `bottom_burst/`，`dag_spec.py` 为核心）
- `path2_web/` — FastAPI 后端（发现 / 扫描 / 序列化 / 诊断，纯投影层） · `path2_web_ui/` — Vue3 前端（类型无关渲染器：K 线 + 拓扑面板 + 诊断侧栏）

> path2 各层架构意图见 `.claude/docs/modules/path2.md` · `path2_apps.md` · `path2_web.md`。

### 共享基础设施
- `configs/` — YAML 配置（`params/`、`scan_config.yaml`、`path2_web.yaml` 等）
- `/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls/` — 美股历史数据（Pickle）。**该路径是主目录的绝对地址，所有 worktree 一律访问主目录这一份**，不要在 worktree 内找/建 `datasets/pkls/`（worktree 内该目录为空）
- `scripts/path2/` — path2 核心入口脚本（`run_path2_web.py` 前后端启动、`path2_eval_scan.py` 评估、`scan-top-miss.py` 漏检扫描；无 argparse。诊断环境探测脚本 `path2_diag_env.py` 随 diagnose-event skill 走、不在本目录）

## 开发环境
- 包管理：`uv`（`uv add` / `uv run` / `uv sync`）
- Playwright 卫生：本回合**用过** playwright MCP（截图/快照/console log）的情况下，任务完成时清空 `.playwright-mcp/` 目录（`rm -rf .playwright-mcp/*`，保留目录本身）；本回合**没用**则不动它。该目录是 playwright 临时产物缓存（page-*.yml / console-*.log 等），不入 git、不进 PR、积累后占空间
- Playwright 截图默认参数：调用 `browser_take_screenshot` 前先 `browser_resize(2560, 1440)`，截图统一 `scale="device"`。按场景分两种模式：
  - **整页截图**：`fullPage=True` —— 看整体布局、多组件对照
  - **元素级截图**：`fullPage=False`，并指定 `target=<selector>` —— 放大看单个组件细节、省 token

## 编码规范
- 语言：界面中文（与项目现有 UI 一致），注释/文档中文
- Docstrings：`__init__.py` 含模块概述；类/函数说明用途、参数、算法逻辑
- 术语与用语纪律 → `.claude/docs/glossary.md`
- 入口脚本：不使用 argparse，参数声明在 `main()` 起始位置。**仅适用于人类手动运行的脚本**（如 `scripts/` 下的入口）——目的是免去每次手敲参数；skill 内由 cc 自己调起运行的脚本不受此限，该用 argparse 传参就用
- 读文件省上下文：先 grep/glob 定位，再 Read 用 `offset`/`limit` 只读相关段；勿整文件读取、勿重读已在上下文的文件
- 评估纪律：策略评估核心指标 = median(forward_return) + FP 首次穿越率（win_rate 废弃：基率复读无增量）；任何「好/坏」判断必须带基线对照（随机日基线 / 池子基线率），孤立数字不下结论。完整五条（口径自检 / 用途匹配 / 小样本计数）见 `.claude/skills/eval-discipline/SKILL.md`（评估/删除模拟/阈值拍板时主动调该 skill）

## Agent Team

当用户说「agent team」「团队」「teammates」时，spawn 任何 teammate 之前**必须**先调 `agent-team` skill——teammate 通信要求、原问题持久化、文档归档、完成汇报的约定全在里面。

## 研究副产品登记

研究中顺手发现的、不属于本轮主假设但也过了及格线的东西（变量 / 方向反了的闸 / 错的基线）必须登记到 `docs/feature_candidates.md`。完整规则在 `.claude/rules/feature-candidates-capture.md`，触碰 `docs/research/**` 时自动加载。

## 后台 agent

> 后台 agent = Claude Code 的 background session：由 supervisor 托管、不绑终端的独立完整会话，经 agent view（`claude agents`）、`/bg`、`claude --bg` 或 `←` 创建。与 agent team、subagent 是不同机制。

**后台 agent 交付约定**：**前提——仅当后台 agent 为本任务创建了独立 worktree 时才按此交付**；未创建 worktree（如纯研究/只读任务、或直接在当前 worktree 内工作）则不走此流程。适用时，完成任务后统一如此交付——① 在该 worktree 分支 `commit`；② `push` 该分支到 `origin`；③ 停下并只报告分支名，任务到此为止。**禁止开 PR**：不得用任何方式（`gh` / GitHub API / `curl` 等）创建 PR，合并一律由我手动完成。派后台 agent 时把本约定原样写进其 prompt（后台 agent 在隔离上下文运行、未必读得到本文件）。


## 创作 skill

### description 的触发词

**触发词只取我在提需求时会自然说出口的词**——产品名、功能名、领域概念（如 Clash、isp、链式代理；稳健区域、同时调好几个参数）。**绝不**把系统内部术语、内部文件名、实现细节当匹配词（反例：`iggfeed`、`multivar_scan`、F 维——我对这些"没什么印象"，需求里根本不会出现）。

**Why**：我表述需求时只会用自己脑子里有的概念。指望我在需求里报出内部细节是反人性的，这种触发词等于没有——`description` 是唯一决定"我说什么会触发它"的地方，正文写得再全，触发不了就等于没做。

**How to apply**：
- 改 `description` 前先问「我会怎么开口说这件事」，取那批词；实现细节一律留 `SKILL.md` 正文（`description` 只负责让你判断要不要点开）。
- 压缩 `description` 时不要为"保住某个内部词的命中率"而加字——那不是真触发路径。
- **skill 功能扩展后必须回头改 `description`**：它不进 diff、不进复审视野，是最容易漏掉的地方（实例：tune-gates 加了多维稳健区整套能力，描述却还停在旧词汇，新那条路谁也触发不了）。

### 运行时只对用户暴露业务层

**skill 的职责是代理我完成复杂任务、减少我的心智负担**，因此 skill 运行期间**内部机制细节尽量不要让我知道**——阶段编号、内部数据结构与字段名、脚本名、中间产物格式，都是 skill 自己该消化的东西，不往外抛。只和我探讨业务层面的内容。

**遇到需要我拍板的中间结果，先翻译成人话再问**：说清这个选择**在业务上意味着什么**、各选项的业务代价是什么，而不是报出内部状态让我自己解码。

**Why**：我的心智预算应该花在业务判断上。把内部状态原样抛给我，等于把 skill 没做完的翻译工作外包回给我，skill 的价值就打了折。

## 修改 CLAUDE.md 时的动态化建议

用户要求往 CLAUDE.md 增改内容时，先按三问给出常驻/按需的建议再动手：**读者是谁**（后台 session 只读 CLAUDE.md、没人替它调 skill）、**场景开始的信号是什么**（文件路径→rules `paths:`／用户口径词→skill／事件→hook／都没有→常驻）、**到位时机来不来得及**（rules 只在 Read 时注入）。只有**长且少用**的内容值得迁；省 token≈0（有 cache），真收益是到位时机与按 agent 数倍乘。判据与实测边界见 `docs/cc_notes/claude-md-dynamic-loading.md`。

## 使用 superpowers

- **brainstorm 提问带倾向**：用 `AskUserQuestion` 提问时，尽量把你自己的倾向性方案作为选项之一，置于首位并在 label 末尾标 `(推荐)`，并在 description 说明推荐理由。
- **永远附子代理选项**：每个 brainstorm 问题都额外提供一个选项「派子代理分析」——选中则把该问题派出去从第一性原理裁定，返回后复述结论再继续。两种子代理按问题性质选：
  - **带上下文**（默认）：`Agent` 工具 `subagent_type: "fork"`，继承当前完整对话上下文，无需打包背景，适合深度依赖前面讨论的问题（等价于我手敲 `/subtask`；`/subtask` 是内置 CLI 命令，你自己调不了，只能走 `fork`）。
  - **独立视角**：`subagent_type: "general-purpose"`，不继承上下文，由你把问题中立地打包进 prompt，适合需要不受你已有倾向影响的第三方裁定。
  - 无论哪种，都在 prompt 里写死子代理是**纯分析角色**：从第一性原理出发，只出结论/论证/方案，不碰代码；`AskUserQuestion` 在子代理内不可用，不要让它问我。
- **自动模式**：当我说「自动模式」时，brainstorm 期间遇到的任何疑问**不要中断问我**。
  - 如果在多个选项之间，有你倾向性很强的推荐，直接采用推荐选项。
  - 如果在多个选项之间你也很不确定，那么派子代理决定（默认用带上下文的 `fork`）；子代理给方案后你自行 adopt / 让其 redo，仅在 circle 结束或硬阻塞（子代理也无法推进）时才回到我。
  - 未说「自动模式」则按常规逐问确认。
- **subagent 模型选择**：按角色固定模型，不随任务复杂度浮动：
  - **Implementer**（实现）：一律 `sonnet`，禁用 `haiku`。
  - **Reviewer**（Spec / Code Quality / Final）：一律 `opus`。
- **计划自包含**：用 `superpowers:writing-plans` skill 产出的计划必须自包含——不依赖当前对话上下文即可被一个全新 session 直接实施。`superpowers:writing-plans` 结束后给出可供在新 session 中粘贴的执行命令即可，不要自行执行。注意，必须将需要粘贴的内容放在代码块中给出，让我能够将需要粘贴的内容和其他文本区分开。
- **计划路径规范**：plan 里涉及**项目内**的文件/目录一律用**相对 repo root** 的路径（如 `path2/dag/_solve.py`、`docs/research/xxx/final_report.md`），禁止硬编码 `/home/yu/PycharmProjects/Trade_Strategy-*/...` 这类绝对路径。原因：plan 可能在别的 worktree 里被实施，绝对路径会指向源 worktree 造成跨 worktree 污染。为消歧义，plan 顶部 spec 里显式写一句「本 plan 中所有项目内路径均相对 repo root」。**例外**（保持绝对）：与 worktree 无关的系统路径，如 `~/.claude/...`、`/tmp/claude-*/scratchpad`、外部工具、系统级配置——这些绝对路径反而更清晰。
- **executing-plans** 默认在新 session 中使用 subagent-driven 执行 `superpowers:executing-plans`。
- **Plan 尽量不拆分**：默认将 spec 内容写为一份完整 plan、单 session 跑完；只有「前段实施结果大分叉迫使后段重写」才拆段，具体判据 `.claude/rules/plan-execution.md`

