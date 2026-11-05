# 前端内部命名、事件三档 `in_hit` 与界面文字

Status: ready-for-agent
Progress: not-started
Blocked by: 02

## Purpose

主视图和标注工具说同一套词。本票把前端所有指 app 产出的名字和固定文字换成 hit，事件第三档改叫 `in_hit`。

## Source

- [spec](../../match-hit-rename/spec.md)「新旧对照」第 1 行（界面）、第 5 行（三档 → `in_hit`）、「验收（草稿）」第 2 条。
- 用户 2026-11-04 的决定（本文件开头）。
- `.scratch/annotation-path2/spec.md` 4.3「事件三档是 detected / qualified / `in_hit`」。
- `~/.claude/rules/ui-text-style.md`。

## Inherited Direction

- 共用执行边界第 1～14 条。
- **第三档就叫 `in_hit`**（用户 11-04 定），主视图和标注工具用同一个词。标注工具悬停用的 `TIER_WORD` 不再需要把 `matched` 转成 `in_hit`，收成直接用档位值。
- **界面固定文字**照 `~/.claude/rules/ui-text-style.md`：英文标识符风格、等宽字体；解释放进悬停提示。档位下拉写 `in_hit`。
- 浏览器里存过的旧档位值 `matched` 读不懂时退回默认档，现有代码本来就这样做，不写迁移。
- **前端不认事件类型**（CLAUDE.md 代码地图的边界红线）：只改名字。

## What to build

- 三档：
  - `Level` 类型与取值（`types.ts`、`stores/view.ts` 的 `LEVEL_VALUES` 和默认值）；
  - `render/visible.ts`、`render/colors.ts`、`render/tierTags.ts`、`render/annotateLanes.ts`；
  - `components/DetailSidebar.vue` 的档位着色与计数；
  - `components/ChartArea.vue` 的 `LEVEL_OPTIONS`：值、标签、悬停。
- 内部名字：照「改名对照」表 03 的几行，以及 CSS 类名、`data-testid`、图表系列名、bracket 轨标题里的旧义 match。
- 测试与 e2e：用例描述、断言里的名字，`e2e/match-event-disambig.spec.ts` 改名。
- `.claude/skills/web-loop/examples/path2.md` 第 62 行。它写的是 view store 里的选中项结构，随本票同步。
- 前端里指 app 产出的中文「匹配」（共用执行边界第 12 条）。

## Scope and exclusions

- 不动后端和 JSON 键（02 已改）。
- 新义的 `match tag`、`matched` / `unmatched` 保留，包括 e2e 里断言「compare 下不出现对照 tag」的词表。
- 不修基线上就失败的主视图 e2e（共用执行边界第 4 条）。

## Blocked by

02

## Acceptance criteria

- 残留检查：`path2_web_ui/src`、`tests`、`e2e` 里旧义 match 为零，`TIER_WORD` 里没有 `matched`。
- `npx vitest run`、`npx vue-tsc -b`、`npx playwright test` 的失败清单与基线相同。
- 截图自查：在本 worktree 用训练段副本扫一份小 scan（02 的 scan 不跟过来）。截这几张：
  - 档位下拉显示 `detected` / `qualified` / `in_hit`；
  - 选 `in_hit` 档的主视图；
  - bracket 轨标题；
  - 诊断侧栏的 hit 列表与聚焦；
  - app 模式副图的 tier tag；
  - compare 模式悬停里的 `in_hit`。
  - 截图进 `evidence/03/`。
- `未安排人审：主视图上改过的固定文字（档位下拉、bracket 轨标题、悬停）读起来顺不顺；原因：只是界面文字，没有 build-on point，用起来不顺随时改`

## Comments

- 2026-11-04 发布。人审行由拆分时按 `docs/agents/review-planning.md` 的推荐写入，用户在审阅中按推荐批准。
