# 框架、eval 与 app 的 Python 接口改名

Status: ready-for-agent
Progress: not-started
Blocked by: none

## Purpose

后面各层都从 path2 的 Python 接口拿 app 的产出。本票先把这个源头的名字改成 hit，下游改名就有统一的依据。

## Source

- [spec](../../match-hit-rename/spec.md)「新旧对照」前四行（`PatternMatch`、`AnalysisResult.matches`、`matches()`、`match_forward_*` / `match_first_passage`）、「范围」第 1 条、「验收（草稿）」。
- [决定票 14](../../annotation-path2/issues/14-naming.md)第 2 节 hit 一行。
- 共用执行边界、改名对照、允许列表：[拆分总览](../ticket-breakdown.md)。

## Inherited Direction

- 共用执行边界第 1～14 条。
- `matches(spec, df, params)` 返回 bool，改名 `has_hit`，不是 `hits`。`hits` 留给「一组 hit」这个名词（spec 表）。
- 只改名，不改行为。防的是：改名混进行为变化，验收分不清是哪一样造成的。

## What to build

- `path2/` 全部（不含 `path2/GLOSSARY.md`，那是 06 的）：
  - `PatternMatch` → `PatternHit`；
  - `AnalysisResult.matches` → `hits`；
  - 字段 `match_id` → `hit_id`；
  - `matches()` → `has_hit`（`path2/dag/engine.py`、`path2/stdlib/app.py`）；
  - `path2/eval.py` 三个函数 → `hit_forward_returns`、`hit_forward_drawdowns`、`hit_first_passage`；
  - 包导出（`path2/dag/__init__.py` 等），以及内部局部名、注释、docstring。
- `path2_apps/` 全部 app（`bb_v1`、`bo_only`、`bottom_burst`、`new_step`、`try_conplex_where`）和 `path2_apps/__init__.py`：
  - `make_app` 装配的入口三件套里，`matches` 改为 `has_hit`；
  - 注释与 docstring。
- 脚本：`scripts/path2/*.py`、`scripts/path2_eval_bottom_burst.py`、`scripts/gate_burst_2x2.py` 里的 Python 名字和注释（读 JSON 键的字面量归 02）。
- 测试：`tests/path2`、`tests/path2_apps`、`tests/path2_dev`，含两个改名的测试文件。
- 别处的调用点：`path2_web/*.py`、`.claude/skills/**/*.py`、`path2_web_ui/e2e/fixtures/build_miss_detection_fixture.py` 里访问上述接口的表达式（import、属性、函数名）改成新名。这些文件的局部变量、注释和 JSON 键不动，分别归 02、04。
- 写残留检查脚本放进 `evidence/01/`（共用执行边界第 11 条）。

## Scope and exclusions

- 不改 scan 文件和 HTTP 返回的键：`serialize` 照旧写 `"matches"`、`"match_id"`，由 02 一起改。
- 不改 `path2_web` 的内部名字、skill 的正文、文档和词表。

## Blocked by

none

## Acceptance criteria

- 残留检查：`path2/`（不含词表）、`path2_apps/`、上面三类脚本、`tests/path2*`、`tests/path2_apps` 里，旧义 match 为零，留下的按允许列表分类计数。
- 全仓 Python 里不再出现 `PatternMatch`、`match_forward_returns`、`match_forward_drawdowns`、`match_first_passage`、`.matches` 属性访问、`match_id` 属性访问。JSON 键字面量 `"matches"`、`"match_id"` 除外，列出清单留给 02。
- 只改名、没改行为：
  - 每个现役 app 挑 2～3 只股票，经 `path2_web/data.py` 的读数函数读训练段副本；
  - 改名前后各跑一遍 `analyze`，逐个比较每个 hit 的 node 绑定、`hit_id`、买点日和 `hit_forward_returns` 的数值，全部相同；
  - 对照脚本和结果进 `evidence/01/`。
- 测试全套（共用执行边界第 4 条）的失败清单与基线相同。
- 无人审：全部可机检。

## Comments

- 2026-11-04 发布。人审行由拆分时按 `docs/agents/review-planning.md` 的推荐写入，用户在审阅中按推荐批准。
