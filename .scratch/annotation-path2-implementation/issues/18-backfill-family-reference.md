# 已有 4 条整族反馈补存基准 event 起止

Status: ready-for-agent
Progress: in-progress
Claimed: 2026-11-16 parallel-tickets session-18 @ worktree impl/18-backfill-family-reference
Blocked by: 17

## Purpose

让新判法从第一天起就能判用户已经写过的 4 条整族反馈，不让它们一直落在「基准 node 对不上」、每轮都要会话手工核对。

## Source

- [spec](../../annotation-path2/spec.md) 6.13 记录字段（`reference`）与第 10 节「整族反馈存基准 event 的记录形状」一行。
- 决策：[票 16 整族反馈按基准 node 认「同一次形状」](../../annotation-path2/issues/16-reference-node.md) Answer 结论第 6 条；旧阶跃的参照值见同票 Question「实测」表。
- 存储的写法：`path2_web/annotation/store.py` 模块说明（只追加批次文件、重放取最新、旧文件从不改）。

## Inherited Direction

- **用户 2026-11-16 在票 16 同意这一次往标注目录补存。** 项目 CLAUDE.md 规定会话对 `annotations/` 只读，这是只限本票的例外；条件是真写之前列出内容、用户点头再写。防的是：标注是用户手工做的、丢了补不回的东西，写错了用户在页面上也看不出来。
- **用写反馈那一版 new_step 的代码算**（4 条的 `app_ver` 都是 `1afa716bc5248d4b`）：补进去的是当时页面要是已有这套逻辑会存下的值。防的是：用当前版算就等于把阶跃换成新版的，平移再也认不出。
- **只经 `append_batch` 新写一个批次文件**：每条操作写这条反馈改完后的整条记录，`base` 取它当前最后一次修改；`note`、`nodes`、`issue`、日期范围、`family_start`、`app_ver` 一律照抄，只多出 `reference`。已有文件一个不改。防的是：改旧文件撤不回、会倒着改写每轮定格读出的历史、还绕过保存校验。
- **不切主目录的分支、不用 `git stash`**：旧版代码用临时 `git worktree` 检出（照项目 CLAUDE.md「在 git worktree 里开发」准备），用完只删链接。防的是：主目录有用户未提交的改动会被一起收走。
- 写的时候提醒用户别在页面上同时改这 4 条反馈，否则会记成冲突。

## What to build

- 在 git 历史里找出 `app_ver(new_step)` 等于 `1afa716bc5248d4b` 的提交（`path2_web/app_version.py` 的取法；参考：new_step 第 1 轮改版在 9b2a5e6，第 2 轮在 e0a6c9c，这 4 条写在两者之间），用临时 worktree 检出那一版。
- 在那一版里对 CRNC、IXHL、LUMN、QBTS 各跑一次 app（全历史区间，参数同 `path2_web/app_run.py` 的 `app_buys` 说明），取出各条反馈当时那一族（起于它的 `family_start` 的 hit）每个 hit 的阶跃（`step`）起止，去重，得到每条的 `reference: {node: "step", spans: [...]}`。
- 停下给用户看（见验收的人审闸），用户点头后经 `append_batch` 写一个批次文件。
- 脚本和它的输出存进 `evidence/18/`；写前写后的标注目录文件清单与哈希也存进去。

## Scope and exclusions

- 只动这 4 条反馈，只加 `reference`。不补别的反馈，不改样本、框、定义。
- 不改代码库里的产品代码（判法与存储校验是票 17 的）。

## Blocked by

17（存储要先认得 `reference` 键，判法要先会用它）

## Acceptance criteria

- 找到的旧版提交与它的 `app_ver` 写进完成记录。
- 算出的每条 `spans` 和票 16「实测」表里旧版那一族的阶跃对得上（QBTS 含 2025-03-14、IXHL 含 2025-08-22～08-25、CRNC 含 2025-01-03、LUMN 含 2024-08-06～08-07）；对不上就停下报告，不写。
- 人审闸（停在写入标注目录之前）：用一张表列出 4 条反馈各自要加的 `reference`（股票、反馈编号、阶跃起止，与「实测」表旧阶跃并排），用户看完点头才写；不点头就停下报告，不写。这一关只确认要写的内容；写完的状态由下面几条机器检查。
- 写完重放（经 `read_annotations`）：这 4 条除了多出 `reference`，其余字段和写之前逐字一样；标注目录里已有的文件一个没改（写前写后对比文件清单和哈希）；冲突与未同步列表没有新增。
- 4 条在当前 new_step 下经 `/feedback/status` 的状态与票 17 真数据核对的结果一致（QBTS `matched`、IXHL `unmatched`、CRNC `matched`、LUMN `matched`）。
- 下一轮 annotation-round 的摘要不把这 4 条列成「内容改过」（它只比 note 和 node；在完成记录里写明核对过）。
- 临时 worktree 已删（只删链接），主目录的分支和工作区没动。

## Comments

- 2026-11-16 由票 16 的 Answer 起草，用户批准时选「批准，发票后接着实施」；人审闸来自用户在票 16 的回答（「真写之前列出来，你点头再写」），照原样写入。
- 暂停 2026-11-16（parallel-tickets，等用户）：人审闸 [Q03](../questions/Q03-backfill-reference-review.md)，4 条要补存的起止已算好、与「实测」表对上，在标注目录字节拷贝上试写通过，独立审查已修（票分支 impl/18-backfill-family-reference 3882ef0）；真写尚未做。恢复：只有调度会话转告「用户已批准写入 Q03」才写——在票 worktree 根目录跑 `.venv/bin/python .scratch/annotation-path2-implementation/evidence/18/backfill_reference.py write --annotation-dir annotations --out-dir .scratch/annotation-path2-implementation/evidence/18/write --expect-ops-sha256 1a3b9e8563676b7c3f48239e8179419aa8f54a5bb0df9480e988c4428d07300a --approved Q03`，再跑 status --expect-backfilled，之后合回、写完成记录、删两个 worktree（票的与旧版 /home/yu/PycharmProjects/Trade_Strategy-18-old-739a2cf）。
- 恢复 2026-11-16（parallel-tickets）：session-18 继续（调度会话转告「用户已批准写入 Q03」，Q03 已 resolved，主目录 651c449）
