# skills 的正文、脚本与输出

Status: ready-for-agent
Progress: done
Claimed: 2026-11-04 parallel-tickets ticket-04 @ worktree impl/04-skills
Blocked by: 02

## Purpose

用户跑 skill 时听到的说法，要和代码、词表一致。本票把 skill 正文、脚本和运行输出里指 app 产出的 match 都换成 hit。

## Source

- [spec](../../match-hit-rename/spec.md)「范围」第 2 条、「验收（草稿）」第 2 条（skill 的冒烟测试）。
- CLAUDE.md「创作 skill」两节：description 的触发词；运行时只对用户暴露业务层。

## Inherited Direction

- 共用执行边界第 1～14 条。
- **description 里的触发词取用户会说出口的词**（CLAUDE.md「description 的触发词」）。例如 diagnose-event 的「为什么没 match」改成「为什么没命中」。防的是：用户改口后，description 里的旧词再也触发不了这个 skill。
- skill 的人话译法表（如 `.claude/skills/tune-gates/SKILL.md` 第三节）里如果列了旧义 match，一并改；hit 是词表里的词，可以照用（CLAUDE.md「用户指令映射」）。
- 统计里的配对（`matched_*` 等）不改代码名（拆分总览「审阅时用户的选择」第 2 条，用户 11-04 定）。防的是：评分口径名写在已冻结的调参记录里，改了复核旧候选时读不出来。

## What to build

- `.claude/skills/` 下所有指 app 产出的 match（第 62 行那处 web-loop 示例归 03）：
  - tune-gates：`SKILL.md`、`reference.md`、脚本、测试、`apps/bb_v1/notes.md`；
  - tune-gates-v3：`SKILL.md`、`references/`、`scripts/`、`tests/`；
  - feature-study：`SKILL.md`、`extract.py`、`run_battery.py`、`apps/*/adapter.py`、测试；
  - diagnose-event：`SKILL.md`、`reference.md`；
  - authoring-path2-app：`SKILL.md`、`reference.md`、`design-heuristics.md`；
  - authoring-path2-detector。
- 测的是 `has_hit` 的测试改名；测试名里「一致」意思的 matches 不动（允许列表）。

## Scope and exclusions

- 不改已经落盘的调参与研究记录（共用执行边界第 7 条）。
- 不改 `path2/GLOSSARY.md` 的行号引用，那是 06 的事。

## Blocked by

02

## Acceptance criteria

- 残留检查：`.claude/skills/` 里旧义 match 为零，留下的按允许列表分类计数，统计配对和「一致」两类单独列出条数。
- skill 自带测试（tune-gates、tune-gates-v3、feature-study、diagnose-event，web-loop 的 node 测试）失败清单与基线相同。
- 冒烟：用一份训练段副本新扫的小 scan，照 diagnose-event 的 `SKILL.md` 入口实跑一次「某个 tb 为什么没命中」的最小流程，读得出 `hits`。输出摘要进 `evidence/04/`。
- `未安排人审：skill 运行时输出里改过的说法读起来顺不顺；原因：没有 build-on point，下次跑 skill 时自然看到，不顺随时改`

## 完成记录

2026-11-04，parallel-tickets ticket-04。合并提交 954cbee（`--no-ff` 合回 `annotation-path2`），测试与审查所在提交 3c98b30；调度分支在本票期间没有前进，合并后的树与 3c98b30 相同。证据都在 `evidence/04/`。

**做了什么**
- `.claude/skills/` 25 个文件，都是逐行替换（132 行改 132 行），所以 `path2/GLOSSARY.md` 的行号引用和别的行号都没动。逐处替换用的是带次数校验的脚本，每条替换次数不符就不写。
- tune-gates（`reference.md`、`apps/bb_v1/notes.md`、`compare_longtable.py`、`edge.py`、`multivar_core.py`、`multivar_scan.py`、三个测试）、tune-gates-v3（`scripts/daily.py`、`tests/test_daily.py`）、feature-study（`SKILL.md`、`extract.py`、两个 `adapter.py`）、diagnose-event（`SKILL.md`、`reference.md`、三个 `detectors/*.md`）、authoring-path2-app（`SKILL.md`、`reference.md`、`design-heuristics.md`）、authoring-path2-detector（`SKILL.md`、`reference.md`）。
- description：diagnose-event 改成「为什么没生成/没命中/confirm 位置」，「何时调」和骨架 A 同步。其他 skill 的 description 里本来就没有旧义 match。
- 运行时输出：`multivar_scan.py` 的报告「有 hit N」「hit 数分布」，`extract.py` 的自检信息「hit 集逐股对齐」「hit 集不对齐」，`multivar_core.py`、`edge.py` 的报错文字。
- 人话译法表（tune-gates `SKILL.md` 第三节、tune-gates-v3 `SKILL.md`）里没有旧义 match，没改。留下的「层匹配随机日基线」「matched baseline」是统计配对。
- 没有测的是 `has_hit` 的测试，所以没有测试要改名。
- 执行细节（没在拆分总览里，都按「派生名」处理）：
  - `compare_longtable.py`：`_engine_keys(matches, out_matches, …)` → `_engine_keys(hits, out_hits, …)`，循环变量 `mm` → `h`；
  - `extract.py`：`mset_fail` → `hit_set_fail`；
  - `test_compare_longtable.py`：`_match(mid, …)` → `_hit(hid, …)`，样例 id `m1～m3` → `h1～h3`；
  - `daily.py`、`test_daily.py`：循环变量 `match` → `hit`；
  - 中文「匹配」在 authoring-path2-app 里有 9 处改成「求解」而不是「命中」（「只显示不参与匹配」→「只显示不参与求解」、「匹配求解」→「求解」、「匹配编排」→「求解编排」等）。理由：这几处说的是 `solve` 开关和求解过程，不是 hit 这个产出，「不参与命中」读不通；票 01 的 `_solve.py`（「求解核心」）和票 02 的 `test_serialize_pk.py`（「不参与求解」）也是这样改的。
  - 留下的 `observe(m, …)`、`for m in res.hits` 里的 `m` 不改，理由见 `review-standards.md`。

**旧 scan 需重扫**（票 02 已写，这里只提醒一点）：`feature-study/apps/bb_v1/adapter.py` 的注释原来点名 `20260908T113225.json` 是「当前配套的 scan」，那份是旧格式，`extract.py` 读不了，注释已改成「配套的 scan 要用现行格式」。新扫 scan 的 `tb.max_day_drop_pct` 核过存在，`PARAM_OVERRIDES` 留空仍然对。

**验收**
- 残留检查（`evidence/01/residual_check.py area .claude/skills --allow evidence/04/allow_04.tsv --detail`，清单 `area_check.txt`）：「未归类」为 0，退出码 0。`allow_04.tsv` 由 `gen_allow.py` 按读过上下文定的规则生成，审查后更正过一次。留下的按行计（一行可算进几类）：
  - 统计里的配对：99（正则认领 71，中文「层匹配」等 28）；
  - 「一致 / 等于」的通用说法：59；
  - 测试框架 211；mismatch 一族 48；web-loop 工作流脚本 41；正则与模式匹配 38；中文「匹配」泛指 23；
  - 归票 03：1（`web-loop/examples/path2.md:62`，本票不动，03 合回后这一行就不在了）。
- skill 自带测试，失败清单与基线相同（都是 0 失败）。基线跑在 3e2637a，改后跑在 3c98b30（`logs/skills-base.log`、`skills-after.log`、`web-loop-base.log`、`web-loop-after.log`，命令见 `run_skills.sh`）：
  - tune-gates 547 通过、13 跳过；tune-gates-v3 156 通过；feature-study 47 通过、2 跳过；diagnose-event 11 通过；
  - web-loop：4 个文件、107 个场景全过。
- 冒烟（`smoke_run.sh`，结果 `smoke_diagnose.txt`）：
  - 用网页的扫描接口新扫一份：`bb_v1`，6 只股票，2022-01-01～2025-12-01，后端端口 8097，读训练段副本。文件 `scan-t04-smoke.json`（sha256 `aa9824611c78054a4a5ea3a241632e92d982eaf3c03fc2760ad3e1e3d4406567`），`data_until` 2025-12-31；
  - 照 diagnose-event 的 `SKILL.md`：步骤 1 用 skill 自带的 `diagnose_env` 从 worktree 找到最新 scan、打出声明；步骤 3 确认不是探索态；步骤 4 从 `reference.md` 原样抠出「骨架 A」的代码块执行；
  - 诊断目标是 AMC 的 `tb_126#0`（在事件里、不在任何 hit 里）。骨架 A 读出 `hits` 1 条、事件 78 条、候选 burst 1 个，并给出结论：`burst_118_121#0` 没过 where（`distinct_pk`=2），所以这个 tb 无主。scan 文件里没有旧键。
- 读 scan 的脚本（`skill_readers.txt`，用票 02 的 `skill_readers.py` 在这份新 scan 上重跑）：feature-study 两道自检门通过，输出新文字「hit 集逐股对齐」；tune-gates `_engine_keys` 读出 8 条 hit，与 scan 文件一致。

**没跑什么、为什么**
- 冒烟没跑骨架 B、C：它们要读 K 线，契约里的写法（`detectors/throwback.md:37`）读 `datasets/pkls`。这两段里只改了说明文字，没有取 hit 键的代码。
- `SKILL.md` 步骤 2「等用户确认声明」只打印、不等，这是冒烟。
- 全套里的 `tests/`、前端测试和 e2e 没跑：本票只改 `.claude/skills/` 和证据，`git diff` 确认没有别的文件；`tests/`、`scripts/`、`path2*` 没有代码引用这个目录（只有 `path2/dag/gate_failure.py`、`path2_web/config.py` 两处注释提到路径）；`tests/` 里有一批测试读 `datasets/pkls`，本票不读。票 06 会在合并后的树上跑全套。
- `tune-gates/test_multivar_equiv.py` 写死读 `datasets/pkls`。本票跑它时用 pytest 插件（`wall/wall_redirect.py`）把目录换成训练段副本，测试文件没改；基线和改后都这样跑，都通过。

**数据墙**
- 跑测试、后端、冒烟都带护栏（`wall/sitecustomize.py`）：任何 Python 进程打开或列 `datasets/pkls` 都被拒绝并记日志。四次记录都是空的，也就是本票没读过 `datasets/pkls`。证据里没有 2026 年的 K 线、hit 或结果（声明里的窗口上限 2026-02-05 只是算出来的边界，行情截到 2025-12-31）。
- 没往共用位置写东西：`datasets/` 只读，`annotations/` 没碰（后端的标注目录是临时目录，机器名 `e2e`），没有请求发往 8001 / 5171，也没占 03 的 8095 / 5195；扫描落在本 worktree 的 `outputs/`，留作证据的那份已提交。没用 Playwright。

**单列：skill 读哪份行情（不在本票范围，只列发现）**
- 读 `datasets/pkls` 的（含 2026 年）：
  - `tune-gates/test_multivar_equiv.py:35`：写死，窗口到 2026 年初之后。票 01、02 的 skill 测试都跑过它，日志里只有通过与否，没有 2026 年的数字。如果要守数据墙，这条要改读副本；
  - `tune-gates`：`holdout.default_data_dir()` 取配置的 `dataset_dir`，`tune.Settings`、`multivar_scan.py`、`edge.py`、`compare_longtable.py`、`stages.py` 都用它（`path2_web/config.py:27` 的注释写明这是设计：旧版调参把完整行情当来源）；
  - `feature-study/fs.py:71` 经 `holdout.default_calendar()` 读它取交易日历（只取日期）；
  - `tune-gates-v3/scripts/run.py:189` 默认 `data_dir` 是它（这个流程本身要用留出数据）；
  - `diagnose-event/detectors/throwback.md:37` 骨架 B 变体。
- 读 scan 记录的目录、新扫 scan 下就是副本的：`feature-study/extract.py:141`。

**单列：改名时碰到的旧问题（不是本票引入）**
- `dropped_matches` 这个键后端早就不产了，diagnose-event 还叫人去看它，改名只会把错指引换个名字。本票删掉了这三处指引（`reference.md` 两处、`detectors/throwback.md` 一处）。前端 `DetailSidebar.vue` 还在读 `dropped_hits`，恒空，票 02 记过，归 03。
- `path2_diag_env.py` 的 `rebuild_params` 写死用 `bottom_burst` 的 `Params`。诊断 `bb_v1` 时会警告「忽略未知字段 `peak_age_min`、`max_day_drop_pct`」，声明里的参数摘要也就少了这两项。这会让用户核对声明时看不全参数，本票没改，建议另起票。

**独立审查**（`review-standards.md`、`review-spec.md`，各附处理；修改在 ff31d4e，之后重跑了 skill 测试与冒烟）
- 已修：删 `dropped_hits` 指引；adapter 注释不再点名旧 scan；`multivar_core.py` 查重断言那三处「命中」改成「触发 / 出现」（否则「至多属于一个 hit（实测零命中）」会读成零 hit）；残留分类把 `test_scoring.py` 两行从统计配对改回「一致」。
- 不改的坏味道：`m` 这个变量名（01、02 都留着，只在这里改会多一种约定）；「cand 为空」代码段和四态回填的重复（改名前就有）。

**改了哪些共享机制**
- 没有接口、JSON 键或落盘记录的格式变化。`_engine_keys` 的形参改名，调用方都是按位置传。
- `multivar_scan.py` 报告和 `extract.py` 自检信息的文字变了，没有代码解析这些文字。
- 已对照未开始的 05、06：没有条文因此变假。06 要改的 `tune-gates-v3` 行号引用，本票没有移动。

`未安排人审：skill 运行时输出里改过的说法读起来顺不顺；原因：没有 build-on point，下次跑 skill 时自然看到，不顺随时改`

## Comments

- 2026-11-04 发布。人审行由拆分时按 `docs/agents/review-planning.md` 的推荐写入，用户在审阅中按推荐批准。
