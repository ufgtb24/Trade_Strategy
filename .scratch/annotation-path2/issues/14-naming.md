# 标注、mapping、app 产出与对照：各环节东西的命名

Type: grilling (HITL)
Status: resolved
Claimed: 2026-10-30 主目录 annotation-path2 分支会话

## Question

### Purpose

用户和会话讨论「标注直接变成 pattern、pattern 直接对回标注」时，标注、mapping、app 产出、对照这几个环节里的东西各有一个不混的名字，一个词只指一样东西；这张票定这些名字和以后起名的规则。

起因（2026-10-30）：标注原型里「买点」同时指用户的三角连同成员框、三角那一天、app 一次命中里算收益的那根 K 线，且包含 no_buy；pattern 同时指用户的形态和 app 的声明（`path2/GLOSSARY.md:73`）；match 同时指 app 的产出和对照的判定。用户要求按维度梳理、从第一性原理重新命名，可以重命名一切。

研究材料：`docs/research/2026-10-30_annotation-naming/`（`原始问题.md`、`inventory.md` 现状与出处、`final_report.md` 团队方案、`final_report_白话版.md`）。团队方案的若干推荐已被下面用户的决定取代（如「样例 / 像但不买」→ sample / negative sample，「shifted」不采用），以本票 Answer 为准。

## Comments

- 2026-10-30 讨论中逐项定下，过程见上述研究目录与当天对话；下列 Answer 为汇总。
- 2026-10-30 用户批准本 Answer，含第 4 节四个默认值和 match-hit-rename 规格里的三个默认名。
- 2026-10-30 执行第 6 节时：新词条（dag、sample 等）放在 `path2/GLOSSARY.md`「看图标注」一节末尾、pattern 与买点两条原地改写，没有挪动已有词条的行号——tune-gates-v3 的 SKILL.md 与 references、`docs/explain/` 按行号引用 :103～:118。

## Answer

**确认的倾向**：一个名字只占一格，格由维度交叉而成；不被旧决定和旧说法限制，从第一性原理推（用户 2026-10-30）。

### 1. 维度与主表

行 = 谁的、是定义还是实物（各带一个动作）；列 = 概念层级。

| | pattern | feature |
|---|---|---|
| 概念（不加修饰） | pattern | feature |
| 用户的实物（annotate） | sample = annotated pattern | box = annotated feature |
| app 的定义（map） | dag = mapped pattern | node / where = mapped feature |
| app 的实物（recognize，见第 4 节默认值） | hit = recognized pattern | event = recognized feature |

- mapping 从「概念」行接到「app 的定义」行；对照拿「用户的实物」与「app 的实物」逐格比（box↔event 得档位 tag，sample↔hit 得 match tag）；差 tag 拿 sample 与 dag 比。
- mapped feature 不总是 node：也可能是某个 node 上的 where、否定边或子事件；对应地 recognized feature 可能是某个 event 上过了的 where。
- 可再加列：attribute（box 上的属性 / where / where 的判定）、两段之间的关系（成员框先后 / 边 / 边是否满足）。

### 2. 已定的名字

| 名字 | 指什么 | 取代 |
|---|---|---|
| pattern | 抽象形态：用户起的名字加一句定义；sample 挂在它下面，app 改版不改归属 | 词表 :73「一组 node 加一组边的声明」改给 dag |
| dag | mapped pattern：app 对 pattern 的声明（node 加边）；代码类名 `PatternSpec` 不改 | — |
| sample / 样本 | annotated pattern：用户在一张图上、相对某个 pattern 下的一次判断连同依据；`judgment` 取 positive / negative | 标注里的「买点」、`instances`、样例 |
| positive sample / 正样本 | 这个 pattern 的 app 应该在样本日买 | 正例、buy |
| negative sample / 负样本 | 用户专门挑的、像这个 pattern 但样本日当天就看得出不该买的那天；没标的日子不是负样本；负样本上 app 买了几个不能当误报率 | 像但不买、反例、no_buy |
| box / 框 | annotated feature | — |
| member box / 成员框 | sample 收进的 box，即判断依据；**必须在样本日当天或之前结束**（因果性，用户 2026-10-30） | 成员（单说） |
| hit | recognized pattern：app 求解出的一次完整命中 | match（作为 app 产出的旧义，全仓改，见第 5 节） |
| match | hit 与 sample 的比较：这个 pattern 的 app 有 hit 的买点落在样本日的容差内（正样本前后 3 天或样本日落在那次 hit 的回踩事件里，负样本前后 1 天，天数待验证）；对正、负样本都适用，负样本 matched 即 app 在不该买处买了（朱红）；不设 shifted | `app:buy` / `app:no_buy` |
| matching | match 这个比较过程 | — |
| map / mapping | 会话的动作 / 它写下的那张表（不变） | — |
| 买点 | 只用于 app 一侧：hit 里真正买的那根（或几根）K 线；词表 :118 去掉「样本 bar」别名 | 标注里的「买点」 |
| tag | 界面上挂在某样东西旁、显示一个状态或结论的小方框；说时带种类：match tag、差 tag、档位 tag、两段之间的 tag | 签 |
| unsorted / 未归类 | sample 还没指定 pattern 的过渡状态，不是一个 pattern；数据存 `pattern: null` | 字面值 `'未归类'` |

数据键：`buy_points` → `samples`，`bp_id` → `sample_id`（编号前缀 `p` → `s`），`label` → `judgment`（值 `pos` / `neg`），「instance 注释」→ `note`。

### 3. 起名规则

写进 `GLOSSARY-MAP.md`「命名规则」，CLAUDE.md「上下文入口」加指针（用户 2026-10-30 批准，已写入）。要点：英文为规范名、词性分工（名词 = 东西、动词 = 动作、过去分词 = 状态）；组合名修饰词个数不限、每格只用该格允许的状态词、顺序「比较结果 + 判断 + 阶段 + 概念」；进界面、数据或反复使用的起短词，短词与组合名并存；定义先写组合名，再写英文定语从句，中文补充条件。

### 4. 默认值（2026-10-30 已批准）

| 待定 | 默认 | 理由 |
|---|---|---|
| app 的动作 | recognize | 组合名 recognized pattern = hit、recognized feature = event；不用 detect（被 detector 与 detected 档占用、且是事件层）、不用 solve（只是其中一步） |
| match tag 的取值 | `matched` / `unmatched` | 表示 sample 的状态，按词性用过去分词 |
| 买点的英文名 | buy point，「买点」作中文别名 | 英文为规范名 |
| 样本日 | sample date | 与数据字段 `date` 对齐 |

### 5. 界面与其他已定

- 标注原型的程序固定文字与悬停说明全部改英文；用户输入（特征名、定义、注释）与会话输出（题目、excluded 原因等）不翻译。CLAUDE.md 编码规范「界面中文」已删（用户 2026-10-30）。
- features 节 `in k/N` 一律显示（已在 f6bff31 落地）。
- match → hit 全仓改名另立：`.scratch/match-hit-rename/spec.md`（草稿）。

### 6. 批准后要改的（这一次批准全部覆盖）

- `docs/research/2026-10-28_annotation-web-loop/repro/mock_v4.html` 与同目录 `backend_contract.md`：按第 2 节改名、按第 5 节英文化、成员框按因果性只收样本日当天或之前结束的框（跨过样本日的不收并提示），一次完成，跑同目录 `smoke.mjs`。
- `path2/GLOSSARY.md`：:73 pattern 改写、新增 dag；:118 买点去「样本 bar」别名并注明只用于 app 一侧；新增 sample、positive sample、negative sample、member box、sample date、unsorted；match / hit 词条随 match-hit-rename 改。`path2_web/GLOSSARY.md`：新增 tag（`_Avoid_` 签）；:45 bracket 注明 hit 与 sample 两种跨度；:20 锚 pattern、active pattern 注明选的是 app。
- 票「结构化标注：存什么、界面和主视图怎么合」（01）Comments 记一行指向本票；票 09、11 里标注侧的「买点」改称 sample；票 12、13 的「像但不买」改称 negative sample。
- `map.md` Decisions so far 加本票一行。
- 本票 `Status: resolved`。
