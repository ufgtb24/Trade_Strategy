# 已有 4 条整族反馈补存基准 event 起止

Status: ready-for-agent
Progress: done
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

## 完成记录

- **合回**：`efe2ef6`（`--no-ff` 合回 annotation-path2）；票分支最后一次提交 `f97158c`。人审所审版本是票分支 `3882ef0`（[Q03](../questions/Q03-backfill-reference-review.md)，操作哈希 `1a3b9e8563676b7c3f48239e8179419aa8f54a5bb0df9480e988c4428d07300a`）；真写就在这一版上跑（`write_result.json` 记的提交、脚本 blob `79841023…` 与送审相同，已跟踪文件无改动），写前重算的操作哈希与送审相同；之后只加了证据，结果没有实质变化。
- **旧版提交与 app_ver**：`739a2cf`（第 1 轮改版 `9b2a5e6` 的前一个提交），new_step `app_ver` `1afa716bc5248d4b`，与 4 条反馈记的相同。
  - 取法：按 `path2_web/app_version.py` 的算法对历史提交逐个算指纹，`1afa716…` 覆盖 `6534f68`～`739a2cf`（第 1 轮 `9b2a5e6` 已是 `e325b38dcfc46d86`，第 2 轮 `e0a6c9c` 起是 `32dd64edf923d266`）。
  - 这一段里识别器（new_step）、`path2/`、`path2_apps` 顶层共用代码只改过注释、词表和 mapping；`path2_web` 里跑 app 的入口 `run_app`（`path2_web/app_run.py`）自 `397baf4` 才有，所以取段末的 `739a2cf`。
  - 票面「这 4 条写在第 1、2 轮之间」那句参考说明不准：4 条的最后一次修改都早于第 1 轮改版提交（CRNC 2026-11-11；另三条 2026-11-16 02:15～03:04 UTC；第 1 轮提交 10:27 UTC）。以 `app_ver` 为准。
- **怎么算的**（`evidence/18/old_reference.py` → `old_reference.json`）：
  - 临时 `git worktree add --detach` 检出 `739a2cf`，照「在 git worktree 里开发」准备：数据软链，自己 `uv sync`。标注目录软链建出后随即删掉，旧版不读标注。
  - 用那一版自己的 `run_app` 跑 CRNC、IXHL、LUMN、QBTS：全历史区间到 TRAIN_END、label_horizon 20、`load_params()`。行情经那一版 `path2_web/data.py` 读训练段副本 `datasets/pkls_until_20251231`，没读 `datasets/pkls`。
  - 这一族 = 起点等于反馈 `family_start` 的 hit。基准 event 照当前 `reference_events` 的取法：hit 绑定的事件及其一级子段里 node 是 `step` 的。起止去重、不合并，同前端 `referenceSpans`。
- **与「实测」表对照**（都对上）：

  | 股票 | 反馈 | 补存的 `reference.spans`（node `step`） | 「实测」表旧阶跃 |
  |---|---|---|---|
  | QBTS | f-pc-92 | 2025-03-14～03-14 | 2025-03-14 |
  | IXHL | f-pc-90 | 2025-08-22～08-25 | 2025-08-22～08-25 |
  | CRNC | f-pc-74 | 2025-01-03～01-03 | 2025-01-03 |
  | LUMN | f-pc-95 | 2024-08-06～08-06；2024-08-06～08-07 | 2024-08-06～08-07 |

  - LUMN 是两段：旧版这一族的每个 hit 都挂着起点相同、终点分别是 08-06 和 08-07 的两个阶跃。页面也是这样逐段存、不合并。
  - 旁证：旧版每一族的买点日首尾与 4 条反馈的 start / end 相同；训练段副本指纹 `40508e77…` 与标注全部 299 个批次记的相同。
- **写入**（Q03 获批后，一次）：
  - 用 `evidence/18/backfill_reference.py write`，只经 `append_batch`。新批次文件 `pc-20261117T015401.584Z-300.json`，sha256 `a7f2f1439d3e36be7f0f522ae420e046d895ce57dad1ea32f635af98c96753d2`。
  - 每条操作的 value 是这条反馈当时的整条记录加 `reference`；base 取它当时的最后一次修改。
- **写后机器核对**（`evidence/18/write/write_result.json`，11 项全过）：
  - 已有的 299 个文件，大小与 sha256 一个没变，只多了这一个（`before_files.json` / `after_files.json`）。
  - 经 `read_annotations` 重放：去掉这 4 条的 `reference` 后，整份状态与写前逐字相同（状态哈希 `4de38fef…` 前后一致）；4 条的 `reference` 与计划相同。
  - 冲突、未同步、越界、不合格文件名四份列表与写前相同，都为空；数据指纹一致性不变；note、nodes 不变。
- **状态**（`evidence/18/write/status_after.json`，当前 new_step `app_ver` `32dd64edf923d266`）：
  - 经 `/feedback/status`（真配置、真标注目录、FastAPI TestClient）：QBTS `matched`、IXHL `unmatched`、CRNC `matched`、LUMN `matched`，与票 17 真数据核对一致。
  - 判法原始三态：写后 QBTS `matched`、IXHL `unmatched`；CRNC、LUMN 把范围换成没有买点的一天再判也是 `matched`（由同一次形状那一支判出）。写前的对照取自标注目录字节拷贝上的试写（`evidence/18/dry-run/status_before.json`）：QBTS、IXHL 是 `lost`（页面显示并成 `unmatched`），CRNC、LUMN 换范围后是 `lost`。
  - 用户开着的页面后端（8001 端口）也只读查了一次 `/feedback/status`，4 条结果相同（`evidence/18/write/live_backend_status.json`）。
- **「内容改过」**：annotation-round 摘要（`path2_web/annotation/revision.py` 的 `_digest_issues`）只在 note 或 nodes 变了时写「内容改过」；写后核对 `note_and_nodes_unchanged` 通过。`path2_web/annotation/changes.py` 不比反馈。所以下一轮摘要不会把这 4 条列成「内容改过」。
- **试写**：真写前，在标注目录的字节拷贝（scratchpad）上走过同一套 status / plan / write / status（`evidence/18/dry-run/`）。拷贝用完已删。
- **独立审查**（`evidence/18/review-standards.md`、`review-spec.md`，审的是 `d9d1584`）：
  - 改了（`d6135fa`、`3a5c585`、`3882ef0`）：
    - 输出记代码身份：提交号、已跟踪文件有没有改动、脚本 blob；
    - 补函数说明，魔法值起名（`FIRST_DAY`、`LABEL_HORIZON`、`NO_BUY_DAY`），变量改名；
    - `old_reference.json` 不再记临时 worktree 的绝对路径；`old_reference.py` 用法里的路径改对；
    - 补存后的状态加机器断言（`--expect-backfilled`）；
    - 试写证据补上写前写后的文件清单。
  - 没改：
    - `--approved` 只是自报：脚本核验不了用户，它只防手滑把试写命令打到真目录上；真正的闸是调度会话转告批准。
    - 两份脚本各写一份 `REFERENCE` 和跑 app 的参数：旧版脚本要在旧版代码里单独跑，不能 import 本票脚本。
    - 引用私有的 `_resolve_end_events`：旧版没有公开入口。
    - Spec 轴说「实测」表用的是第 1 轮代码、两版阶跃起止一致：没单独核。「实测」表的脚本没留下；本票的验收是和表对上，已对上。
- **测试**：本票不改产品代码（`git diff --quiet beb78fe HEAD -- . ':!.scratch'` 退出码 0）。合进调度分支后在票分支尖 `3a2836d` 上重跑 `tests/path2_web/test_annotation_store.py`、`test_annotation_match.py`，共 153 过（`evidence/18/pytest.txt`）。
- **改了的共享机制与先前结论**：
  - 没改代码。
  - 共享数据：主目录 `annotations/` 多了上面那一个批次文件；4 条整族反馈从此带 `reference`；页面上 QBTS 这条从常色变成朱红。
  - 未开始的票：12（两台机器的环境准备）核过，条文没有变假。
- **临时 worktree**：旧版 worktree（`Trade_Strategy-18-old-739a2cf`）已删：先删 `datasets` 软链，再 `git worktree remove --force`。主目录一直在 annotation-path2、工作区没动，没用 `git stash`。
- **要转告用户的一条**：写入时页面后端开着（8001 端口），批次文件只多了一个、序号接在 299 后面，说明写入那一刻页面没有并发保存。若页面没刷新、还拿着写入前的这 4 条去改：改 note 或点出的 node，保存会被拒（存储不许去掉已写下的 `reference`），刷新后再改就行；拖边改成 `range` 存得进，但会记一条冲突。
- **过程里的一处**：第一次发真写命令时，输出目录还不存在，shell 重定向先失败，脚本没跑起来；随即确认标注目录文件数仍是 299。建好目录后再跑的那一次，是唯一的一次写入。

## Comments

- 2026-11-16 由票 16 的 Answer 起草，用户批准时选「批准，发票后接着实施」；人审闸来自用户在票 16 的回答（「真写之前列出来，你点头再写」），照原样写入。
- 暂停 2026-11-16（parallel-tickets，等用户）：人审闸 [Q03](../questions/Q03-backfill-reference-review.md)，4 条要补存的起止已算好、与「实测」表对上，在标注目录字节拷贝上试写通过，独立审查已修（票分支 impl/18-backfill-family-reference 3882ef0）；真写尚未做。恢复：只有调度会话转告「用户已批准写入 Q03」才写——在票 worktree 根目录跑 `.venv/bin/python .scratch/annotation-path2-implementation/evidence/18/backfill_reference.py write --annotation-dir annotations --out-dir .scratch/annotation-path2-implementation/evidence/18/write --expect-ops-sha256 1a3b9e8563676b7c3f48239e8179419aa8f54a5bb0df9480e988c4428d07300a --approved Q03`，再跑 status --expect-backfilled，之后合回、写完成记录、删两个 worktree（票的与旧版 /home/yu/PycharmProjects/Trade_Strategy-18-old-739a2cf）。
- 恢复 2026-11-16（parallel-tickets）：session-18 继续（调度会话转告「用户已批准写入 Q03」，Q03 已 resolved，主目录 651c449）
