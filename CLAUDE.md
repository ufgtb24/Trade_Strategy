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
  - **写词条时**（`/grill-with-docs` 一谈定术语就当场写入，不攒着）：词头**多写**——同一概念的各种正当说法（标识符、中文名、口头简称）全列上、`/` 分隔，**第一个是规范词，输出一律只用第一个**；其余只为抬高查词命中率而存在，**不规范用户怎么说**。
  - **`_Avoid_` 只放不正当的说法**：自造词（where 别叫「定语」）、已退役的名字（`event_id` / `class_id`）、会误读的（FP 别读成 false positive）。它们 grep 一样命中同一词条，所以命中率不受损；正当的同义说法一律进词头，不进 `_Avoid_`。**两个集合不相交**——同一个词不能既在词头又被 `_Avoid_`，这是词条的自检式。写法统一为「被避免的词打头，理由跟后面」。
  - **并列概念用顿号**：`点事件、span 事件`、`确认型、回顾型`、`detected、qualified、matched` 是一个词条里讲一组不同的东西，「取第一个」不适用。
- **跑 `/grill-with-docs` 时**：开场**整读**两份 `CONTEXT.md`（唯一整读的场景，日常查词仍只读一段）；之后每轮回讲需求都用词表的词，并把用户的说法与规范词的对应显式点出来（「你说的『身份字段』，词表里叫 `instance_id`」）。异词同义 `domain-modeling` 没有任何条款管，只能靠回讲时暴露给用户纠。
- **普通会话里（没跑 `/grill-with-docs`）碰到这三个信号，提示一句「要不要进词表」，别直接改文件**：① 用户给某个东西起名或改名（「以后叫它 X」「不叫 A，叫 B」）；② 用户纠正我的用词——那就是术语敲定的现场；③ 我要用一个词表里没有的词去指代本项目特有的东西（这是输出侧自查的另一半：检查不通过时，除了「我该改用规范词」，另一种可能就是词表缺了这个概念）。别拿「这算不算术语」当触发条件——那要先判断、判错就静默失效。通用编程概念不收，哪怕项目里用得多。
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
- `atoms/` — 走势-无关的 L1 detector：bo 检测（一趟同时产 bo 与 pk 两条流）、走势区段、平台、派发、回踩（多代实现共存）。
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
- 术语：输出里提到领域概念时，用 `CONTEXT.md` 里定下的那个词，别漂到它 `_Avoid_` 掉的同义词（尤其 where 别叫「定语」、首次穿越别写成 FP（会被读成 false positive）、身份别用已退役的 `event_id` / `class_id` / `source_tag`）
- 入口脚本：不使用 argparse，参数声明在 `main()` 起始位置。**仅适用于人类手动运行的脚本**（如 `scripts/` 下的入口）——目的是免去每次手敲参数；skill 内由 cc 自己调起运行的脚本不受此限，该用 argparse 传参就用
- 读文件省上下文：先 grep/glob 定位，再 Read 用 `offset`/`limit` 只读相关段；勿整文件读取、勿重读已在上下文的文件
- 评估纪律：策略评估核心指标 = median(forward_return) + 首次穿越率（win_rate 废弃：基率复读无增量）；任何「好/坏」判断必须带基线对照（随机日基线 / 池子基线率），孤立数字不下结论。完整五条（口径自检 / 用途匹配 / 小样本计数）见 `.claude/skills/eval-discipline/SKILL.md`（评估/删除模拟/阈值拍板时主动调该 skill）

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
- **task 尽量少、颗粒度尽量大**：每个 task 边界 = 两次 subagent 往返（implementer + reviewer，后者不可跳过），实测最小 5 分钟、与 task 难度无关——task 数是实施总时长的主因。**默认合并，只在有具名理由时才切**，理由只有四种：① **reviewer 可能对相邻两半给出不同结论**（与 `writing-plans` 的 Task Right-Sizing 同源：能一半驳回、一半放行的地方才是边界）；② **两半风险档不同**——合了就得整体升 `opus`（见下条 Reviewer 选档）；③ **后半要等前半的实测结果才写得出来**；④ **单个 task 大到会爆 subagent 的 context**。setup / 脚手架 / 配置 / 文档跟进一律折进它服务的那个 task，不单独成 task。**别拿「implementer 做不做得动」当切分理由**——模型能力涨的是实现侧，边界的价值在验证侧。注意 `writing-plans` 里的「Bite-Sized」说的是 **step**（每步一个动作、2-5 分钟），不是 task，别拿它当切 task 的依据。**合并的前提是具名风险跟着搬**——在 dispatch 里逐文件写「这里要定点核实什么」，review 质量来自这份清单，不来自 task 切得细。（实测：某轮 6 个 task 全部首轮 review clean、fix 轮 = 0，其中四个 diff 不到 20 行改动，该切 3 个。）
- **测试只跑必要的那一次**：plan 里每个 task 的 Run **只写覆盖本 task 改动的测试**，不写全量；全量只允许出现在两处——起点基线、末尾验收关卡。按成本分三档：**秒级定向测试**每个 task 随便跑；**分钟级套件**只在起点基线与末尾关卡各一次；**依赖外部数据的集成测试**只在末尾，且**验收关卡必须断言它的规模数字**（`n_stock=104 n_cmp=2496` 这类），不能只看 `passed`——缺数据时它静默 skip，`-q` 输出里跟通过几乎一样，验证悄悄没做而结果仍是绿的。派 implementer 时把这条写进 dispatch（「只跑覆盖你改动的测试，全量与验收关卡由控制端在末尾统一跑」），否则它们会出于好意自发跑全套「交叉验证」。**验收关卡的记录必须跑在代码最后一次改动之后**（终审 fix wave 也算改动）——提前跑只能当中途信息，不能当交付证据。**起点基线必须把每条验收关卡的命令都实测一遍并记数**：漏测哪条，那条的 Expected 就会写错（实测：某轮 plan 只测了 skill 子套件、没测 `tests/` 全量，于是关卡写成「0 failed」，而起点本就有 7 个既存失败，执行时只能另开 worktree 补跑基线才敢判「0 新增」）。
- **plan 末尾不归任何 task 的节，标题必须写成 `## Task <N+1>: xxx（控制端执行，不派 implementer）`**：`task-brief` 的切分**只认** `^#+\s+Task\s+<数字>` 这一种标题（读脚本坐实），别的标题一律拦不住——最后一个 task 的 brief 会一路吞到文件末尾，把验收关卡、留账、附录全当成它自己的需求。实测后果：某轮 Task 6 自身 76 行、brief 却有 141 行，implementer 照单把 7 道验收关卡整套跑了一遍。
- **每个 task 点名证据形式，别默认 TDD**：plan 为每个 task 写清「这一轮凭什么算做对了」，形式随 task 形状变——**新增或改变行为** → TDD，且 **RED 必须红在断言上**（`ImportError` / `TypeError: unexpected keyword` 那种红只证明代码还不存在，不证明断言有牙齿：一个 `assert True` 的测试同样能这样红、这样绿）；**删代码 / 删闸** → 前后红点差分（如「8 errors + 3 failed 归零」），没有新行为可钉；**更新陈旧期望、重冻 fixture** → **人工来源核对**，红是自动的、绿是必然的，两者都不是证据（实测：自产自销的 fixture 重冻必然变绿，真证据是新增字段逐字等于参数声明的默认值）；**纯文档 / 注释** → 跑一遍覆盖测试确认没写坏即可。**这不是省时间的条款**——RED 一步实测是秒级（0.46s），它防的是「造出一份不会失败的测试」和「拿必然的绿当证据」。
- **subagent 模型选择**：
  - **Implementer**（实现）：一律 `sonnet`，禁用 `haiku`。固定，不随任务复杂度浮动。
  - **per-task Reviewer**：按三条**可观察**的性质选档，**不固定**、**与 diff 大小无关**——① **错了是静默的**（结果少了、空了，但不抛异常，测试也未必红）；② **正确性依赖改动之外的性质**（要同时按住几条互相牵制的不变式才判得了对错，不论它们在同一函数里还是跨文件）；③ **副作用越出改动边界**（原地改写调用者传进来的对象、写全局状态）。命中任一条用 `opus`；都不命中用 `sonnet`（机械 diff、纯接线、常量替换、摊平的逐条核对），fix 轮的定向复审也用 `sonnet`——**`sonnet` 是下限，任何角色都不降到它以下**。**逐条对着改动本身判，别用「这块在哪个模块 / 算不算核心 / 算不算复杂」代替**——按模块名单判会漏且漏了不自知；判据里含需要先分类的词，分类错了这条规则就等于不存在。**大而浅的 diff 不该升档**：失败模式是注意力被摊薄、不是推理深度不够，该补具名风险清单或拆开，升档买不到东西——「值得仔细 review」不等于「该上 opus」。
  - **档位在 plan 里给建议、执行时可覆盖**：上面三条全是 task 的固有属性、写 plan 时就定得下来，所以 plan 为每个 task 标一个建议档（写在该 task 的 Files/Interfaces 附近）。**控制端拿到实际 diff 后有最终决定权**——implementer 可能做出计划外的东西（改动被带进剪枝路径、副作用比设计时更宽、顺手动了相邻不变式），这时按实际 diff 重判并在台账记一句理由。plan 的建议档是省一次判断，不是绑住执行。
  - **Final holistic reviewer**（whole-branch 那一次）：一律 `opus`，不降档。
- **计划自包含**：用 `superpowers:writing-plans` skill 产出的计划必须自包含——不依赖当前对话上下文即可被一个全新 session 直接实施。`superpowers:writing-plans` 结束后给出可供在新 session 中粘贴的执行命令即可，不要自行执行。注意，必须将需要粘贴的内容放在代码块中给出，让我能够将需要粘贴的内容和其他文本区分开。
- **计划路径规范**：plan 里涉及**项目内**的文件/目录一律用**相对 repo root** 的路径（如 `path2/dag/_solve.py`、`docs/research/xxx/final_report.md`），禁止硬编码 `/home/yu/PycharmProjects/Trade_Strategy-*/...` 这类绝对路径。原因：plan 可能在别的 worktree 里被实施，绝对路径会指向源 worktree 造成跨 worktree 污染。为消歧义，plan 顶部 spec 里显式写一句「本 plan 中所有项目内路径均相对 repo root」。**例外**（保持绝对）：与 worktree 无关的系统路径，如 `~/.claude/...`、`/tmp/claude-*/scratchpad`、外部工具、系统级配置——这些绝对路径反而更清晰。
- **执行方式**：plan 写完后**不在当前 session 执行**——换新 session，用 `superpowers:subagent-driven-development`（每 task 一个 fresh subagent + 两阶段 review）。注意 `subagent-driven-development` 与 `superpowers:executing-plans` 是互斥的两个执行 skill，二选一，不存在「用前者执行后者」。

## Agent skills

### Domain docs

multi-context：根目录 `CONTEXT-MAP.md` → `path2/CONTEXT.md` + `path2_web/CONTEXT.md`；`docs/adr/` 由 `/grill-with-docs` 懒创建，尚不存在时静默跳过。See `docs/agents/domain.md`.
