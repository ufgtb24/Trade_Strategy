# 词表收尾与全仓终检

Status: ready-for-agent
Progress: done
Claimed: 2026-11-05 parallel-tickets ticket-06 @ worktree impl/06-glossary-and-final-check
Blocked by: 05

## Purpose

词表定下 hit 和 match 的新义之后，讨论里 match 只指样本与 hit 的比较。本票改词表，并对全仓做最后一次检查，给整个改名收口。

## Source

- [spec](../../match-hit-rename/spec.md)「新旧对照」第 5、7 行（三档词条、bracket 词条）、「验收（草稿）」第 1～3 条、「注意」。
- [决定票 14](../../annotation-path2/issues/14-naming.md)第 2 节 hit、match、matching 三行，第 6 节「match / hit 词条随 match-hit-rename 改」。
- 用户 2026-11-04「最后进词表」。

## Inherited Direction

- 共用执行边界第 1～14 条。
- **写词表的授权**：用户 11-04 明确要求最后进词表，所以本票直接写，不另走 `/grill-with-docs`。
- **词条内容照决定票 14 第 2 节的对照表**：
  - hit = recognized pattern，app 求解出的一次完整命中，`_Avoid_` 旧义 match；
  - match = hit 与 sample 的比较。容差引用 `.scratch/annotation-path2/spec.md` 第 10 节「match 容差」一行，不抄天数；
  - matching = match 这个比较过程。
  - 表里没给的中文别名不自造。
- **词条写法**：照 `GLOSSARY-MAP.md`「命名规则」第 5 条，以及 CLAUDE.md「写词条时」那几条（词头多写、第一个是规范词；`_Avoid_` 只放不正当说法；词头与 `_Avoid_` 不相交）。
- **行号引用**（spec「注意」）：`path2/GLOSSARY.md` 的行被现行文档按行号引用，下面「What to build」列了全部清单。
  - 能不移行就不移；移了就把这些现行引用同步改对；
  - 已关闭的票和研究目录里的引用不改（共用执行边界第 8 条）。
- **`matched baseline` 移出词头**（拆分总览「审阅时用户的选择」第 2 条，用户 11-04 定）：讨论层面 match 只剩一个意思；代码内部名不动。

## What to build

- `path2/GLOSSARY.md`：
  - 原 match 词条（:95）改成 hit 词条；
  - 新增 match、matching 词条，放在标注那一节；
  - :99「完整匹配」改「完整命中」（共用执行边界第 12 条）；
  - :114 的别名 `matched baseline` 移进同一词条的 `_Avoid_`，并写理由：matched 已是 sample 的状态词（拆分总览「审阅时用户的选择」第 2 条）。
- `path2_web/GLOSSARY.md`（都就地改，不移行）：
  - :5 核心词里的 match 改 hit；
  - :26 与 :28～:29 三档改为 `detected、qualified、in_hit`，定义写「进了某一次 hit」；
  - :46 bracket 写「一次 hit」（sample 那句已经在）；
  - :62「没被匹配上」改「没命中」。
- `GLOSSARY-MAP.md` :12 的「event / node / match」改为 hit。
- 如果移了行，同步这些现行引用：
  - `.claude/skills/tune-gates-v3/SKILL.md`、`.claude/skills/tune-gates-v3/references/method.md`；
  - `docs/explain/tune-gates_v3_通俗解释.md`；
  - `.scratch/annotation-path2/spec.md`、`.scratch/annotation-path2/manual.md`；
  - `.scratch/annotation-path2-implementation/v-s1-notes.md`；
  - 实测共 40 处，都指向 :95 之后的行。
- 全仓终检：在合并了 01～05 的树上，对全仓跑一次残留检查，再跑一次测试全套。
  - 残留检查用 `evidence/05/residual_check.py`：`evidence/01/` 那份把中文文件名漏掉了（票 05 完成记录）；
  - `docs/sample_usage/bb_v1.jsonl` 是落盘的账本，有一行说明文字是旧义「宽进 match」，其余是统计配对，照共用执行边界第 7 条不改，单列进允许列表；`docs/setup/ubuntu_tkinter_font_fix.md:140` 的「不匹配」是泛指。

## Scope and exclusions

- 不改已关闭的票、研究目录和 `evidence/`。

## Blocked by

05

## Acceptance criteria

- `path2/GLOSSARY.md` 有 hit、match、matching 三个词条：
  - 每个词条的词头与自己的 `_Avoid_` 不相交；
  - match 词条只讲样本与 hit 的比较；
  - hit 的 `_Avoid_` 里有旧义 match。
- 两份词表和 `GLOSSARY-MAP.md` 里，除新义外没有 match。三档词条是 `detected、qualified、in_hit`。
- 行号检查脚本：对上面清单里每一处引用，改后那一行的词头与改前所指的词头相同。脚本和结果进 `evidence/06/`。
- 全仓终检（spec「验收（草稿）」第 1、2 条的收口）：
  - 全仓残留只剩允许列表，按类别与区域给出条数；
  - 测试全套的失败清单与 01 开工时的基线相同。
- 完成记录再提一句「旧 scan 需重扫」。
- `未安排人审：新词条的措辞；原因：内容照决定票 14 已批准的对照表，没有 build-on point，措辞不顺随时改`

## 完成记录

2026-11-05，parallel-tickets ticket-06。合并提交 9128d35（`--no-ff` 合回 `annotation-path2`），分支尖 f0f349b；调度分支在本票期间没有前进，合并后的树与分支尖相同。证据都在 `evidence/06/`。

改名到此收口：词表里 hit 指 app 的产出，match 只指样本与 hit 的比较，和代码、skill、文档说的一致。全仓查过一遍，留下的 match 字样都能归到允许的用途里；测试全套的失败清单和改名开工前相同。这说明改名没有改坏东西，也没留下旧义；不说明新词条读着顺，那是末尾「未安排人审」那行的事。**旧 scan 需重扫**：scan 文件的键在票 02 改了，不做兼容。

**做了什么**
- `path2/GLOSSARY.md`：
  - :95 原 match 词条改成 `hit / 命中 / recognized pattern`，`_Avoid_` 里是旧义 match 和中文「匹配」；
  - 新增 `match`（:183）、`matching`（:188），放在「看图标注」一节末尾。容差只引 `.scratch/annotation-path2/spec.md` 第 10 节，不抄天数；`match` 的 `_Avoid_` 放对照表的 `app:buy`、`app:no_buy` 和 `shifted`；
  - node 诊断的「完整匹配」改「完整命中」；
  - `matched baseline` 从 :114 词头移进 :116 的 `_Avoid_`，理由写 matched 已是 sample 的状态词。
- `path2_web/GLOSSARY.md`：:5、:26、:28～:29、:46、:62 就地改，行数不变。
- `GLOSSARY-MAP.md` :12 改 hit。
- 票面没列、因本票变假才改的（都不移行）：
  - `CLAUDE.md` 词头数 47 → 49；
  - `.scratch/annotation-path2/manual.md`：:56 删「该行第三档仍叫 matched」；:73 原来讲「path2 一直把一次完整求解结果叫 match、bracket 词条还写着一次 match」，改成 hit 与 match 的区分；:53、:55 的出处指到 hit、match 自己的词条；
  - `.scratch/annotation-path2/spec.md` 未决表 U5 改成「已解决：2026-11-05 实施完成」。

**不移行是怎么做到的**
- hit 词条比原 match 词条多一句英文、一行 `_Avoid_`。英文定语从句和中文写在同一行（命名规则第 5 条没要求分行）；`### 度量` 标题后去掉一个空行，抵掉多出的一行。新词条加在文件末尾。
- 结果：:103 之后除 :114、:116 外逐行没动，:95～:102 内部的行动了，现行文档没有引用这一段。`v-s1-notes.md` 不用改，没动。
- **以后谁给 `### 度量` 补回空行，:103 之后的引用就都错一行。**

**词条的取舍**
- 「命中」进词头：票面写「表里没给的中文别名不自造」，但拆分总览「审阅时用户的选择」第 1 条写了「hit 的中文名『命中』」，所以不算自造。match、matching 没有中文名。
- hit 的正文写了代码名 `PatternHit`，和 dag 词条写 `PatternSpec` 同样处理。

**验收**
- 词条（`check_glossary.py`，结果 `glossary_check.txt`）：三个词条都在；两份词表全部词条的词头与自己的 `_Avoid_` 不相交；hit 的 `_Avoid_` 有 match；三档词条是 `detected、qualified、in_hit`；`CLAUDE.md` 写的 49 与实际相同。两份词表和 `GLOSSARY-MAP.md` 里剩下的 match 字样逐行列在结果末尾，只有新义和 hit、同日对照两处 `_Avoid_`。
- 行号（同一脚本，引用取自改前的文档）：79 处。票面的 6 个文档之外多查了 `write-user-doc/SKILL.md`。票面的「40 处」只数 :95 之后的；这里把 :95 之前、`path2_web/GLOSSARY.md` 和 spec 里没写文件名的 `:NNN` 也算上。
  - 词头相同 73；
  - 规范词相同、词头少了别名 5（都是 :114，票面要求的）；
  - 词条按票面改名 1（`path2_web/GLOSSARY.md:28`）；
  - 错位 0。
- 全仓残留（`residual_check.py report`，结果 `final_check.txt`，判定清单 `allow_06.tsv`、`allow_path_06.tsv`，规则在 `gen_allow.py`）：**未归类 0，退出码 0**。按行计，一行可算进几类；各小类和全部区域见结果文件。

  | 类别 | 条数 | 区域 |
  | --- | --- | --- |
  | 测试框架 | 310 | skills 209、tests 56、前端 45 |
  | 统计里的配对 | 114 | skills 94、`feature_candidates.md` 19、annotation-path2 1 |
  | mismatch 一族 | 100 | skills 48、前端 22、tests 16、path2 6、annotation-path2 5、docs/path2 2、path2_web 1 |
  | 「一致 / 等于」 | 93 | skills 57、tests 21、前端 10、path2_web 3、docs/explain 2 |
  | 中文「匹配」泛指 | 85 | tests 26、skills 23、前端 19、path2 8、`CLAUDE.md` 与 `AGENTS.md` 4、docs/path2 2、path2_web 1、`docs/setup` 1、`.gitignore` 1 |
  | 正则与模式匹配 | 78 | skills 38、path2_web 20、前端 17、scripts 3 |
  | 新义本身 | 54 | annotation-path2 42、词表 10、前端 2 |
  | web-loop 工作流脚本 | 41 | skills 41 |
  | 过时旧名（票 05 的清单，单列） | 25 | docs/path2 21、docs/explain 4 |
  | 第三方包名 | 14 | `package-lock.json` 14 |
  | 别的系统（新闻情感评测） | 11 | `experiments/` 11 |
  | 拿不准（单列，见下） | 5 | annotation-path2 4、docs/explain 1 |
  | 落盘账本的值 | 4 | `docs/sample_usage/bb_v1.jsonl` 4 |
  | 词表 `_Avoid_` 里写明的旧说法 | 2 | 词表 2 |
  | 研究目录、归档里的路径 | 2 | `feature_candidates.md` 2 |
  | 本批改名自身的记录与指针 | 217 | match-hit-rename 214、annotation-path2 3 |
  | 已关闭的票、决定票原型、研究目录、归档票文件名 | 75 | annotation-path2 75 |
  | 不在范围的地方 | 4619 | 本批证据 2405、`docs/` 历史 1678、BreakoutStrategy 等 441、`scripts/experiments` 等 83、`tests/` 其他 10、annotation-path2 证据 2 |

- 全仓 Python 旧接口名（`api_check.txt`）：范围内 0，JSON 键字面量 0。
- 受管文件名里带 match 的：范围内只剩决定票 `issues/08-blind-match-list.md`（已关闭）和本批自己的目录。
- 两个检查都确认过拦得住（`negative_controls.txt`）：词表 :95 前多插一行，报 56 处不通过；含 `res.matches`、`m.match_id`、「一次匹配」的文件，2 行进未归类。两次退出码都是 1。
- 测试全套（比较结果 `test_compare.txt`，命令 `run_py.sh`、`e2e/run_e2e.sh`、`make_compare.sh`）。失败清单与票 01 开工时的基线 1359914 相同：
  - pytest（`tests/path2 tests/path2_apps tests/path2_web tests/scripts`）：两边都是 1229 通过、2 跳过、6 失败，清单相同：`test_throwback_v4.py` 4 条、`test_self_contained.py::test_no_breakoutstrategy_imports_in_path2`、`test_serialize_tbseg.py::test_serialize_tbseg_walked_from_container`；
  - skill：两边都是 tune-gates 547 通过、13 跳过，tune-gates-v3 156 通过，feature-study 47 通过、2 跳过，diagnose-event 11 通过；web-loop 4 个文件、107 个场景全过；
  - `npx vitest run`：基线 1088 通过、4 失败，终检 1089 通过、4 失败，多的一条是票 03 加的，失败清单相同；`npx vue-tsc -b` 通过；
  - e2e 同一批 13 个文件 36 条，逐条状态相同：19 通过、17 失败。其中 `annotate-rally-random.spec.ts:145` 用的是基线的重跑结果：基线首轮通过，是因为跑到它时检出里还没有 `.venv`；票 01 在基线代码、有 `.venv` 的条件下重跑同样报 ENOBUFS（`evidence/01/e2e/results-base-rerun-rally-random.txt`），终检也是 ENOBUFS（`logs/e2e.log` 第 44 行）。这是环境问题，和改名无关。

**基线怎么比的**（调度会话的约定）
- 票 01 的 Python 基线没带护栏。本票在 1359914 的干净检出上，用和终检一样的护栏（`evidence/04/wall/sitecustomize.py`）和重定向（`wall/wall_redirect.py`）重跑了 pytest 和 skill，拿它比较。
- 两边的差别：带护栏的基线与票 01 的原基线计数相同、失败清单相同，所以护栏和重定向没有改变结果。重定向让 `test_throwback_v2`、`test_bb_v1` 读 AA.pkl 时止于 2025-12-31（测试写的窗口到 2026-03-08），`PKL_DIR` 那批测试改读副本；这些测试两边都通过或按原样跳过。
- 票 04 的插件只管 `test_multivar_equiv`，所以扩了一份放在 `wall/`。首轮 `PYTHONPATH` 把 04 的目录放在前面，加载了旧插件：两边都是 1210 通过、19 跳过、8 失败，护栏拒绝 20 次。那轮作废，改顺序重跑。它也说明护栏真的在拦。
- 前端没重跑基线：vitest、vue-tsc 不读行情；e2e 里读 `datasets/pkls` 的只有不跑的 `miss-detection-walkthrough`。

**跑在哪个版本**
- Python 与 skill 的最后一轮跑在 d67bf49（审查修改之后）。之后只提交了证据。
- vitest、vue-tsc、e2e 跑在 bc33f87，工作树多未提交的证据脚本，e2e 期间端口临时改成 8095 / 5195，已复原。从那时到合回，证据目录之外只改了 `manual.md:73` 的一个词和 `matching` 的英文句，都和前端无关，所以没重跑。

**没跑什么、为什么**
- e2e 22 个文件跑了 13 个，这 9 个没跑：
  - `miss-detection-walkthrough` 和夹具脚本：直接读 `datasets/pkls`，数据墙；
  - `kline-ctrl-wheel-right-anchor`、`marker-click-focus-highlight`、`shift-pair-feedback`、`sidebar-chart-focus`、四个 `subchart-*`：写死已不在的旧扫描，每条等满 600 秒才失败，票 01～03 同样没跑。它们里改过的名字只由票 03 的 `e2e_static_check.py` 盖到。
- 跑了但基线就失败的 17 条（`dev-ui-replication`、`flow`、`hit-event-disambig`、`scan-dialog`、`annotate-rally-random:145`），改过的名字没被执行到多少，票 03 写过，本批不修。
- skill 冒烟和主视图截图没重做：验证责任归 04、03。本票之后只动了词表和文档。

**数据墙**
- Python、skill、e2e 的后端和残留检查全程带护栏，探测确认会拒绝打开 `datasets/pkls`（`logs/*-guard-probe.log`）。`check_glossary.py`、`gen_allow.py`、比较脚本只读文档和 git，最后一轮没带。作废那轮之外，记录都是 0 行（`logs/after-wall.log`、`base-wall.log`、`e2e-wall.log`）。作废那轮 20 次都是被拒绝，没读到内容。
- 证据和本记录不转述 2026 年的 K 线、hit 或结果。`final_check.txt` 每行只留前后 24 字、数字打码，`docs/sample_usage/bb_v1.jsonl` 按整文件判定、不抄原行。日志里的 `2026` 只有运行时间戳。
- 写到共用位置的：没有。`datasets/` 只读，`annotations/` 没碰（合回前查过，90 分钟内没有新文件），标注用临时目录、机器名 `e2e`。没有请求发往 8001 / 5171。没用 Playwright MCP，`.playwright-mcp/` 没动。基线检出放在 scratchpad，用完已 `git worktree remove`。

**独立审查**（`review-standards.md`、`review-spec.md`，各附处理；修改在 d67bf49，之后重跑了 Python 与 skill 全套、残留检查、词表检查）
- 已修：`manual.md:73` 的「全仓」改「讨论里」（参数快照比较的 `match` 字段和 `matched_*` 还在）；`matching` 的英文补主体；证据脚本补 docstring、改形参名、不再写死 worktree 路径、删掉和票 02 相同的副本；e2e 比较用同样条件的基线重跑，并留下日志。
- 不改：`path2_web/GLOSSARY.md:28` 不补英文句（票面要就地改，补了要移行，这份词表早于命名规则的词条都没有英文句）；`cmd_report` 与 `cmd_area`、`load_allow_path` 与 `load_allow` 的重复（只跑这一次的脚本，`cmd_area` 要和票 05 那份输出相同）。

**单列，留给调度会话**
- 拿不准、没改：
  - `.scratch/annotation-path2/scripts/01-dump-proto-data.py:49` 的 `res.matches`：决定票 01 的原型取数脚本，本来就跑不起来（票 01 记过）；
  - `docs/explain/next_mode_ptr_advance_通俗解释.md:197` 的「unmatched satisfy」（票 05 记过）。
- `docs/sample_usage/bb_v1.jsonl:8` 有一行旧义说明文字「宽进 match」，是落盘账本的值，照共用执行边界第 7 条不改。
- `GLOSSARY-MAP.md` 第 3 条的「event 允许 detected / qualified」没动：票面只要改 :12，句子带「如」，不算假。`in_hit` 要不要也列进去，用户看词条时可以一起定。
- 票 05 留下的：`docs/path2/` 过时清单待另起票；记忆备份 `~/.claude/backups/memory-before-ticket05-20261104/` 等用户确认后再删。

**改了哪些共享机制**
- `path2/GLOSSARY.md`：词头 49 个，:96～:102 内部移了行，:103 之后的行号不变。
- `CLAUDE.md`（每个会话都加载）1 行里的数字。`.scratch/annotation-path2/spec.md`、`manual.md` 上面那几行。
- 没有接口、JSON 键或落盘记录的格式变化。
- 本批已没有未开始的票。`.scratch/annotation-path2-implementation/issues/` 里没有票引用 :95～:102。
- `evidence/06/residual_check.py` 在票 05 那份上加了 `report` 子命令和 `--allow-path`，分类规则没动。

`未安排人审：新词条的措辞；原因：内容照决定票 14 已批准的对照表，没有 build-on point，措辞不顺随时改`

## Comments

- 2026-11-04 发布。人审行由拆分时按 `docs/agents/review-planning.md` 的推荐写入，用户在审阅中按推荐批准。
