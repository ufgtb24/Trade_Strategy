# path2_web 后端与前后端之间的数据改名

Status: ready-for-agent
Progress: in-progress
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

## Comments

- 2026-11-04 发布。人审行由拆分时按 `docs/agents/review-planning.md` 的推荐写入，用户在审阅中按推荐批准。
