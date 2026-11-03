# 成员推断、骨架、框套框：Python 参照实现与共用例子

Status: ready-for-agent
Progress: done
Claimed: 2026-11-03 parallel-tickets ticket-03 @ worktree impl/03-membership-reference
Blocked by: 02

## Purpose

会话读标注时，得到的成员、归属、骨架，必须和用户在界面上看到的完全一致。本票写出唯一的参照算法，再配一组带答案的例子，让前端的实现和它对得上。

## Source

- [spec](../annotation-path2/spec.md) 的这几处：5.4「框套框」；5.5「成员框的自动推断」「手动点进点出」「当前样本与冻结」「跨过样本日的框」；5.6 骨架的定义；5.9「骨架、框套框、成员推断的算法」；第 9 节「成员推断、骨架、框套框」。
- 可查的参照：`docs/research/2026-10-28_annotation-web-loop/repro/backend_contract.md` 里讲成员推断的那几节。只能查，不能引用（共用执行边界第 4 条）。
- 前置交付：[02](02-annotation-store.md)。

## Inherited Direction

- 共用执行边界。
- 候选只取在样本日当天或之前结束的框。防的是：依据里混进当天看不到的东西（决策票 01、14）。
- `GAP`、`NEAR` 是待验证的默认值（spec 第 10 节），只在一处设定、各处去读那一处。V-01-1 以后会改它们。
- 手动点进点出永远算数。
- 冻结后的成员直接存成 `members`，会话读的时候不用重算（spec 5.9）。

## What to build

- 参照实现，放在 02 的存储模块里或同一个包里。
- 一份 JSON 例子文件。每个例子的输入是框、样本、`attach` / `detach`、手动进出，期望输出是归属、成员、骨架，以及跨过样本日的空槽原因。
- 例子文件放在 Python 测试和 vitest 都读得到的位置，由执行者定，写进模块文档。

## Scope and exclusions

前端实现不在本票。05 和 06 各自实现，并且都要过这组例子。

## Blocked by

02

## Acceptance criteria

- 例子至少覆盖：
  - 默认归属到包住它的框里最短的那个；
  - `detach` 和 `attach` 互斥；
  - 按 `GAP` 链式扩展，直到不再新增；
  - 被成员包住的框、`attach` 到成员上的框，都带进来；
  - 跨过样本日的框收不进，空槽的原因分得清；
  - 手动进出覆盖自动推断；
  - 骨架只取顶层特征名的先后，子框和属性不进骨架；
  - 同名框标出 `dup`。
- Python 测试逐例通过。例子文件是唯一的事实来源，测试从文件里读，不另抄一份答案。
- 无人审：全部可机检。

## 完成记录

2026-11-03，parallel-tickets ticket-03。合并提交 a12b22f（`--no-ff` 合回 `annotation-path2`）。测试所在提交 572967f（本票分支合进调度分支 ac9bd95 之后）；合回后的代码与它相同。

**做了什么**
- 新模块 `path2_web/annotation/membership.py`，纯计算，不读行情、不读写标注文件：
  - `parents(boxes, days)`：框套框，每个框属于这组框里的哪个框；
  - `sample_members(date, boxes, days, stored=, new_boxes=, manual=, gap=)`：样本现在的成员框，含放下样本时的推断、冻结、当前样本期间新画的框、手动点进点出、因果过滤；
  - `member_tree`、`skeleton`、`dup_features(members, boxes, days)`：成员框排成树、骨架、顶层同一特征的 dup；
  - `empty_slots(charts, symbol, sample_id, days, near=)`：成员链上的空槽，原因分 `unclaimed`（画了没收）和 `crosses_sample_date`（跨过样本日收不进）；
  - `GAP = 20`、`NEAR = 40` 只在这个模块里设定，函数的默认参数读它们；
  - 坏输入报 `MembershipInputError`，code 为 `attach_and_detach`、`unknown_chart`、`unknown_sample`。
- 例子文件 `tests/path2_web/fixtures/membership_examples.json`，20 例，格式写在文件的 `about` 里。答案是手算后写进去的，没有用实现生成。
  - 例子里的位置写成 `days` 的下标，调用实现之前换成日期。`days` 是 2025 年上半年的交易日，带着美股休市日的空缺。所以如果哪个实现把「隔 20 根」算成 20 天，就过不了。
  - vitest 用 node 的 fs 读同一个文件，从 `path2_web_ui/tests/` 出发的相对路径是 `../../tests/path2_web/fixtures/membership_examples.json`。这一点写进了模块说明。
- 测试 `tests/path2_web/test_annotation_membership.py`：
  - 逐例从例子文件读答案，不另抄一份；
  - 检查例子覆盖了票面列的 8 种情形（例子的 `covers` 标记）；
  - 检查会话的读法：把存储重放出的状态原样交给参照实现，能算出骨架和空槽。
- 包说明 `path2_web/annotation/__init__.py` 加了一行，介绍 membership。

**实现上的选择**（spec 没规定、本票定下的，都由例子守着）
- **怎么数「隔几根」**：一个日期的序号 = `days` 里比它早的交易日有几个。先后、包住、交叠、长短、`GAP`、`NEAR` 都按序号比。因果按日期字符串比 `end <= date`，和存储保存时的校验是同一条。
- **框的先后**：起点早的在前；同起点的，长的在前；再按编号的字符串比。
- **几个框一样短时归谁**：包住它的框里取最短的；一样短取起点早的；再一样，取编号小的。
- **`attach` 什么时候算数**：那个框在这组框里、比它长、和它交叠。拖框以后不再满足的 `attach` 不算数，照默认规则。所属的框一定更长，所以不会绕成环。
  - 原型对这种 `attach` 是照单全收的。例子 `stale_attach_falls_back` 和 `stale_attach_does_not_join` 把两种做法分开了。
  - 在一个样本的成员框里，`attach` 的框不是成员框时，照默认规则在成员框里找。
- **`detach` 和 `attach` 同时出现**：当坏输入报错。存储本来就拒绝保存这种框。
- **spec 5.5 推断的第 3 步**（带上被成员框包住的框、`attach` 到成员框上的框）不单独做：这样的框和某个成员框交叠，终点不早于边界，第 2 步停下时已经收进来了。两位审查者都核过这个论证。
- **成员框随后怎么变**：
  - 新放的样本：成员框 = 推断结果；
  - 已有成员框的样本：存下的那份就是冻结的；它是当前样本期间，推断会收的新框并进来，只加不踢；
  - 手动点进点出最后生效；
  - 最后只留还在这张图上、且在样本日当天或之前结束的框。
- **骨架和 dup**：骨架给特征编号，不给特征名，改特征名不影响分组。还没标特征的框记 null，不算 dup。
- **空槽**：
  - 两种原因的框都要满足三条：特征在同一 pattern 的样本的成员框里出现过；不是这个样本的成员框；也不是同一张图上同一 pattern 别的样本的成员框。
  - unsorted 的样本自成一组。
  - 「跨过样本日」= 起点不晚于样本日、终点晚于样本日。整段在样本日之后的框不留空槽。
  - 存下的成员框后来越过了样本日的，不再算成员框。这一条是按审查改的。

**验收**
- 票面列的 8 种情形都有例子，每例的 `why` 写了为什么是这个答案：
  - 默认归属到最短的包住它的框：`nest_shortest_container`、`nest_edges_and_ties`；
  - `detach` 和 `attach` 互斥：`detach_and_attach_override_default`、`stale_attach_falls_back`、`attach_and_detach_together_rejected`、`tree_with_detach_and_attach`；
  - 按 `GAP` 链式扩展到不再新增：`gap_chain_until_no_more`，三轮各收一个，两处正好等于 `GAP`，最后差一根停下；`nothing_within_gap`；
  - 被成员框包住的、`attach` 到成员框上的框都带进来：`contained_and_attached_join`、`stale_attach_does_not_join`；
  - 跨过样本日收不进，空槽原因分得清：`crossing_box_is_never_a_member`、`manual_in_and_out_win`、`frozen_sample_keeps_its_members`、`slot_reasons`（两种原因都在）、`stored_member_now_crossing`；
  - 手动进出覆盖自动推断：`manual_in_and_out_win`、`current_sample_grows_with_new_boxes`；
  - 骨架只取顶层、子框和属性不进：`skeleton_is_top_level_names`、`tree_with_detach_and_attach`、`unnamed_boxes`；
  - 顶层同一特征标 `dup`：`dup_only_on_top_level`、`unnamed_boxes`。
- 例子分得出几种容易写错的做法。在临时副本里把实现改成下面几种，各有例子失败（脚本没入库）：
  - 「隔 20 根」算成 20 天：3 例失败；
  - `attach` 不查交叠和长短：1 例失败；
  - 一样短时取起点晚的：1 例失败；
  - 照原型字面做第 3 步：1 例失败；
  - `GAP` 边界不含等号：1 例失败。
- 全套测试：在 572967f 上跑 `pytest tests/path2_web tests/scripts`，结果 493 通过、2 跳过、1 失败。
  - 失败的仍是票 01、02 记过的 `test_serialize_tbseg_walked_from_container`，它读本机没有的 `datasets/pkls/ACUT.pkl`，与本票无关。
  - 本票新增的 23 个测试全过。
  - **环境说明**：这次没用 worktree 自己的 `.venv`。`uv sync` 经代理下载 torch 等大包，一个小时还没下完，我已按进程号停掉。测试用的是 scratchpad 里临时建的环境，装了测试要用的包（pytest、pandas、fastapi、akshare、yfinance 等），版本取当时的最新版，没有照 `uv.lock` 锁定。本票只新增了一个纯标准库模块，和 `__init__.py` 里的一行说明。
- 在改动的代码、测试、注释里 grep `docs/research`，结果为空。
- `未安排人审：成员链空槽的两条取舍。一条是同一张图上、同一 pattern 别的样本的成员框不留空槽；另一条是 unsorted 的样本自成一组，看特征「出现过」没有。原因：spec 5.5 只写到「名字在这个 pattern 里用过、却没收进来的框」，这两条是 cc 照原型补的。提示好不好用，只有用户在第一次真实标注（V-S1）时判断得了。`

**审查**：两份报告在 `evidence/03/review-standards.txt`、`review-spec.txt`。
- 已修：
  - 空槽原来直接用存下的成员框，后来越过样本日的旧成员框会被当成成员框：它不出跨样本日的空槽，还把样本范围起点拉远，报出不该有的「画了没收」。现在先滤掉这种框，补了例子 `stored_member_now_crossing`。
  - 说明里把还不存在的界面写成了现状，已改成只写这份参照的约定。
  - 单独说「成员」的地方都改成「成员框」。
  - 测试文件不再写票号和「票面」，改为把要求本身写清楚。
  - 「特征名」「同名」「没起名」按词表改成特征、同一特征、还没标特征。
  - 交叠和包住做成框自己的两个方法；范围起点改名 `range_start`；框编号到特征编号的映射、测试里遍历下标的写法各收成一个函数。
- 没改的，及理由：
  - `(members, boxes, days)` 三个参数总是一起传，每层都重新换算一遍序号。输入就是状态的原样和例子文件的约定，前端照同一个形状写；一张图上的框只有几十个，重算不费事。
  - 框同时带日期和序号：两者各有用处，类的说明里写了。日期比因果，和存储的校验一致；序号比根数。
  - 会话读法那个测试的答案写在测试代码里，不在例子文件中：它检查的是存储状态的形状能不能直接交给参照实现，前端没有这条路。它的答案也不是从例子文件抄的。
  - spec 审查提到的空槽排除规则：保留，写成上面的「未安排人审：」行。
  - `GAP`、`NEAR` 前端还读不到：这是 06 的事（拆分总览「验证责任」V-01-1 那一行）。模块说明只写「默认值只在本模块设定」。

**给后续票的接口**（05、06、07）
- 前端要实现的就是上面那几个函数，逐例通过 `tests/path2_web/fixtures/membership_examples.json`。
  - 例子按 `fn` 分四种：`parents`、`members`、`tree`、`slots`。每种的参数和期望的形状写在文件的 `about` 里。
  - 期望报错的例子写成 `expect_error: <code>`。
- 05（框套框）：
  - 子框轨的归属，用 `parents` 对全图的框算；
  - 一个框的 `attach` 拖框后失效时，参照实现当它不存在，界面可以在这时把它清掉；
  - 能点 `attach` 的框，参照实现认的是「比它长、和它交叠」的框。
- 06（成员框）：
  - 照 `sample_members` 的模型：新放的样本用推断；之后存下的成员框就是冻结的；当前样本期间新画的框传 `new_boxes`；手动点进点出传 `manual`，界面在会话期间记住。
  - 空槽和它的两种原因照 `empty_slots`。
  - `GAP`、`NEAR` 的默认值现在只在 Python 常量 `membership.GAP` / `membership.NEAR` 里。要让前端读同一处，需要后端把这两个数交给前端，比如加进读标注的返回，或者走配置路由。
- 07：骨架用 `skeleton`，给的是特征编号，显示时换成特征名。

**共享机制与复核**
- 本票新增 `path2_web/annotation/membership.py`，改了 `path2_web/annotation/__init__.py` 的包说明。没有改共享接口、配置或别的模块。
- 复核了还没开始的 05、06、07、09、10、11、12，条文都仍然成立，没有改动。spec 自认领以来没有变化。

**写了共享数据**：没有。测试只用内存数据和仓库里的例子文件；临时环境与核对脚本都在 scratchpad。
