# rubric.md：标注原型 mock_v4 的 web-loop 验收表

本文件是本次循环所有 reviewer 与 implementer 共用的**绝对标准**（配合 `.claude/skills/web-loop/principles.md` 的通用底线）。本文中项目内路径均相对 repo root。

- 被改的文件：只有 `docs/research/2026-10-28_annotation-web-loop/repro/mock_v4.html`（起点 = `docs/research/2026-10-28_annotation-groups-rethink/repro/variant_a_columns.html`，即上一轮定下的 instances 表版本；顶部只多了一个空 favicon）。
- 演示数据：`docs/research/2026-10-26_annotation-workflow-polish/repro/data.js`，只读。**绝不读 `datasets/` 下任何东西。**
- 页面：http://localhost:8792/2026-10-28_annotation-web-loop/repro/mock_v4.html
- 简称：polish = `docs/research/2026-10-26_annotation-workflow-polish/final_report.md`；groups = `docs/research/2026-10-28_annotation-groups-rethink/final_report.md`；基线 = 同目录 `baseline.md`。

## 使命与两条原则（用户 2026-10-28 定，一切取舍以此为准）

标注工具的使命：用户通过看图标注直接得到 path2 pattern（结构化标注是构建 pattern 的唯一方式；七步流程：找图 → 标注 → 写 app → 拿 app 对标注 → 盲看 → 调参 → 最后检查，`docs/research/2026-10-23_annotation-path2-direction/方向讨论.md` 第 3 节）。

1. **标注功能能高效、高质量地完成这个使命**：标得快、标得准，标出来的东西能直接变成 pattern、pattern 能直接对回标注。
2. **用户友好、心智负担低**：用户要知道的概念、要记的规则、要认的词越少越好；看一眼就读对。

## 0. 判法总则

1. **must / nice**：违反第 2 节任一硬条款、违反 GOAL 子项、真实 bug 或回归 = must；其余改进建议 = nice。
2. **【方向题】**：凡是会推翻第 4 节「已定规矩」的，或者要在两条都说得通的路之间选一条的，**一律记 nice，标题以【方向题】开头**，正文写清：选项（至少两个）、各自代价、推荐哪个及理由。**implementer 不做【方向题】**；reviewer 也不得因为「没做某个【方向题】」记 must。第 7 节列出已知的方向题，不要重复提。
3. **只判截到的证据**：需要别的状态才能看到的，写「需加 state」，不自己开浏览器。
4. 指出缺陷，不设计替代方案（【方向题】除外，它本来就要写选项）。

## 1. 项目特化（填 principles.md 的占位）

- **核心链路**：在主图画框 → 起或选特征名 → 放买点（`buy` / `no_buy`）→ 框归哪个买点（界面默认，框或买点任一边改）→ 未归类页整行挪进 pattern → pattern 页看 `features` 区、`instances` 表、页头 `next` / `ask` → 打开 `ask` 单子作答 → `compare` 档对照 app → 点两段之间的签跳图。
- **架构红线**（code lens）：
  - 单个静态 HTML 文件；只从 data.js 读演示数据；不新增外部依赖、网络请求、`localStorage` / 任何持久化。
  - 状态都在全局 `S` 上、改完调 `render()` 全量重画，沿用现有写法。**以下名字不得改名或删除**（截图靠它们进状态）：`S.mode`、`S.tab`、`S.cur`、`S.sel`、`S.stock`、`S.vKey`、`S.askOpen`、`S.labels`、`S.patterns`、`S.lkOpen`、`render()`、`STOCKS`、`annOf()`、`sigOf()`；`data-act` 的 `mode:` / `vkey:` / `lkopen:` / `lkgoto:` / `goto:` / `askopen` 动作保留。
  - 不改 data.js、mock_v3、旧报告、`.scratch/` 下的票和地图、两份 `GLOSSARY.md`。
- **smoke**：`node docs/research/2026-10-28_annotation-web-loop/repro/smoke.mjs`（内联脚本逐段 `node --check` + 页面打开后 console error / pageerror 为零）。

## 2. 硬条款（全部 lens 通用，违反 = must）

| # | 条款 | 怎么判 |
|---|---|---|
| H1 | **每个标签只有一个来源**：界面上每个签 / 值属于用户、会话、app 三者之一，底色与来源一致（用户无底色；会话浅蓝 `#93c5fd`；app 琥珀 `#fdecc0`） | 同一个签在两处底色不同、或一个签的值由两个来源拼成 |
| H2 | **规则不随阶段或页面变**：同一元素在不同页面、不同 mode、有没有 app 时，算法和意思一致 | 例：同一个计数在两页分母不同；同一个按钮在两页做不同的事 |
| H3 | **同一个词只有一个意思**（全界面，含悬停） | 例：`session` 既指「会话写的内容」又指「等会话处理」 |
| H4 | **没有任务对应的元素**：截图里每个列、签、按钮、计数、颜色都要能对到第 3 节的某个任务 | 对不上 = must（razor 主判） |
| H5 | **新手第一眼读错**：几周没碰、不看悬停的用户第一眼会读错、读不出，或会因此点错下一步 | newbie 主判，正确含义见 baseline.md 的元素含义表 |
| H6 | **界面文字规则**（`~/.claude/rules/ui-text-style.md`）：程序固定内容（字段名、状态、按钮、标签页、表头）用等宽标识符，可用英文；用户 / 会话的业务内容用正常字体，不在输入框里的加浅灰底；**字一律黑色**，灰字只给空着或没选上的状态；**说明放悬停**，界面上不写说明句、口语问句，不重复已显示的内容；字段名用名词、状态用枚举或布尔 | 任一处违反 |
| H7 | **色弱**：区分只靠明暗差或一冷一暖，不靠同冷暖、深浅相近的两色（如绿-橙、蓝-紫、浅黄-浅绿）；**朱红 `#D55E00` 只有一个意思**：app 的判断 / 结果和用户的标注对不上 | 新出现靠色相区分的一对；朱红用在别的意思上 |
| H8 | **已定规矩不得违反**（第 4 节）；要推翻只能记【方向题】 | 改动与第 4 节冲突 |
| H9 | **心智负担不得变多**：按第 5 节的数法数本轮的概念数、要记的规则数、屏上固定词数，**任一项高于基线 = must**（写出本轮数与基线） | razor 主判 |
| H10 | console error / pageerror 为零；smoke 全绿 | func 主判 |
| H11 | **高频操作不得变慢**：第 3.2 节每项的点击数不得多于基线列 | func / razor |
| H12 | 布局不崩：无溢出、截断、遮挡；关键按钮可见可点（principles 轴 ③） | ux |

## 3. 任务清单（razor、func 的对照依据）

### 3.1 用户打开各处的时刻（groups 的 `flow.md` 第 1 节 A～K，加标注时刻）

| # | 时刻 | 用户想知道 / 要做 | 主要在哪 |
|---|---|---|---|
| T1 | 标注一张图 | 画框、起或选特征名、改起止、填属性、放买点选 label、框归哪个买点 | 主图 + `instance` 页 |
| T2 | 起新特征名、发现近义词 | 有没有已有的同义特征；合并 | `instance` 页输入框、`features` 页 `→ merge` |
| A | 未归类攒了一批 | 哪些是一回事，整行挪进 pattern | 未归类页 |
| B | 任何时候 | 挨个翻、找一张不在眼前的买点 | `instances` 表缩略图 |
| C | 已命名、没 app | 有没有混进别的（不拿「多数」当参照） | `features` 区点 `in k/N` |
| D | 会话写完单子 | 答单子 | `ask` 单子 |
| E | 每轮 app 后 | app 对得怎样 | 页头 `app:buy` 两个总数 |
| F | 每轮 app 后 | 漏买 / 误买的是哪几张 | `instances` 表朱红行 |
| G | 有 app 后 | 这个正例为什么和必须有对不上；补框 | `must / must_not` 列、跳图补框 |
| H | 有 app 后 | 像但不买为什么被买 | 缩略图悬停（不挂差签，groups 4.4） |
| K | 忘切 pattern | 把混进来的一批（含像但不买）整排挪走，在写第一个 app 前 | `features` 区点开后的 `→ pattern` |
| T3 | 对照 | 框底下 app 认出了什么、够不够格、两段之间连没连上 | `compare` 档主图 band 与签、`instance` 页 compare 节、两段之间的签 |
| T4 | 几周后回来 | 这个 pattern 走到哪一步、等谁 | 页头 `next` |
| T5 | 只看 app | app 在 K 线上跑出了什么 | `app` 档 |
| T6 | 存档 | 标注文件长什么样 | `json` 页 |

I（调参丢了哪几张）、J（每轮翻了哪几张）不归界面（groups 第 2 节）。

### 3.2 高频操作与基线点击数（polish 3.2、groups 的 `ui.md` 4.1 的 A 列；按代码数）

| 操作 | 基线 |
|---|---|
| 画已有特征的框 | 1 |
| 改起止 | 1 |
| 改属性 | 2 |
| 补画了没收（主图 `◂` / instance 空槽） | 1 |
| 补画了没收（从 pattern 页缩略图出发） | 3 |
| 未归类一行挪进已有 pattern | 1 |
| 一行挪进新 pattern | 2 + 起名 |
| 找到漏买那张并打开对照 | 1（+1 若未开 `compare`） |
| 查没 app 的 pattern 混没混（点一个特征计数） | 1 |
| 几周后回来知道等谁 | 0（看 `next`） |
| 近义词合并 | 2 |
| 指定框归哪个买点 | 1 |
| 挨个翻完 6 个买点 | 6 |

## 4. 已定规矩（H8；推翻只能记【方向题】）

- **流程**：polish 第 2 节（2.2 灵活与规范的分界、2.3 阶段表、定级规则、必须项检查、2.4 偏离与像但不买）。
- **不变量**：polish 2.5 的 N1～N11。尤其 N6 分母只数正例；N7 买点只属于一个 pattern、框不属于任何 pattern；N11 框归哪个买点只在界面里定。
- **界面**：polish 第 3 节 U1～U39（U2、U16 里关于 groups 的部分已被 groups 第 4 节取代），及其「不做的」一段。
- **instances 表**：groups 第 4 节全部（三列各管一个来源、并行键、行序、朱红一刀切、像但不买不挂差签、列表缩略图无 `◂`、`features` 区 `in k/N` 点开含像但不买、属性计数不可点）。
- **配色**：band 档位 matched = node 本色 / qualified 深灰 `#9ca3af` / detected 浅灰 `#d1d5db`；`qualified` / `detected` 签挂每根灰 band 右端，框旁只剩 `missing`（白底虚线）；会话一侧的签浅蓝；`not_sample` 白底；`app:buy` / `app:no_buy` 琥珀、对不上朱红。

## 5. 数法与基线（H9，razor 每轮按同一把尺数）

数法照 `docs/research/2026-10-28_annotation-groups-rethink/critic.md` 第 5 节：
- **概念**：用户要知道「它是什么」才能读对的东西；同一含义多处出现算一个；全工具通用的（buy / no_buy、pattern、点缩略图跳图）只在第一次出现的区域算。
- **规则**：用户要记住才能读对或用对的条件句（「X 时 Y」）；屏上直接写着的不算；悬停写着、但不悬停就会读错的算。
- **固定词**：屏上出现的不同程序固定词（表头、签、按钮、符号、状态值）；用户内容不算；同词算一次。

**基线（起点 mock_v4，逐项清单见 `baseline.md`）**：

| 区域 | 概念 | 规则 | 固定词（首次出现，全局去重） |
|---|---|---|---|
| ① 顶栏 | 6 | 2 | 15 |
| ② 主图 | 25 | 14 | 17 |
| ③ instance 页 | 9 | 12 | 46 |
| ④ features 页 | 3 | 2 | 7 |
| ⑤ pattern 页（不含单子） | 17 | 9 | 17 |
| ⑦ ask 单子 | 5 | 4 | 10 |
| ⑧ 未归类页 | 1 | 0 | 2 |
| ⑥ json 页 | 1 | 0 | 21 |
| **总计** | **67** | **43** | **135** |

- 口径（切词、概念粒度、去重顺序 ①②③④⑤⑦⑧⑥）照 `baseline.md` 第 1 节；**逐项清单在 `baseline.md` 第 2 节，razor 每轮对着清单逐项增删，不要只比总数**（概念粒度换人数会差两三个）。写出「本轮新增了哪几项、删了哪几项」再给总数。
- 元素的正确含义：`baseline.md` 第 4 节元素含义表（newbie 先看图写读法，再对照它）。注意第 4 节记的是**起点**的含义，其中标「见疑点」的几行本身就是问题，以本文件第 2、4 节为准。
- 起点已知的问题：`baseline.md` 第 5 节「疑点」15 条（例如主图 `compare` 下偏离的 buy 没买仍是琥珀、与列表的朱红一刀切冲突；`qualified` 在主图和 pattern 页 `qualified k/n` 里意思不同；同一个差签在列表和主图、单子里底色不同）。它们都是 H1～H8 的候选 must，reviewer 按本轮截图证据判。

## 6. 各 lens 的重点

- **ux**：H6、H7、H12；对照态（`compare` + `labels`）的签与 band 是否叠压、看得清。
- **func**：GOAL 子项逐条；H10、H11；核心链路各状态都进得去；第 3 节每个任务在截图里有入口。
- **code**：本轮 diff 无 bug；第 1 节架构红线；不留只为变体 B / C 写的死分支以外的新死代码（旧的死分支可记 nice）。
- **rival**：独立复核 H1～H3、H5，专找别人容易放过的。
- **razor**：H4、H9、H11；只指出多出来的东西。
- **newbie**：H5；先看截图写读法，再 Read baseline.md 的元素含义表对照。

## 7. 已知方向题（不实施，不重复提；跑完连同新方向题一起交用户）

1. 每轮改完 app 判断翻了哪几张：只写在会话交付说明里，还是在列表每张上标「这轮翻了」（要存每一版 app 对每一张的判断）。（groups 6.1）
2. 像但不买的差签要不要恢复可见。（groups 6.2）
3. 列表里补收「画了没收」的框从 1 下变 3 下，要不要在列表缩略图上加「先跳到图上确认再收」的入口。（groups 6.3）
