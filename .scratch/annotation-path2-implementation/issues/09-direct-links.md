# 直达链接：「股票 + 日期」与「样本编号」（M14）

Status: ready-for-agent
Progress: in-progress
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
