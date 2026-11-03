# 直达链接：「股票 + 日期」与「样本编号」（M14）

Status: ready-for-agent
Progress: done
Claimed: 2026-11-03 parallel-tickets ticket-09 @ worktree impl/09-direct-links
Blocked by: 06

## Purpose

用户在对话里说一只股票和一个日期，或者会话要指给用户看某个样本时，用户点一个链接就能落到那张图上去标或者看。

## Source

- [spec](../annotation-path2/spec.md) 的这几处：5.3「链接」；5.2「模式切换」；用户故事 4。
- 说明书报告 M14。
- 前置交付：[06](06-samples-and-members.md)。

## Inherited Direction

- 共用执行边界。
- 日期晚于 2025-12-31 的，一律截到 2025-12-31（spec 5.3）。
- 从链接进来落在 `annotate`（spec 5.2）。
- 「按编号找样本」的逻辑，第二段的题目链接 `#q=` 也要用（spec 5.3），所以做成单独一处、可以直接调用。

## What to build

- 两种链接的格式，照现有路由的风格，由执行者定。定下的格式写进完成记录和模块文档，会话照它生成链接。
- **股票 + 日期**：打开那只股票，图窗停在那天附近。
- **样本编号**：打开样本所在的那张图，并选中它。编号不存在时明确提示。

## Blocked by

06

## Acceptance criteria

- e2e 验以下几种：
  - 「股票 + 日期」链接打开的是对的股票和日期，并且落在 `annotate`；
  - 日期写 2026-03-01 的链接，最后一根 K 线不晚于 2025-12-31；
  - 「样本编号」链接选中了对应的样本；
  - 不存在的编号有明确提示。
- 无人审：全部可机检。

## 完成记录

2026-11-03，parallel-tickets ticket-09。合并提交 335df17（`--no-ff` 合回 `annotation-path2`）。测试、审查修改与证据所在提交 ff4fce8；认领以来调度分支没有前进，合并后的树与它相同。

**定下的链接格式**（会话照它生成链接；模块文档在 `path2_web_ui/src/annotate/directLinks.ts` 开头）
- 前端地址是 `http://localhost:<configs/path2_web.yaml 的 frontend_port>`，现在是 5171。
- 股票 + 日期：`http://localhost:5171/#symbol=AAPL&date=2024-05-10`
- 样本编号：`http://localhost:5171/#sample=s-pc-12`。编号就是标注文件里样本的 id。
- 都写在 `#` 后面，键值照后端路由的查询串写法；第二段的 `#q=` 也写在 `#` 后面。
- 代码照顶栏输入的规则去空白、转大写；日期写 YYYY-MM-DD，而且必须是存在的一天。

**做了什么**
- 跟链接：页面打开时跟一次，地址的 `#` 部分变了再跟一次（`App.vue` 监听 `hashchange`）。跟完把 `#` 部分从地址里去掉。
  - **股票 + 日期**：
    - 先对股票列表核代码。在列表里就打开那只股票，落在 `annotate`。图窗从那天往前 180 个日历日、往后 60 个日历日，大约前 124 根、后 41 根。晚于 2025-12-31 的日期先截到 2025-12-31。
    - 不在列表里：提示条写 `url symbol <代码> not_found`，当前的图不动。
    - 列表拿不到：交给后端判，和顶栏一样。
  - **样本编号**：
    - 等标注读完，按编号打开样本所在的图，选中它，侧栏翻到 `selection`。图窗和 pattern 页的样本卡一样：样本的跨度前后各留约两个月。
    - 不换顶栏的当前 pattern，和 06 的做法一样。
    - 编号不存在：提示条写 `url sample <编号> not_found`。
    - 标注读不到：提示条里已经有 `annotations unavailable` 或 `load_failed`，不另外报。
  - **认不出的写法**：提示条写 `url bad_url`，悬停能看到原文和两种格式。
  - 跟没跟成，最后都落在 `annotate`。提示条一直显示，直到点 `ok` 或下一个链接跟成。
- 按编号找样本：标注 store 的 `openSample(id, {keepTab})`，找不到返回 false。样本链接和 pattern 页的样本卡都走它，样本卡的行为不变。第二段的题目链接 `#q=` 可以直接调它。
- 代码位置：
  - 纯函数在 `annotate/directLinks.ts`：解析、图窗，还有前端的 `TRAIN_END`。`TRAIN_END` 有单测读 `path2_web/data.py`，核对两边同值。
  - 跟链接在 `stores/directLinks.ts`；提示条在 `AnnotationNotices.vue`。
  - 视图 store 加了 `enterAnnotate()`：切到 annotate，图不换。
  - `shiftDays` 从 `grouping.ts` 挪到 `annotate/viewWindow.ts` 并导出，两处共用。

**实现上的选择**（都由测试守着；只有用户判断得了的，写在末尾的「未安排人审」里）
- **写在 `#` 后面，不用查询串**：不经过后端；同一页里换链接不刷新页面；第二段的 `#q=` 也是这种写法。
- **跟完去掉 `#` 部分**：同一个链接在这一页再点一次照样会跟，刷新也不会把图拉回链接那里。代价是刚跟完就刷新的话，回到空图。
- **认不出的写法也给提示**（`bad_url`）。票只要求编号不存在时提示。
- **名字避开词表的 `link tag`**（`path2_web/GLOSSARY.md:50`，第二段 compare 里「相邻两段 app 连没连上」）：提示条的键叫 `url`，代码模块叫 directLinks。
- **图窗数值是 detail**：往前 180、往后 60 个日历日，和大涨段清单的图窗长度相近（涨前往前 120 根，观察期最多 40 根）。往前多留，是因为样本的依据都在样本日之前。
- **按编号打开样本不换当前 pattern**：样本属于别的 pattern 时，三角和 bracket 画淡、不带字母（06 的规则），选中、暗一档、样本页都照常。审查前一度会换成样本所在的 pattern；审查指出这样之后新放的样本会悄悄改归别的 pattern，而且和 06 的做法相反，已撤回。

**验收**
- e2e：`path2_web_ui/e2e/annotate-direct-links.spec.ts`，2 条，在 2560×1440 下跑，都过。
  - 第 1 条：
    - 新开的页带 `#symbol=msft&date=2024-05-10`：打开 MSFT，落在 `annotate`。看得见的那段含 2024-05-10，并在 2023-11-12～2024-07-09 之内。地址的 `#` 部分已去掉。
    - 页面切到 `app` 后，把 `#` 部分改成 `#symbol=AAPL&date=2026-03-01`：落在 `annotate`。看得见的最后一根就是图上的最后一根，不晚于 2025-12-31；第一根不早于 2025-07-04。
    - 再改成股票列表里没有的代码：提示条写 `symbol NOSUCH9 not_found`，图不动。
  - 第 2 条：
    - 新开的页带 MSFT 2024-02-08 那个样本的编号：等标注读完，打开 MSFT 并选中它。它是当前样本，侧栏在 `selection`，当前 pattern 不变，样本日在看得见的那段里。
    - 改成 NVDA 那个样本的编号：换图并选中它。
    - 改成 `s-pc-999`：提示条写 `sample s-pc-999 not_found`，图不动；点 `ok` 收起。
    - 认不出的写法 `#symbol=AAPL`：提示 `bad_url`，悬停有原文。
    - 另开一页带不存在的编号：同样提示。
  - 标注用固定的例子 `tests/path2_web/fixtures/annotation_grouping_v1`，由测试自己起的后端读，标注目录在系统临时目录。主目录的 `annotations/` 跑完仍是空的。
- 单测：
  - `annotate.direct-links.spec.ts`，8 条：解析、认不出的写法、图窗、截到 2025-12-31，以及前端 `TRAIN_END` 与后端同值。
  - `stores.direct-links.spec.ts`，10 条，覆盖：
    - 两种链接；代码不在列表里；列表拿不到；
    - 等标注读完再找；编号不存在；标注读不到；
    - 样本卡的 `keepTab`；`bad_url`；没有 `#` 部分。
- 截图自查：截图在 `evidence/09/01`～`04`。
  - 提示条沿用 05 的样式：黑色粗边框、白底。`url`、`symbol` / `sample`、编号用等宽字体，`not_found` / `bad_url` 加粗。文字全黑，没有新颜色。
  - `03`：样本链接打开 MSFT 的 W底 样本。当前 pattern 是 unsorted，所以三角画淡、不带字母；样本页、成员框加粗、暗一档都照常。
- 测试结果：
  - `npx vitest run`（在 af1031a 上，代码与 ff4fce8 相同）：1044 个通过，4 个失败。失败的都在 `components.sidebar-result-list.spec.ts`，票 04～07 记过，基线上就失败。
  - `npx vue-tsc -b` 通过。
  - `python -m pytest tests/path2_web tests/scripts`（在 6854aad 上；之后没改 Python）：499 个通过，2 个跳过，1 个失败。失败的仍是票 01～07 记过的 `test_serialize_tbseg_walked_from_container`，它读本机没有的 `datasets/pkls/ACUT.pkl`。本票没改后端。
  - e2e：`annotate-direct-links`、`annotate-grouping`、`annotate-boxes`、`annotate-samples`、`annotate-open-by-symbol`、`annotate-rally-random`、`symbol-search` 共 15 条全过，日志在 `evidence/09/e2e-annotate.log`。
- 在本票的 diff 里 grep `docs/research`，结果为空。

**审查**：两份报告和逐条处理在 `evidence/09/review-standards.md`、`review-spec.md`。
- 已修：
  - 注释去掉还没实现的 `#q=`；
  - 「股票 + 日期」先对股票列表核代码，不在就提示、不动当前的图；
  - `openSample` 挪进标注 store；
  - 改用 `enterAnnotate()`，不再在视图 store 外面直接写 `mode`；
  - `shiftDays` 共用；代码的规范化复用 `resolveSymbolInput`；
  - `chartLinkWindow` 只返回图窗；
  - 撤回「换当前 pattern」。
- 没改：e2e 里另有两份 `TRAIN_END`。那是测试自己的期望值，不该从被测代码里取。

**新起的界面名**（照 `GLOSSARY-MAP.md` 命名规则）
- 提示条的键 `url`；状态 `bad_url`。
- 链接里的键 `symbol`、`date`、`sample`。

`not_found`、`ok` 是已有的。

**共享机制与复核**
- 改了：
  - 标注 store 加 `openSample`，样本卡改走它，行为不变；
  - 视图 store 加 `enterAnnotate`；
  - `shiftDays` 从 `grouping.ts` 挪到 `viewWindow.ts` 并导出；
  - 提示条加 `url` 一类；
  - `App.vue` 监听 `hashchange`。
- 复核了还没开始的 10、11、12。11 的「从 `rally`、`random`、代码输入和链接进来时，都落在 `annotate`」仍然成立：链接走 `openSymbol` 或 `enterAnnotate`，11 加了 `compare` 之后也照样切回 `annotate`。没有条文变假，都没改。spec 自认领以来没有变化。

**给后续票的接口**
- 第二段 `#q=`：在 `annotate/directLinks.ts` 的 `parseLink` 里加一种写法，在 `stores/directLinks.ts` 跟它；打开样本用标注 store 的 `openSample(id)`。

**写了共享数据和主目录**
- 标注目录、`datasets/` 都没写。测试只写系统临时目录和 scratchpad。
- worktree 的 `outputs/` 里有 e2e 跑出的小扫描和找图缓存，属于临时产物，删 worktree 时一起删。

**运行环境**
- worktree 的 `uv sync` 下载 torch 时卡住，已按进程号停掉。pytest 和 e2e 用主目录 `.venv` 的解释器，在 worktree 根目录跑；e2e 用 `PATH2_E2E_PYTHON` 指定这个解释器。
- worktree 的端口临时改成 8089 / 5189（skip-worktree，没提交），合回前已改回。
- 04、08 的 e2e 要真后端：在 8089 起过一个，跑完已按进程号停掉。

`未安排人审：两种链接的格式（#symbol=<代码>&date=<YYYY-MM-DD>、#sample=<样本编号>）与新起的界面名 url、bad_url；原因：spec 第 10 节把「两种链接的格式」列为 owned、由用户定；第一段界面上的这类值，build-on 就是 V-S1，V-S1 本身就是这次审查`

`未安排人审：「股票 + 日期」的图窗（那天往前约半年、往后约两个月）、样本链接不换当前 pattern（样本属于别的 pattern 时画淡、不带字母）、跟完去掉地址的 # 部分；原因：顺不顺手只有用户实际用的时候判断得了，build-on 是 V-S1（spec 第 7 节 V-S1、第 10 节）`
