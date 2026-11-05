# 前端内部命名、事件三档 `in_hit` 与界面文字

Status: ready-for-agent
Progress: done
Claimed: 2026-11-04 parallel-tickets ticket-03 @ worktree impl/03-frontend-names-and-tiers
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

## 完成记录

2026-11-04，parallel-tickets ticket-03。合并提交 88810f5（`--no-ff` 合回 `annotation-path2`），分支尖 23968b5；测试跑在 3274f3c（已合入票 04），之后只提交证据，代码与它相同。证据都在 `evidence/03/`。

主视图和标注工具现在说同一套词：第三档叫 `in_hit`，前端指 app 产出的名字和固定文字都是 hit。浏览器里存过的旧值 `matched` 读不懂，退回默认档 `in_hit`（实测，`shots.txt`），没写迁移。

**做了什么**
- 三档：`Level` 取值、`LEVEL_VALUES`、默认档、`RANK`、`render/visible.ts`、`render/colors.ts`、`render/tierTags.ts`、`components/DetailSidebar.vue` 的着色与计数。`render/annotateLanes.ts` 的 `TIER_WORD` 删了，悬停直接用档位值。
- 内部名字：照拆分总览的对照表，含 `{kind: 'hit', hitId}`、CSS 类 `.hit-row` 等。批量替换用 `rename_frontend.py`（只跑一次，之后是手工修改，所以它不能复现最终结果）。
- 测试与 e2e：用例名、断言、夹具 id；`git mv` 成 `e2e/hit-event-disambig.spec.ts`；`miss-detection-walkthrough.spec.ts` 也改了名字，**改了但没跑**（数据墙）。`build_miss_detection_fixture.py` 里只有 `mismatch`，不用改。
- `.claude/skills/web-loop/examples/path2.md` 第 62 行。
- 加了一条 vitest：存的档位值读不懂时退回 `in_hit`。

**改过的固定文字**（`未安排人审` 那行说的就是这些）

| 位置 | 旧 | 新 |
|---|---|---|
| 档位按钮 | `Matched` / `Qualified` / `Detected` | `in_hit` / `qualified` / `detected`，等宽 |
| 档位悬停 | 仅显示命中 match 的事件 等 | 仅显示进了某一次 hit 的事件 等 |
| bracket 轨标题 | `matches` | `hits`，等宽、黑字 |
| 侧栏标题 | 命中匹配 / 匹配 trace | `hits` / `hit_trace`，等宽、黑字，解释在悬停 |
| 侧栏提示 | 点匹配带看 trace | 点 bracket 看 trace |
| 残缺提示 | … 个残缺 match | `⚠ dropped_hits: N`，解释在悬停 |
| 图上悬停 | `Match: …` / `确认: N 个 match 共享此买点` / `归属: match ①` | `hit: …` / `shared_by_hits: N` / `in_hits: ①`，等宽 |
| 扫描进度 | 命中 N | `hit_stocks` N，等宽 |
| 扫描完成 | 完成: 命中 N / 错误 N | `done: hit_stocks N / errors N`，等宽 |
| 停止对话框 | 当前已经命中 N，是否保存？ | `hit_stocks: N`，解释在悬停 |

票面写的「档位下拉」实际是一排按钮，形式和顺序（`in_hit` / `qualified` / `detected`）都没动。

**派生名**（对照表没列的，照同一条规则推出）
- `UnionCell.matched` → `hasHit`，CSS `.matched` → `.has-hit`：这一格说的是「这个 pattern 在这只股票上有 hit」，不是事件第三档，所以不叫 `in_hit`。
- `_previewHits` → `_previewApplies`：它是布尔，意思是 preview 对得上当前股票和 pattern，紧挨着 `pv.analysis.hits` 会读混（票 02 交代的那处，按允许列表「通用的 hit」一行判断）。
- `patternHitCounts` → `patternHitStocks`，`data-testid` `pattern-hit-count` → `pattern-hit-stocks`，`.hit-count` → `.hit-stocks`（审查后加）：它数的是有 hit 的股票数，和 `hit_stocks` 同一格。
- 其余只是把 Match 换成 Hit 的局部名：`eventTierOf` 的 `inHit`、`inHitBtn`、`eInHit`、`inHitIdsJs`、`waitForHits`、`setRealCandidateHits`、`hitsReferencing`、`refHits`、`SHORT_HIT`、夹具 id `hit_A`、`hit_1`、`bo_hit`、`preview_hit_1`。
- 留着的通用 `hit`：`annotation.ts`、`annotateGestures.ts`、`grouping.ts` 里找框、找样本的局部变量，`kline-hit-spanner`。它们和 app 的 hit 不在同一个函数里。
- 单字母循环变量 `m` 没改，理由见 `review-standards.md`。

**验收**
- 残留检查：`residual_check.py area path2_web_ui/src path2_web_ui/tests path2_web_ui/e2e --allow evidence/03/allow_03.tsv --detail`，「未归类」为 0、退出码 0，逐行清单 `area_check.txt`。留下的行按类计（一行可算进几类）：测试框架 45、mismatch 一族 23、中文「匹配」泛指 19、正则与模式匹配 17、「一致 / 等于」10（含参数快照比较的 `match` 字段）、新义 2（compare 下不出现对照 tag 的两个词表）。`TIER_WORD` 已删，全 `path2_web_ui` 里的词 `matched` 只剩那两个词表。
- 测试，基线都跑在 85ec540，改后都跑在 3274f3c：
  - `npx vitest run`：基线 1088 通过、4 失败；改后 1089 通过、4 失败（多的一条是新加的）。失败都在 `components.sidebar-result-list.spec.ts`，清单相同（`logs/vitest-base-failures.txt`、`vitest-after-failures.txt`）；
  - `npx vue-tsc -b`：通过（`logs/vue-tsc.log` 为空）；
  - e2e：按调度会话的约定用票 02 的 spec 清单（`e2e/run_e2e.sh`，只把文件名换成 `hit-event-disambig`），端口 8095 / 5195，配置改动没提交、已复原。36 条逐条状态与基线相同：19 通过、17 失败（`e2e/results-base.txt`、`results-after.txt`）。基线结果也和票 02 的 `results-after.txt` 一字不差；
  - web-loop：4 个文件、107 个场景全过（`logs/web-loop.log`），因为动了它的示例文件。
- e2e 没验到的，要分开看：
  - 没跑的 9 个文件：`miss-detection-walkthrough`（直接读 `datasets/pkls`，数据墙）；`kline-ctrl-wheel-right-anchor`、`marker-click-focus-highlight`、`shift-pair-feedback`、`sidebar-chart-focus`、`subchart-band-zoom`、`subchart-blankclick-yaxis`、`subchart-scroll-drag`、`subchart-tooltip-crosshair`（写死了不在的旧扫描，每条等满 600 秒才失败，票 01、02 同样没跑）。其中 `miss-detection-walkthrough`、`sidebar-chart-focus`、`subchart-blankclick-yaxis`、`subchart-scroll-drag` 本票改过名字；
  - 跑了但基线就失败的：`flow`、`scan-dialog` 卡在开头等 `底部反转突破爆发`，文件里改的名字没被执行到；`hit-event-disambig` 走到了 `setCandidateHits`，然后等不到 `.candidate-banner`（它传的是退役的 `event_id`，票 02 记过）；
  - 补救：`shots.spec.ts` 实际走了档位切换、`.hit-row`、`.hit-trace`、`focusedHitId`、`selected`、扫描进度与完成；`e2e_static_check.py`（结果 `e2e_static_check.txt`）核对全部 spec 用到的 store 成员和类名。它列出 7 个找不到的名字，没有一个是本票改出来的：`annotate-rally-random` 的 4 个是局部变量 `v` 的字段，`selectedEventId`、`focusedEventId`、`pendingDisambigEventId` 在基线的 spec 里就已经不在 store 上了。
- pytest 与 tune-gates、tune-gates-v3、feature-study、diagnose-event 的测试**没跑**：本票不动 Python（`git diff` 确认，只有证据目录里的脚本），`tests/` 里提到 `path2_web_ui` 的只有注释。提到它的两个文件 `test_annotation_grouping_fixture.py`、`test_data_wall.py` 带护栏跑了：29 通过，没有读 `datasets/pkls`。合回后全套由票 06 在合并后的树上跑。
- 截图（`shots.spec.ts`，文字记录 `shots.txt`，Playwright 2560×1440、device scale）。先用网页扫描对话框扫一批 `^[A-C]` 中途停掉丢弃，看进度和停止对话框；再扫这份小 scan，读训练段副本：`bb_v1`，10 只股票，2022-01-01～2025-12-01，`scan-t03-hit-names.json`（sha256 `d810bf4670b4fd7d385516737c0b2c34cc06596b467969fe9d483028f3b275d7`），`hit_stocks` 5、hit 8，没有含 match 的键。
  - `01-level-bar.png`：档位按钮；
  - `02-main-view-in_hit.png`：选 `in_hit` 档的主视图（PLTR，3 条 hit）；
  - `03-bracket-lane-title.png`：bracket 轨标题 `hits`；
  - `04-sidebar-hit-list-focus.png`、`04b-main-view-focused.png`：hit 列表、`hit_trace`，点第 2 行后 `focusedHitId` 和 `selected` 都对上；
  - `05-app-tier-tags.png`、`05b-main-view-detected.png`：app 模式 `detected` 档的 `detected_only`、`qualified_only`；
  - `06-compare-tooltip-in_hit.png`：compare 悬停（`bo_only` + 手写 mapping，AAPL）；
  - `07-scan-progress.png`、`08-stop-dialog.png`、`09-scan-done.png`：扫描面板和停止对话框。
- 修了一处旧缺陷：`annotateLanes.ts` 三处悬停的 `style="font-family:${MONO}"` 被 `MONO` 里的双引号截断，字体一直没生效。验收要求等宽，截图里才看出来，收成 `monoTip`。`render.compare-overlay.spec.ts` 加了断言。`annotation-boxes`、`annotation-brackets` 两处悬停不是本票要求的，同一个缺陷，一起修了。

**数据墙**
- 没跑 `miss-detection-walkthrough` 和它的夹具脚本。
- 最后一轮 e2e 和截图带票 04 的护栏（`evidence/04/wall/sitecustomize.py`）：后端和测试起的后端都在护栏下，记录 0 行（`logs/wall-e2e.txt`），也就是没读过 `datasets/pkls`。
- 基线和前两轮改后的 e2e、截图是在调度会话转告之前跑的，没带护栏；spec 清单和后端代码相同，只能由最后一轮推断它们也没读，不是直接证据。
- 证据里没有 2026 年的 K 线、hit 或结果。scan 段的 `win_end` 2026-02-05 是算出来的窗口边界，行情截到 2025-12-31；截图里的图窗都不超过 2025 年。
- 没往共用位置写东西：`datasets/` 只读，`annotations/` 没碰（后端标注目录是临时目录，机器名 `e2e`），没有请求发往 8001 / 5171。没用 Playwright MCP，`.playwright-mcp/` 没动。扫描落在本 worktree 的 `outputs/`，留作证据的那份已提交。

**独立审查**（`review-standards.md`、`review-spec.md`，各附处理；修改在 9ea1a01，之后重跑了 vitest、vue-tsc、e2e、截图）
- 已修：`patternHitCounts` 一族；固定文字改黑字、等宽、去掉问句（侧栏标题、bracket 轨标题、图上悬停、扫描完成行、停止对话框、残缺提示）；`CandidateStatusBar.vue` 注释改中文；`DetailSidebar.vue` 一处说旧代码的注释；`annotateLanes.ts` 另两处断引号。
- 不改的坏味道（理由都在报告的「处理」节）：`MONO` 两份常量；`.sym` 不复用 `.ann-sym`；循环变量 `m`；`inHitEventIds` 这个别名；`DetailSidebar.vue` 的档位联合类型和 `RANK` 两处。

**单列：碰到的旧问题（不是本票引入，没修）**
- `DetailSidebar.vue` 的 `dropped_hits` 提示恒空：后端早就不产这个键，只改了名字和文字。票 04 把这件事记成归 03，但本票只改名字，删它是另一件事，建议另起票一起删。
- 好几个没实跑的 e2e 还在读退役的 `event_id`（`hit-event-disambig`、`sidebar-chart-focus`、`subchart-scroll-drag`、`subchart-blankclick-yaxis`）和 store 上早已不存在的 `selectedEventId`、`focusedEventId`、`pendingDisambigEventId`。本票照共用执行边界第 4 条不修，只把 `Match` 换成 `Hit`。
- 新浏览器里诊断侧栏默认收着，这是现状；写 e2e 的人要先点开 `panel-toggle-sidebar`。

**改了哪些共享机制**
- view store 对外的名字，也就是 `window.__e2e.view` 上的：`focusedHitId`、`candidateHitIds`、`selectedHitId`、`selectedHit`、`markedHitIds`、`inHitIds`、`inHitEventIds`、`focusHit`、`setCandidateHits`、`patternHitStocks`，`selected` 的结构是 `{kind:'hit',hitId}`。web-loop 的配方如果读这些，示例已同步。
- `level`、`Tier` 的取值变成 `in_hit`，浏览器存的 `path2_web_ui.level` 也是。
- `render/tierTags.ts` 导出 `MONO`。
- 已对照未开始的 05、06：没有条文因此变假。两张票里的 `detected、qualified、in_hit` 与代码一致。现行文档（`docs/path2`、`docs/explain`、`CLAUDE.md`、两份词表、`GLOSSARY-MAP.md`）里没有引用旧的界面文字 `命中匹配`、`匹配 trace`、`Matched` 和这些 store 名字。

`未安排人审：主视图上改过的固定文字（档位按钮、bracket 轨标题、悬停，以及上表其余几处）读起来顺不顺；原因：只是界面文字，没有 build-on point，用起来不顺随时改`

## Comments

- 2026-11-04 发布。人审行由拆分时按 `docs/agents/review-planning.md` 的推荐写入，用户在审阅中按推荐批准。
