# CLAUDE.md

> **项目主线 = path2**（独立多级事件表达框架）。`BreakoutStrategy/` 是其前身突破选股流水线，仅供开发 path2 时参考，基本不用。

## 工作原则

**第一性原理**——不限于编码：分析、设计、方案取舍、评审、写文档同样先回到问题本身推导，别靠惯例和类比堆结构。

**奥卡姆剃刀 / 反对过度设计**——砍的是**结论与产出物**的复杂度，不是思考过程的宽度：
- 分析阶段先宽后窄：假设、对照、反例先枚举全，收敛时才动剃刀。「最简单的解释」必须是搜完之后剩下的那个，不是没搜就先挑的那个。
- 仅在解释力 / 需求覆盖相同时才用它择优；覆盖不同就不归剃刀管，老实说清取舍代价。

## 简称约定
聊天中常用以下简称，遇到时按全称理解：
- bb → `path2_apps/bottom_burst/`（path2 应用层的主线走势 app）
- cc -> claude code
- bs -> BreakoutStrategy

## 用户指令映射

- **当我说「白话解释 / 通俗解释」**：默认不打比方。我通常懂领域、只是不想看公式，要用语言化方式把机制本身讲清楚；仅当我说「完全不懂 / 我是小白」时才用比喻。
  - **「白话」≠「少用专有名词」。** `CONTEXT.md` 里定义过的词**不在回避之列，反而要优先用**——「引用槽」「复合事件」「事件流」「物化」这些词条本身就是白话，比自造的替代说法更准。把它们换成自造词（「对象引用」「容器」「贴身份」）是在**制造**术语而不是消除术语，实测会直接让解释读不懂。
  - 该回避的是**没有定义过的**行话，以及函数名 / 行号 / 内部字段名这类实现细节。回避它们的办法是换成 `CONTEXT.md` 的词，**不是换成自己临时造的词**。
  - **动笔讲机制前先 grep 一遍词表**（`path2/CONTEXT.md` 共 45 个词头），别靠记忆——这条纪律没有任何自动触发机制（`.claude/rules/` 无 `paths:` 覆盖 `path2/**`，且 rules 只认 Read 工具、Bash 里 grep/sed 不触发），全靠主动查。

## 上下文入口

全仓只有两份 AI 上下文文档，各管一件事：

- **某个词在本项目里到底指什么** → 根目录 `CONTEXT-MAP.md`，它指向 `path2/CONTEXT.md`（框架与走势词汇）和 `path2_web/CONTEXT.md`（界面词汇）。**查词用 `grep -n '词' path2/CONTEXT.md` 定位后只读那一段，别整读。** 由 `/grill-with-docs` 维护。
- **代码在哪、各层为什么这么分** → 本文件下面的「代码地图」节，它是唯一的系统概览。由 `update-ai-context` skill 维护。

（`.claude/docs/` 已整体删除：术语归 `CONTEXT.md`，模块架构意图并入本文件代码地图，机制细节归代码 docstring。）

需要生成面向人类阅读的研究报告 / 代码解释 / 临时计划时，运行 `write-user-doc` skill。

注：**文档只反映当前代码状态，不写开发历史、不写未实现的设计。当代码与文档冲突时一律以代码为准，永远不要根据文档修改代码。**

## 代码地图

> **主线是 path2**——独立的多级事件表达框架：把「股票走势」建模为多级不可变事件 + DAG 约束求解。
> 主链路：`参数 + K 线 → build_pattern → analyze（跑 detector 产流 → 求解约束图 → 物化 match）→ AnalysisResult → web 投影与渲染`
> `BreakoutStrategy/` 是它的前身突破选股流水线，日常不动；代码地图见 `.claude/breakout_strategy_map.md`（按需加载）。

### path2/ — 走势-无关的框架

一条分层红线贯穿全包：**框架不认识任何具体走势**，走势语义只出现在 `path2_apps/` 的声明里。

- `core.py` / `runner.py` / `config.py` — 协议地基：`Event`（ABC + frozen dataclass，容器字段一律 tuple）、`Detector`（Protocol）、`run()`。
  - 不变式：事件身份是 `node_id` + `instance_id` 双轴，由引擎物化时统一注入，detector 阶段恒为 None；任何地方都不得自行拼 `instance_id`。
- `dag/` — 唯一引擎：`nodes`（NodeSpec）/ `edges`（六类边）/ `where`（一元谓词与组合子）/ `spec`（声明容器 + 构造期校验）/ `_solve`（求解）/ `_reify`（物化）/ `result` / `diagnose`。
  - 分工红线：一元条件走 node 的 where，二元关系走边的 satisfies，两者正交、不得混写；跨节点约束绝不写进 where。
  - 不变式（INV-C）：求解期剪枝只能基于边 `feasible_window` 依赖的单调结构字段；`satisfies` 里读的非单调 / 身份属性一旦进剪枝就会漏匹配。**改 C1 / `c1_off` / INV-C 相关代码前必须先跑 fuzz**（历史上两次真漏匹配都是 fuzz 才抓到的）。
- `atoms/` — 走势-无关的 L1 detector：突破（一趟同时产 bo 与 pk 两条流）、走势区段、平台、派发、回踩（多代实现共存）。
  - 不变式：K 线回看只能发生在 detector 内部——算好的字段挂到 event 上供 where 直读，where 拿不到 df。
- `calc/` — 纯数值函数（ATR / 均线 / 量比 / 几何 / 稳定性等），不碰 Event 与 Detector。
- `stdlib/` — 便利层：`BarwiseDetector`（逐 bar 扫描模板）+ `make_app`（app 入口三件套装配）。
- `eval.py` — 度量：前瞻收益 / 前瞻回撤（幅度）+ 首次穿越（方向）+ 随机日基线。
  - 不变式：幅度与方向两个指标正交互补，任何「好 / 坏」判断必须带基线对照。

### path2_apps/<走势>/ — 走势-特异的声明层

一个子包 = 一个 pattern 的完整声明（`dag_spec.py` 拓扑与 where + `params.py` / `params.yaml` 参数），与 `path2/` 顶层平级。不实现 detector、不做求解。现役 app：`bottom_burst`（主线）、`bb_v1`（另一代回踩实现）、`bo_only`（参照系）；其余子包是历史版本或实验残留。

- 不变式（铁律）：每个 app 必须导出 `eval_meta()`，声明买点 node 与首部缓冲交易日数；缺了它，web 的 pattern 发现会直接跳过这个 app。

### path2_web/ + path2_web_ui/ — 调试可视化

FastAPI 后端（pattern 发现 / 扫描 / 序列化 / 诊断）+ Vue3 前端（K 线主图 + 事件副图 + 拓扑面板 + 诊断侧栏）。

- 边界红线：后端是**纯投影层**，只把 path2 的只读数据结构转成 JSON，不含走势语义、不做二次判定；前端是**类型无关渲染器**，按 node 分轨、按 where 分列，不为任何具体事件类型写分支。

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
- 术语：输出里提到领域概念时，用 `CONTEXT.md` 里定下的那个词，别漂到它 `_Avoid_` 掉的同义词（尤其 where 别叫「定语」、FP 别读成 false positive、身份别用已退役的 `event_id` / `class_id` / `source_tag`）
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

## Agent skills

### Issue tracker

本仓库的 issue 与 spec 以本地 markdown 跟踪，放在 `.scratch/<feature-slug>/`（进 git）。See `docs/agents/issue-tracker.md`.

### Triage labels

使用默认五个标签（`needs-triage` / `needs-info` / `ready-for-agent` / `ready-for-human` / `wontfix`），标签字符串与角色名相同。See `docs/agents/triage-labels.md`.

### Domain docs

multi-context：根目录 `CONTEXT-MAP.md` → `path2/CONTEXT.md` + `path2_web/CONTEXT.md`；`docs/adr/` 由 `/grill-with-docs` 懒创建，尚不存在时静默跳过。See `docs/agents/domain.md`.
