# 放样本与成员框（含因果性、冻结与 M12）

Status: ready-for-agent
Progress: not-started
Blocked by: 05

## Purpose

样本是用户「这天会不会买、凭什么」的判断。本票让用户放样本、看清依据是哪几个框，并保证两件事：依据里混不进样本日之后的东西；旧样本的依据不会被后来的改动悄悄改掉。

## Source

- [spec](../annotation-path2/spec.md) 的这几处：
  - 5.2：样本三角、`bracket` 轨上样本的虚线、选中时暗一档、`pattern` 下拉；
  - 5.5 全节；
  - 用户故事 12～18。
- 决策：[结构化标注](../annotation-path2/issues/01-structured-annotation.md)、[命名](../annotation-path2/issues/14-naming.md)。
- 前置交付：[05](05-boxes-and-vocabulary.md)。

## Inherited Direction

- 共用执行边界。
- 正样本只按当天看得到的判（spec 1.3）。
- **成员框必须在样本日当天或之前结束**；换掉当前样本时，冻结旧样本的成员。防的是：后来补画的框改掉旧判断（决策票 01、14）。
- **M12**：拖框边时停在会被波及的那个样本日；`member_of` 列出收了它的全部样本，包括别的 pattern 的（变淡、只读）。防的是：删改共用的框时，在不知情中改掉旧样本的依据。这是已经实测到的漏洞（说明书报告 M12）。
- 前端的成员推断，必须过 03 的例子。
- `GAP`、`NEAR` 读同一处默认值（V-01-1）。

## What to build

- **放样本**：
  - `tool` 里的 `point`，放完自动回到 `box`；
  - 样本默认 `pos`，归当前 pattern；同一 pattern 同一天已经有样本，点下去就是选中它；
  - 顶栏的 `pattern` 下拉，含 `unsorted · n` 和 `+ new`；
  - `selection` 页可以改样本的 pattern、judgment、note，也可以 delete。
- **成员**：
  - 自动推断成员；
  - 手动点进点出：从样本这边的成员链、`others` 一排，或者从框那边的 `member_of` 一行；
  - 当前样本与冻结。
- **跨样本日的框**：变灰，悬停写 `crosses sample date`；成员链上的空槽注明原因。
- **M12 三条**：
  - 拖框边停在会被波及的样本日；
  - `member_of` 一行；
  - 02 拒绝保存时，在界面上显示原因。
- **辅助提示**：画了没收的空槽和 `◂`、`dup`、样本字母。
- **图上**：
  - 样本日画三角，正样本实心 ▲，负样本空心 △；
  - `bracket` 轨上画样本跨度的虚线；
  - 选中样本时，样本日之后的 K 线暗一档；
  - 不画两条竖虚线。

## Scope and exclusions

不做 unsorted 页和 pattern 页，这些在 07。

## Blocked by

05

## Acceptance criteria

- e2e 覆盖以下流程：
  - 放样本，它自动收进之前的框，刷新后成员不变；
  - 跨过样本日的框收不进，并且有提示；
  - 拖框边会停在样本日；
  - 换掉当前样本以后，再补画的框不会并进旧样本。
- 前端的成员推断过 03 的全部例子（vitest 读同一份 JSON）。
- 后端拒绝保存时，界面显示原因，改动不会悄悄丢掉。正常操作（不越界地改起止、删样本）照常保存。
- 拍截图自查（共用执行边界第 5、6 条）：实心和空心的三角分得清；暗一档以后，K 线仍然看得清形状。
- `未安排人审：界面是否顺手、颜色是否分得开；原因：第一次真实使用就是 V-S1，它本身是用户的审查，那批标注只当试用（spec 第 7 节 V-S1）`

## Validation responsibility

为 V-01-1 里的 `GAP`、`NEAR` 提供「只在一处设定的默认值」。V-01-1 不在票里收口，见[拆分总览](../ticket-breakdown.md)「验证责任」。
