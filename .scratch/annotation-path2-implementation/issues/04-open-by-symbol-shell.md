# 按代码打开任一只股票：标注模式的外壳与成交量

Status: ready-for-agent
Progress: in-progress
Claimed: 2026-11-03 parallel-tickets ticket-04 @ worktree impl/04-open-by-symbol-shell
Blocked by: none

## Purpose

用户找图的第一条路，是直接打开「心里想到的那只」。本票让主视图不经扫描就能按代码打开训练段里的任一只股票，并且只画 K 线、成交量和用户自己的东西。

## Source

- [spec](../annotation-path2/spec.md) 的这几处：5.2 顶栏的 `symbol`、侧栏三页、「图」里的成交量（M7）和 `annotate` 画什么；5.3「按代码打开」；4.1；1.8 的前两行；用户故事 1、5、27。
- 决策：[结构化标注：存什么、界面和主视图怎么合](../annotation-path2/issues/01-structured-annotation.md)的 Answer 第 1 节。

## Inherited Direction

- 共用执行边界。
- 标注时图上不画任何 app 认出的东西（决策票 01；说明书报告第 7 节第 4 条）。防的是：用户被现成的 detector 结果带偏。
- 股票列表就是训练段副本里有的股票，2026 年才上市的不出现。
- 不要 `json` 页（用户 10-31 定删）。
- K 线和成交量沿用现有渲染（spec 第 8 节）。

## What to build

- **后端**：
  - 加一个股票列表路由：读训练段副本目录，排除 01 写的指纹清单；
  - 按代码打开沿用现有的 `/ohlc`（已经截断）：代码不合法回 400，不存在回 404（`check_symbol`）。
- **前端**：
  - 顶栏加 `symbol` 输入框，回车就打开，不需要先扫描；
  - 侧栏建好 `selection` / `features` / `pattern` 三页的空架子，内容由后面的票填；
  - `annotate` 模式下只画 K 线、成交量，以及后面才有的用户的框和样本；
  - 成交量在三种模式下都画，高度默认约为主图的四分之一（待验证，spec 第 10 节）；
  - 现有的扫描入口照旧能用。

## Scope and exclusions

- 不做 `mode` 的 `compare` 和 `app`，这在 11。
- 不做画框，这在 05。
- 不改现有的扫描流程。

## Blocked by

none

## Acceptance criteria

- 在顶栏输入训练段副本里的任一个代码、回车：图打开，最后一根 K 线的日期不晚于 2025-12-31。2026 年才上市的代码不在列表里，输入后有明确的「不存在」提示。用 e2e 和 API 测试各验一遍。
- 非法代码回 400，不存在的代码回 404。用 API 测试验。
- `annotate` 模式下，图上没有 band、bo 方框这类 app 的产物。用 e2e 截图加 DOM 断言验。
- 成交量画在图的下方。
- 拍整页截图，照共用执行边界第 5、6 条自查配色和文字，截图放进 `evidence/04/`。
- `未安排人审：界面是否顺手、颜色是否分得开；原因：第一次真实使用就是 V-S1，它本身是用户的审查，那批标注只当试用（spec 第 7 节 V-S1）`
