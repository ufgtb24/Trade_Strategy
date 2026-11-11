# 任务简报：反馈去掉二分类 + 会话每轮流程写成 skill

本文件中项目内路径均相对 repo root。用户原话见同目录 `原始问题.md`。

## 背景（现状）

标注工具的「反馈」：用户在 `compare` 里圈定 app 的买点（点一个 ▼、点一族、或拖一段日期），在面板里作答，记录存进用户的标注文件，会话经 `path2_web/annotation/store.py` 的 `read_annotations` 读。

- 权威设计：`.scratch/annotation-path2/spec.md` 1.11、6.13、6.14；说明书 `.scratch/annotation-path2/manual.md`「反馈」一节；词表 `path2_web/GLOSSARY.md` 的 `off_pattern`、`feedback`、`issue` 词条；进度表 `.scratch/annotation-path2-implementation/feedback-plan.md` 末尾。
- 现在的作答：先选答案 `neg` / `off_pattern`；`off_pattern` 下点 node 按钮（认错的 node）或 `dag`（毛病不在某个 node 上，必须写 note）；`neg` 必须写 note、没有 node 按钮。
- 现在的 issue：一份作答（pattern、answer、note、nodes、dag）叫一个 issue，几处反馈可共享；作答内联在每条反馈里，共享的几处带同一个可选键 `issue`，保存时校验各处作答相同（原因码 `issue_diverged`）。面板先点答案，再列出同答案的已有 issue 供挑；所属 issue 还有别处且内容改了才问 `all` / `only this`；换答案 = 这一处离开原 issue；侧栏 `feedback` 页按 issue 分组。
- 会话侧：`path2_web/annotation/revision.py`（定格 `start_round`、改版报告 `revision_report`，模块说明里写了一轮的顺序和禁忌）；会话账本在 `path2_apps/<app>/mapping.yaml` 顶层键 `session`（`snapshot` / `conditions` / `tags`，解析在 `path2_web/mapping.py`）；规格 6.14「会话每轮的固定动作」。这套流程现在没有 skill，新会话读不读得到全凭运气。

## 用户 2026-11-10 定下的方向（不再讨论）

1. **反馈界面拿掉 `neg` / `off_pattern` 二分类。** 理由：反馈不进任何统计；「app 认错了还是定义缺一条」会话对照用户的定义自己判断得更准；这个标签允许「拿不准随便选」，会话不能当真；用户应从股票本身描述问题，不必先学软件的分类规则。盲看作答（来源不是 `picked` 的记录）照旧三选一，不动。
2. **一并拿掉 `dag` 按钮。** note 必写之后，一个 node 都不点已经表示「不在某一块上或说不清」。
3. **面板 = 可选的 node 按钮（可多选）+ 必写的 note。** node 按钮的意思统一为「问题落在这一块上」，不再区分认错还是缺条件。
4. **issue 随之简化**：一个 issue = pattern + nodes + note；挑选列表不再按答案过滤；没有「换答案」这回事；其余规则不变（复用时直接共享；所属 issue 还有别处且内容改了才问 `all` / `only this`；只有一处的 issue 改了不问；再点一次已选中的那条 = 不再共享；删除只删一处；侧栏按 issue 分组、组头写处数与还在买的处数；撤销删除时写回的作答照 issue 现有各处）。
5. **会话一侧加一个固定步骤**：每轮收齐 issue 后，会话通盘考虑，按 issue 给处理建议，分三类——
   - app 认得比用户的定义松：直接改 app，不用用户选，改完在改版报告里说；
   - 用户的定义里没有这一条：问用户要不要写进定义（这才是用户做的选择题）；
   - 当天看不出、留给调参、量过不值得：说明理由，用户可以反对。
6. **把会话每轮的处理流程写成项目级 skill**（`.claude/skills/<名字>/`），减少流程上的随机性。skill 管顺序、每步的产出与给用户看的格式、禁忌；不管判断本身（一句 note 翻成什么条件、几个 issue 是不是同一件事）；要改 app 结构、写 detector、查某处为什么认成这样、调阈值时转给现有的 `authoring-path2-app` / `authoring-path2-detector` / `diagnose-event` / `tune-gates-v3`，不重复它们。

## 必须守住

- **用户已有的标注一条都不能坏。** 用户的标注文件里已有反馈记录（带 `answer`，今天可能还存了带 `dag`、`issue` 的）。它们必须照样读得出、显示得出、能编辑、能复用，用户不需要做任何迁移动作。旧形状怎么兼容由设计定；`tests/path2_web/fixtures/annotation_store_v1` 的黄金重放测试与期望一字不改。设计前先用 `read_annotations` 只读地看一眼真实记录现在有哪些形状（只看形状，别把用户写的 note 原文抄进任何产出）。
- **后端任何时刻都同时接受旧形状和新形状的保存。** 用户的前后端开着热加载，开发途中页面可能新旧混搭；不能出现「存进去一条坏记录」的窗口。
- 用户眼下只用这一台机器（pc）：不为跨机器同步加提醒、防护或兼容。

## 待设计（fb-design 定；属于方向、定不了的回 team-lead）

- 记录形状：`picked` 反馈不再有二分类之后 `answer` 键怎么办（与盲看共用一个 kind）、旧记录里的 `answer` / `dag` 怎么读怎么显示、issue 一致性校验比哪些键、旧 issue 里答案或 `dag` 不同的各处怎么处理。
- 界面：面板布局（issues 列表现在一打开就能列）、node 按钮的悬停文字、反馈带记号上原来写答案的位置写什么、侧栏组头、hover 文案；保存条件（note 必写）。
- 改版报告里一条反馈的写法。
- 会话的「按 issue 给处理建议」：产出格式、三类各自怎么呈现、选择题怎么问（照用户级 `~/.claude/CLAUDE.md` 里关于提问的要求：AskUserQuestion、推荐项放第一位加「(推荐)」、白话讲清在决定什么）、结果怎么记进会话账本（现有 `conditions` / `tags` 够不够，尽量不加新结构）。
- skill：名字、description 的触发词（只取用户会自然说出口的词，见根 `CLAUDE.md`「创作 skill」节）、覆盖范围（以规格 6.14 已实现的部分为准，不替未实现的东西写流程）、与四个现有 skill 的交接点。

## 分工与文件归属（各管各的文件，别人的文件只读）

| teammate | 负责 | 可写的文件 |
|---|---|---|
| `fb-design` | 设计、答疑、最后的只读审查、写 `final_report.md` | 只写本目录（`docs/research/2026-11-10_feedback-unify-and-session-skill/`）下的 `design.md`、`final_report.md` |
| `fb-backend` | 存储校验、改版报告、后端测试；规格、说明书、词表、进度表 | `path2_web/**`、`tests/path2_web/**`、`.scratch/annotation-path2/spec.md`、`.scratch/annotation-path2/manual.md`、`path2_web/GLOSSARY.md`、`.scratch/annotation-path2-implementation/feedback-plan.md` |
| `fb-polish-ui` | 前端、vitest、e2e | `path2_web_ui/**` |
| `fb-skill` | 会话每轮流程的 skill；规格 6.14 里「会话每轮的固定动作」那几条的文字归 `fb-backend` 改，`fb-skill` 把要改的原文发给它 | `.claude/skills/<新 skill>/**`；需要会话侧新工具函数时与 `fb-backend` 商量，由 `fb-backend` 写 |

teammate 之间用 SendMessage 按名字直接沟通（问接口、报冲突、对文案），不必经 team-lead 转；方向性的分歧发给 `team-lead`。

## 阶段

1. **设计**：`fb-design` 先出 `design.md` 初稿（越快越好，先定记录形状与界面，再定会话步骤），发给另外三人；三人各自从可实现性上提意见（直接回 `fb-design`），`fb-skill` 同时起草 skill 的提纲并与 `fb-design` 对齐会话步骤。`fb-design` 定稿后通知全员「设计定稿」。定稿前其余三人只读代码、不改文件。
2. **开发**：三人并行实现；记录形状以 `design.md` 为准，发现设计走不通就回 `fb-design` 改设计再做，别各自变通。
3. **收尾**：各自跑完自己的测试后向 `fb-design` 和 `team-lead` 汇报；`fb-design` 对照设计做只读审查，把问题发回责任人改；全部过了，`fb-design` 写 `final_report.md` 并通知 `team-lead`。`team-lead` 负责最后的整体验证、skill 的试跑和白话版。

## 红线（全员）

- 不读 `datasets/pkls` 和 2026 年以后的行情；行情只经 `path2_web/data.py` 的 `read_bars`（读 `datasets/pkls_until_20251231`）。测试用合成数据或测试自建目录。
- **绝不写 `annotations/`**；读标注只经 `read_annotations`。测试、e2e 一律用临时标注目录（`create_app(config_override=...)` 或 `path2_web_ui/e2e/annotationBackend.py`）。
- 不碰端口 8001 / 5171 / 8767 上不是自己起的进程；**不要运行 `scripts/path2/run_path2_web.py`**；关进程只按自己记下的进程号，不用 pkill / killall。用户开着的后端会随 `.py` 改动自动重启、前端会热更新，属正常。
- 不 git commit / push / stash，不开 PR；不碰代理配置、Syncthing；不动本目录以外的 `docs/research/`。
- **实现产出与研究目录脱钩**：代码、测试、注释、skill、规格、说明书、词表里不出现 `docs/research` 字样，也不引用本目录的文件；需要的结论直接写进产出本身。
- 前端是类型无关渲染器，不为具体 node 名写分支；后端只做存储与校验、日期比对，不含走势语义。
- 界面固定文字用英文标识符风格、等宽、黑色；用户写的内容正常字体加浅灰底；解释放悬停（原生 `title`，英文小写短句）；不靠字色深浅区分。配色：要分开的两种颜色冷暖相反或深浅明显拉开，浅色填充配深色描边（用户色盲，靠冷暖和深浅分颜色）。
- 新界面名、新词照根目录 `GLOSSARY-MAP.md`「命名规则」起，列进汇报请用户认。
- 中文注释与 docstring；不走 TDD，但测试要写、要跑；e2e 用 `--workers=1`。
- 不用 playwright MCP（截图用 e2e 里的 `page.screenshot`，`scale: 'device'`，不改视口）。
- 写 skill 时照根 `CLAUDE.md`「创作 skill」节：description 的触发词只取用户会说的词；运行时只对用户暴露业务层，内部字段名、脚本名、阶段编号不往外抛。
- 调工具纪律：中途消息正文至多一句状态行（无代码 token、不预告"我去调用 X"），随后直接发调用；长篇解释只放不再调工具的收尾消息。若发现自己把调用写成了正文文字，不要停笔，在同一条消息里立即发出真正的调用。

## 汇报里要有的

改了哪些文件；新增或改名的界面固定文字、testid、记录键、原因码；和 `design.md` 不一致或自己拿了主意的地方；不放心的点；测试命令与结果原文摘要（已知与本任务无关的失败：pytest `tests/path2_web/test_serialize_tbseg.py::test_serialize_tbseg_walked_from_container`；vitest `tests/components.sidebar-result-list.spec.ts` 的 4 条）。

## 更新（定稿之后，覆盖上文与之冲突处）

**用户后来又定了三件事**（都已写进 `design.md`）：

1. 会话流程的 skill 不做成单独的反馈处理 skill，而是规格 6.10 的「循环技能」：照标注翻 app 与处理反馈合在一个 skill 里，共用一轮的骨架，定格一轮只做一次。名字 `annotation-round`。
2. `authoring-path2-app` 将被用户删除，标注这条线是创建 pattern 的唯一入口。新 skill 不交接给它、不引用它、不改它，删掉它之后必须照样完整可用。上文第 6 条里「转给 authoring-path2-app」作废；`authoring-path2-detector`、`diagnose-event`、`tune-gates-v3`、`feature-study` 仍然交接。
3. 从第一性原理设计最适合标注工具的 skill：先从标注这条线自己推出每一步需要什么知识，再去旧 skill 里取对得上、对着现在的代码仍成立的；默认不搬，旧 skill 的结构、分层、访谈式逐层确认都不沿用。
4. 定义文字只由用户自己在页面的 pattern 页改，会话只给建议的措辞。

**进度与续做（会话重启过，原来的四名 teammate 都不在了）**：

- 设计：`design.md` 已定稿，以它为准。
- 后端与文档（原 `fb-backend`）：已全部完成并自测（`uv run pytest tests/path2_web -q` → 652 过、1 条已知无关失败）。存储同时接受带 `answer` 的旧形状和不带 `answer` 的新形状；`path2_web/annotation/revision.py` 有 `start_round`（没有 app 时也能定格）、`round_digest`、`revision_report`（含第一版报告）；规格、说明书、词表、进度表已改。**这名成员已不在，审查发现后端或文档的问题一律发给 `team-lead` 处理。**
- 前端：这次任务的改动一行都还没写（`path2_web_ui/` 里现在是上一批「issue 复用」的代码，仍会发带 `answer` 的保存，后端照收）。由新的 `fb-polish-ui` 从头实现。
- skill：`.claude/skills/annotation-round/SKILL.md` 主文件已写完（189 行），但它指向的 `references/resume.md`、`references/checklist.md`、`references/writing-app.md`、`references/ledger.md` 和 `scripts/look.py` 都还不存在。由新的 `fb-skill` 补完并自查。
- 审查与最终报告：由新的 `fb-design` 做。

现在的分工表：`fb-design`（审查、写 `final_report.md`，只写本目录）、`fb-polish-ui`（`path2_web_ui/**`）、`fb-skill`（`.claude/skills/annotation-round/**`）。其余文件要改时发给 `team-lead`。
