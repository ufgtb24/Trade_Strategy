# `app` 模式与第一段的 `compare` 叠画

Status: ready-for-agent
Progress: not-started
Blocked by: 07

## Purpose

第一段的验证，要把会话照标注写出来的 app 叠回用户的图上，让用户看出差在哪。本票让主视图能切到 `app` 模式，以及不带对照 tag 的 `compare` 模式。

## Source

- [spec](../annotation-path2/spec.md) 的这几处：
  - 5.2：顶栏的 `mode` 和 `tiers`、`app` / `compare` 怎么分轨、「模式切换」；
  - 5.8 全节；
  - 4.4 档位色；
  - 第 7 节 V-S1 的第 3、4 步；
  - 6.1「mapping 随 app 进 git」；
  - 用户故事 24。
- 决策：[结构化标注](../annotation-path2/issues/01-structured-annotation.md)现行 Answer 第 3 节（换图不退出 `compare`）。
- 前置交付：[07](07-grouping-and-pattern-page.md)。

## Inherited Direction

- 共用执行边界。
- **`compare` 只叠画，不做对照**：只把 app 的 event 叠到用户框所在的轨上，并在 `bracket` 轨上画 hit。不挂第二段的对照 tag，不显示 mapping（spec 5.8）。第二段的对照规则要等 V-S1。
- `tiers` 默认开，只管 band 上的 `qualified_only` / `detected_only`（spec 5.2）。
- band 和档位签用档位色，不套琥珀（spec 4.4，用户 10-29 定）。
- 用 `symbol` 换图时不退出 `compare`（决策票 01）。
- 跑 app 走现有的 `/preview`，数据照 4.1 截断。

## What to build

- 顶栏的 `mode` 分三档。当前 pattern 没有 app 时，`compare` 变灰。
- `app` 模式照现有主视图的画法：按 node 分轨，带三档和 `tiers` 开关。
- `compare` 模式：按会话手工给出的「app 的 node → 用户的特征」对应，把 event 画到对应特征的轨上，并在 `bracket` 轨上画 hit。
- **这个对应怎么给，spec 没定**（见[拆分总览](../ticket-breakdown.md)「待定」第 2 条）。本票的暂行做法：
  - 用一个随 app 进 git 的小文件，写明这个 pattern 用哪个 app、哪个 node 对应哪个特征编号；
  - 「当前 pattern 有没有 app」就看有没有这个文件；
  - 文件格式写进模块文档，供 V-S1 的会话照着写；
  - 第二段的正式 mapping 会取代它。

## Blocked by

07

## Acceptance criteria

- 用一个现成的 app（例如 `bo_only`）加一份手写的对应小文件：`compare` 下，event 出现在对应特征的轨上，hit 出现在 `bracket` 轨上，没有任何对照 tag。用 e2e 验。
- `compare` 下换股票，不退出 `compare`。从 `rally`、`random`、代码输入和链接进来时，都落在 `annotate`。
- app 的全部输出，最后日期都不晚于 2025-12-31（数据墙测试）。
- 没有对应小文件的 pattern，`compare` 是灰的。
- 拍截图自查（共用执行边界第 5、6 条）。
- `未安排人审：叠回来能不能看出差在哪；原因：这正是 V-S1 第 4 步由用户判的，V-S1 就是这次审查（spec 第 7 节）`
