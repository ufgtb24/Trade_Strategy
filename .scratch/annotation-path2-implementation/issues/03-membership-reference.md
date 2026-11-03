# 成员推断、骨架、框套框：Python 参照实现与共用例子

Status: ready-for-agent
Progress: in-progress
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
