# skills 的正文、脚本与输出

Status: ready-for-agent
Progress: not-started
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

## Comments

- 2026-11-04 发布。人审行由拆分时按 `docs/agents/review-planning.md` 的推荐写入，用户在审阅中按推荐批准。
