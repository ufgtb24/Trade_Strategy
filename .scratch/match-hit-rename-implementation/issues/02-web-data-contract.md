# path2_web 后端与前后端之间的数据改名

Status: ready-for-agent
Progress: done
Claimed: 2026-11-04 parallel-tickets ticket-02 @ worktree impl/02-web-data-contract
Blocked by: 01

## Purpose

scan 文件和网页后端返回的数据，是前端、skill 和脚本读 app 产出的共同入口。本票把这层数据的键改成 hit，并让所有读它的代码一起换过来，新扫的结果在主视图里照常可用。

## Source

- [spec](../../match-hit-rename/spec.md)「新旧对照」第 2 行（`AnalysisResult.matches` 及序列化后的 JSON 键、`_match_to_dict`）、第 6 行（扫描进度的 `hits` → `hit_stocks`）、「不改」第 1 条、「验收（草稿）」第 2 条。
- 共用执行边界、改名对照、允许列表：[拆分总览](../ticket-breakdown.md)。

## Inherited Direction

- 共用执行边界第 1～14 条。
- **先改 `hits` → `hit_stocks`，再改 `matches` → `hits`**（spec 表）。防的是：两个 `hits` 同时存在，读的一方拿错意思。
  - 要改的是数「有 hit 的股票数」的那几处：进度事件、scan 文件的 `scan.hits`、扫描列表行的 `hits`、前端 `ScanProgress` / `ScanMeta` / 完成事件 / `StopScanDialog` 的属性。
  - `per_pattern` 里数 hit 个数之和的 `hits` 本来就是新义，不动。
  - 逐处看它数的是股票还是 hit，按这条分。
- **后端只做投影**（CLAUDE.md 代码地图的边界红线）：本票只改名字，不改投影逻辑。
- 参数快照比较返回的 `match` 字段（意思是「一致」）不改（拆分总览「审阅时用户的选择」第 2 条，用户 11-04 定：代码内部名不动）。

## What to build

- `path2_web/*.py`（不含 `path2_web/GLOSSARY.md`）的全部旧义 match：
  - `serialize.py`：`_match_to_dict`，`analysis.matches`、`match_id`、`summary.matches`、`match_fp_counts`、`dropped_matches` 等键；
  - `scan.py`：`any_match`、`match_windows`、`per_leaf_match_count_distribution`，以及 scan 段的 `hits`；
  - `eval_runner.py`：`target_matches` 等；
  - `api.py`：进度事件、注释里的「match 级」。
- `tests/path2_web` 全部，含改名的测试文件。
- 前端的数据契约：
  - `path2_web_ui/src/types.ts`：`MatchDict` → `HitDict` 及各字段；
  - `path2_web_ui/src/api.ts`；
  - 前端各处取这些字段的地方，以 `vue-tsc` 报错为准，只改取字段的表达式，局部名留给 03；
  - 前端测试夹具 `path2_web_ui/tests/fixtures/apcx-instance-id-acceptance.json`（只换键、不动值，或者重新生成，二选一，完成记录写明）；
  - `path2_web_ui/e2e/fixtures/build_miss_detection_fixture.py`。
- 其他读 scan 文件或后端 JSON 的代码，只改键的字面量和直接相关的取值：`.claude/skills/feature-study/extract.py`、`.claude/skills/tune-gates/compare_longtable.py`、`.claude/skills/diagnose-event/path2_diag_env.py`（如有读键）、`scripts/path2/path2_eval_scan.py`。

## Scope and exclusions

- 前端内部名字（`focusedMatchId` 等）、三档 `matched`、界面固定文字归 03。
- skill 的正文和内部名字归 04。

## Blocked by

01

## Acceptance criteria

- 残留检查：`path2_web/*.py`、`tests/path2_web` 里旧义 match 为零。全仓代码里不再有 `"matches"`、`"match_id"`、`match_fp_counts`、`match_windows`、`dropped_matches`、`target_matches` 这些键。前端 `types.ts` 里没有 `matches`、`match_id`、`MatchDict`。
- 测试全套的失败清单与基线相同。
- 在 worktree 里用网页的扫描新扫一份小 scan：几只股票、一个现役 app，读训练段副本（共用执行边界第 5 条）。然后：
  - 用脚本检查这份 scan：有 `hits`、`hit_id`、`hit_stocks`，没有任何旧键；
  - 打开主视图：hit 列表、bracket、诊断侧栏的命中留痕都正常；扫描进度和完成数显示的是有 hit 的股票数；
  - 截图进 `evidence/02/`。
- 读 scan 的 skill 脚本在这份新 scan 上能读出 hits：feature-study 的对齐自检、tune-gates 的长表比对、diagnose-event 的环境探测。有测试覆盖读键的走测试，没有的就实跑一次最小读取，完成记录写明各走的哪条。
- 完成记录写一句「旧 scan 需重扫」。
- 无人审：全部可机检。

## 完成记录

2026-11-04，parallel-tickets ticket-02。合并提交 84a76cc（`--no-ff` 合回 `annotation-path2`），测试与审查所在提交 f308c94；调度分支在本票期间没有前进，合并后的树与 f308c94 相同。证据都在 `evidence/02/`。

**旧 scan 需重扫。** scan 文件和后端 JSON 的键都改了，没写迁移和双读。旧文件在主视图里读不出 hit。

**做了什么**
- 先改 `hits` → `hit_stocks`（提交 b8b8ed7），再改 `matches` → `hits`（fe98c3b、38d8b8c）。两步之间全套测试与基线相同。
  - 改成 `hit_stocks` 的：进度事件、完成事件、scan 文件的 `scan.hits`、扫描列表行、前端 `ScanProgress` / `ScanMeta` / 完成事件 / 列表行；`StopScanDialog` 的 prop 改成 `hitStocks`。
  - 没动的：`per_pattern` 里的 `hits`，它数的是 hit 个数之和。
- `path2_web/*.py`：
  - 键：`_hit_to_dict`、`analysis.hits`、`summary.hits`、`hit_id`、`hit_fp_counts`、`any_hit`、`hit_windows`、`per_leaf_hit_count_distribution`、`target_hits`；
  - 注释、docstring 里的旧义 match 和「匹配」一并改；
  - 投影逻辑没动。
- `tests/path2_web` 全部，`test_serialize_match_fp.py` 用 `git mv` 改成 `test_serialize_hit_fp.py`。
- 前端数据契约：
  - `types.ts`：`HitDict`、`hits`、`hit_id`，这几个接口上的注释也改了；
  - `MatchDict`、`match_id` 全 `path2_web_ui` 换掉，含 bracket 图表数据点上的 `hit_id`；
  - src 里 analysis、summary 上的取字段表达式；
  - `dropped_matches` → `dropped_hits`；
  - vitest 与 e2e 的夹具、取值；
  - 局部名、`CandidateStatusBar` 的 prop `matches`、`ChartInput.matches`、tooltip 的 `ctx.matches`、`focusedMatchId`、三档 `matched`、界面文字都留给 03。
- `tests/fixtures/apcx-instance-id-acceptance.json`：只换键、不动值，没重新生成。脚本核对过，文本替换后的 JSON 与按键映射的树完全相同。它的 scan 段本来就没有 `hits`。
- `build_miss_detection_fixture.py`：`hit_stocks`、`summary.hits`，docstring 跟上。
- 其他读键的代码，只改键和直接相关的取值：
  - `feature-study/extract.py`；
  - `tune-gates/compare_longtable.py`、`test_compare_longtable.py`、`test_multivar_equiv.py`；
  - `scripts/path2/path2_eval_scan.py`、`scan-wide.py`；
  - `diagnose-event/path2_diag_env.py` 不读这些键，没动。
- 修了票 01 留下的一处坏代码：`KlineChart.vue` 调试脚本模板里生成的 `result.matches`，01 改完 Python 接口后这段脚本已经跑不通，改成 `result.hits`。
- 中文「匹配」：`path2_web` 与 `tests/path2_web` 里指 app 产出的改了；`test_serialize_pk.py` 的「不参与匹配」改成「不参与求解」。留下两处泛指：`stock_pool.py` 的正则、`test_diagnose_time.py` 的 node_id 相等。

**派生名**（执行细节，照拆分总览的规则推出；后两项是审查后加的）
- `hc`、`hfp`（`scan.py` 里原来的 `mc`、`mfp`）；
- `n_hits`（miss-detection 夹具）；
- 测试辅助 `_pick_pkl_with_hit`、`per_hit`；
- `tickers_hit` → `hit_stocks`、`universe_hit_tickers` → `universe_hit_stocks`（`eval_runner.py`、两个脚本的打印、`test_eval_runner.py`）：
  - 拆分总览没列它们。独立审查指出，有了 `hit_stocks` 后它们和它是同一格的两个名字，违反 `GLOSSARY-MAP.md` 命名规则第 2 条；
  - 评估 JSON 的 `meta` 里有这个键。`run_regress` 读旧评估文件时只取窗口、horizon、`end_node`、缓冲、`module_path` 和 `results`，不读它，所以不影响复核旧文件。

**验收**
- 残留检查（`evidence/01/residual_check.py`）：
  - `area path2_web tests/path2_web --exclude path2_web/GLOSSARY.md --allow evidence/02/allow_02.tsv --detail`：「未归类」为 0，逐行清单见 `area_check.txt`。留下的行按类计（一行可算进几类）：正则与模式匹配 20、测试框架 5、mismatch 一族 4、「一致 / 等于」13（含参数快照比较的 `match` 字段）、中文泛指 2。
  - `api`：JSON 键字面量 0，清单见 `api_check.txt`。
  - `key_grep.sh`（结果 `key_grep.txt`）：范围内代码文件里没有 `"matches"`、`match_id`、`match_fp_counts`、`match_windows`、`dropped_matches`、`target_matches`、`any_match`、`per_leaf_match`、`_match_to_dict`、`MatchDict`；`types.ts` 没有 `matches`、`match_id`、`MatchDict`。
  - 还留在正文里、归后续票的：`.claude/skills/diagnose-event/detectors/throwback.md`、`diagnose-event/reference.md`、`tune-gates/reference.md`（04），`docs/explain/path2_漏检分析_v1_v2_脉络.md`（05）。
- 单列，没改：`.scratch/annotation-path2/scripts/01-dump-proto-data.py:68` 还读 `ana["matches"]`。票 01 单列过同一个文件：已 resolved 的决定票的原型取数脚本，属历史资产，本来就跑不起来。
- 测试全套。基线是 cc46e73，它与 fe36381 除票据外没有差别（`git diff` 为空），所以 pytest、skill、e2e 的基线用票 01 的改名后结果；vitest 另跑了一次。改名后都在 f308c94：
  - `.venv/bin/python -m pytest tests/path2 tests/path2_apps tests/path2_web tests/scripts -q`（`logs/pytest-after.log`）：1229 通过、2 跳过、6 失败，失败清单与基线相同（`test_throwback_v4.py` 4 条、`test_self_contained.py`、`test_serialize_tbseg.py`）；
  - skill（`logs/skills-after.log`）：tune-gates 547 通过、13 跳过；tune-gates-v3 156 通过；feature-study 47 通过、2 跳过；diagnose-event 11 通过；与基线相同；
  - web-loop（`logs/web-loop.log`）：4 个文件、107 个场景全过；
  - `npx vitest run`（`logs/vitest-base-failures.txt`、`vitest-after-failures.txt`）：1088 通过、4 失败，都在 `components.sidebar-result-list.spec.ts`，清单与基线相同；
  - `npx vue-tsc -b`（`logs/vue-tsc.log`）：通过。
  - e2e：`e2e/run_e2e.sh`，端口 8095 / 5195，配置改动没提交、已复原。36 条逐条与票 01 改名后的结果相同（`e2e/results-after.txt`）：19 通过、17 失败，都是基线就失败的。这次跑在 c688066；之后的审查修改只碰 `eval_runner.py`、两个脚本的打印、`test_eval_runner.py` 和一行注释，e2e 不经过它们，没重跑。
  - e2e 没跑的：
    - 票 01 没跑的 8 个文件，理由相同：写死了不在的旧扫描，每条等满 600 秒才失败。其中 `sidebar-chart-focus`、`subchart-blankclick-yaxis`、`subchart-scroll-drag` 本票改过键，这三处没有实跑验证，只核对过改的都是 `effectiveAnalysis` 上的取值；
    - `miss-detection-walkthrough`：见下面「数据墙」。票 01 的基线里它是 1 失败 4 跳过。
- 新扫 scan：网页扫描对话框，`bb_v1`，10 只股票，2022-01-01～2025-12-01，读训练段副本。文件存成 `scan-t02-hit-rename-d.json`（sha256 `8aa53d9a90ec95c20434a590b6072de3ed86c2b30a8585281520cec8977b997c`），`data_until` 2025-12-31，最晚买点日 2025-05-30。
  - 脚本检查（`check_scan_keys.py`，结果 `scan_keys.txt`）：有 `hits`、`hit_id`、`hit_stocks`、`hit_fp_counts`，含 match 字样的键为空；`hit_stocks` = 5 等于有 hit 的股票数，与 hit 总数 8 分得开。
  - 主视图（Playwright，2560×1440，`scale=device`）：
    - `01-scan-history.png`：历史列表 `bb_v1` 显示 8（per_pattern 的 hit 数）；
    - `02-main-view-hit.png`：PLTR 的 3 条 hit 列表、bracket ①②③、侧栏的 trace 都正常；点 bracket ① 选中列表第 1 条，`hit_id` 对得上；
    - `03-stop-dialog.png`：扫描中点停止，对话框「当前已经命中 9」跟着进度涨，`hitStocks` 接通了；
    - `04-scan-done.png`：完成数显示「命中 5 / 错误 0」。
  - 进度事件原文（`scan_progress_events.txt`）：`hit_stocks` 逐只累加，完成事件也是它。
- 读 scan 的 skill 脚本（`skill_readers.py`，结果 `skill_readers.txt`），都实跑了这份新 scan：
  - feature-study：`build_dataset` 两道自检门通过，8 例 label 全部 <1e-12；
  - tune-gates：`_engine_keys` 读出 8 条，`hit_id` 集合、`hit_fp_counts` 都与 scan 文件一致；另有 `test_compare_longtable.py`、`test_multivar_equiv.py` 走测试；
  - diagnose-event：`diagnose_env` 探测到 `bb_v1`，它不读 hit 的键；
  - `path2_eval_scan.py` 的打印键没实跑（它默认读 `datasets/pkls`），`test_eval_runner.py` 断言了同名键，脚本过了 `py_compile`。
- miss-detection 夹具：临时复制一份，把数据目录换成训练段副本、截到 2025-12-31、股票换成 DGNX 和 AMC（副本里没有 LIXT）跑了一次，产出有 `hit_stocks`、`hit_fp_counts`、`summary.hits`、`analysis.hits`。副本没入库。
- 数据墙：本票的扫描、预览、skill 实跑都只读训练段副本，没读 `datasets/pkls`；证据里没有 2026 年的 K 线、hit 或结果（scan 段的 `win_end` 2026-02-05 只是算出来的窗口边界，行情截到 2025-12-31）。
- 没往共用位置写东西：`datasets/` 只读，`annotations/` 没碰，e2e 与验收后端的标注目录是临时目录，机器名 `e2e`，没有请求发往 8001 / 5171。Playwright MCP 只能写主目录的 `.playwright-mcp/`：截图已挪进证据，自己的两个临时文件已删，那里 11-03 的旧日志不是本票的，没动。

**单列：数据墙相关的旧问题（不是本票引入）**
- `path2_web_ui/e2e/fixtures/build_miss_detection_fixture.py` 直接读 `datasets/pkls/<股票>.pkl`，窗口到 2026-04-20；`miss-detection-walkthrough.spec.ts:276` 也读 `datasets/pkls/DGNX.pkl`。跑这个 spec 就越过共用执行边界第 5 条，所以本票没跑。
- 票 01 的 e2e 跑过这个 spec，它完成记录里「没读 `datasets/pkls`」这句不准确。按当时的日志，产物是一份写进它 worktree `outputs/` 的 scan（该 worktree 已删），证据里只有测试名，没有 2026 年的数字；票 01 已关闭，不改它。
- 本票只改了夹具的键。让它改读训练段副本是另一件事，不在本批范围，建议另起票（LIXT 不在副本里，要换股票或改用例）。

**独立审查**（`review-standards.md`、`review-spec.md`，各附处理；修改在 f308c94）
- 已修：`tickers_hit` 一族；`eval_runner.py` 续行对齐；`match-event-disambig.spec.ts` 注释误写的 `props.hits` 改回 `props.matches`；证据脚本没用的参数；过时的 `key_grep.txt` 重新生成；补 vitest、vue-tsc 改后日志。
- 不改（理由都在报告的「处理」节）：
  - 坏味道：`target_hits` 是布尔（对照表定的名字）；`KlineChart.vue:171` 的局部名 `hits`（归 03）；`summary.hits` 与 `analysis.hits` 同名（spec 表）；`DetailSidebar.vue:373` 说 `dropped_hits` 已进 `AnalysisResult` 的注释（之前就不准，这段读取恒空）；`scan.py:80-81` 过时的行号引用；`serialize.py` 的 `m_counts`（跟循环变量 `m` 走）。
  - 规范违反里转给 03 的一条：见下面「给后续票」的 `event_id`。

**改了哪些共享机制**
- scan 文件与 HTTP 返回的键：`analysis.hits`、`summary.hits`、`hit_id`、`hit_fp_counts`、`dropped_hits`、`per_leaf_hit_count_distribution`、`scan.hit_stocks`，扫描列表行与进度、完成事件的 `hit_stocks`。
- 评估 JSON：`hit_windows`、`hit_stocks`、`target_hits`、`universe_hit_stocks`。
- 前端类型 `HitDict`、`Analysis.hits`，`StopScanDialog` 的 prop `hitStocks`。
- 已对照未开始的 03～06：没有条文因此变假。

**给后续票**
- 03：
  - e2e 用 `evidence/02/e2e/run_e2e.sh` 的 spec 清单，别跑 `miss-detection-walkthrough`（数据墙）；
  - `match-event-disambig.spec.ts`、`sidebar-chart-focus.spec.ts`、`subchart-scroll-drag.spec.ts` 还在读 hit 的 `event_id`，这个键早已退役。disambig 三条在基线上就失败（找不到 `.candidate-banner`），很可能就是这个原因，没有单独验证；共用执行边界第 4 条写明本批不修，这里只交代；
  - `stores/view.ts:473` 的 `_previewHits` 是布尔，意思是「preview 对得上当前股票」，紧挨着 `pv.analysis.hits`，按允许列表「通用的 hit」那行判断要不要改；
  - `KlineChart.vue:171` 的 `hits: packHits(a.hits…)`、`SidebarScanPanel.vue` 与 `StopScanDialog.vue` 的「命中」文字（现在数的是股票）都在 03 的范围。
  - 主视图默认全选 pattern 时，`try_complex_where` 每只股票都报错，整次扫描显示「错误 N」、一只也不入选。这是它改名前就有的问题（票 01 记过），e2e 和手工验收要记得只勾现役 app。
- 04：`extract.py`、`compare_longtable.py` 只改了键，局部名（`matches`、`out_matches`）和说明文字（「match 集对齐」）原样留着；skill 的 `.md` 里还有旧键，见上面的清单。
- 新格式样例：`evidence/02/scan-t02-hit-rename-d.json`。

## Comments

- 2026-11-04 发布。人审行由拆分时按 `docs/agents/review-planning.md` 的推荐写入，用户在审阅中按推荐批准。
