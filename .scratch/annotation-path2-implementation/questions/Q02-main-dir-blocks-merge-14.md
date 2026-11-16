# 票 14 合不回去：主目录里有别处改了、还没提交的文件

Status: open
Blocks: 14
Raised: 2026-11-16 ticket-14
Recommended: 等那边提交后再合回

## 在决定什么

票 14（标注三档的左栏换成找图清单 `rally` / `random` / `charts`）已经做完：
- 代码、测试、独立审查、截图都在分支 `impl/14-finder-list` 上；
- 单测全过；
- e2e 和开工前比没有新增失败。

只差最后一步：把分支合回 `annotation-path2`。

合不回去，是因为主目录里有 9 个文件改了、还没提交：
- 看内容是在改 annotation-round 的流程（「setback / invalidation」那套出局核对）和 new_step 的 mapping，最后一次改动在 00:49，到 01:17 还没提交；
- 不是本票改的；
- 其中 `.scratch/annotation-path2/manual.md` 本票也改了（本票改「四、界面一览」和「① 找图」，那边在 ⑤ 加了一行，内容不冲突），但文件里有没提交的改动，git 会拒绝合并。

本票不会去动别人没提交的改动（不替它提交、不 stash）。

没人处理的话，票 14 一直停在「做完没合回」。实施存储里没有别的票在等它。

## 路线

### A. 等那边提交后再合回

做法：
1. 主目录那批改动由正在做它的会话（或你）提交。
2. 之后你说「继续 14」。
3. 执行者把新的调度分支合进票分支（`manual.md` 两边改的地方不挨着，预计 git 自动合并）。
4. 那边也改了 `spec.md`，重核票 14 引用的 spec 条款。
5. 重跑单测；e2e 只在合并后的树与测过的不同时重跑。然后合回、写完成记录。

代价：要等那边做完；合回前多一轮合并与重测，约十几分钟（要重跑 e2e 全套时约半小时）。

不改任何决定或 spec。

### B. 那边先不提交，把它的改动挪走再合

做法：由那边的会话或你，把这 9 个文件的改动先收起来（commit 到别的分支或 stash），票 14 立刻合回；那边再在新的调度分支上接着改。

代价：打断那边的工作；`manual.md` 回来时要和本票的改动合一次（不冲突）。

不改任何决定或 spec。

## 为什么推荐 A

- 那边看着是一件独立的事，等它提交最省事，也不碰它的工作现场。
- 两边在 `manual.md` 里改的是不同的节，合并预计不用手工处理。
- 票 14 的验收不受影响。

## 证据

- 主目录 `git status --short`（2026-11-16 01:17）：
  - `.claude/skills/annotation-round/SKILL.md`、`.claude/skills/annotation-round/references/checklist.md`、`ledger.md`、`writing-app.md`；
  - `.scratch/annotation-path2/manual.md`、`.scratch/annotation-path2/spec.md`；
  - `CLAUDE.md`、`path2/GLOSSARY.md`、`path2_apps/new_step/mapping.yaml`。
- 票分支尖 `impl/14-finder-list` 84b21e8；独立审查所在提交 1902a86，e2e 全套所在提交 9d20e13。
- 完成记录草稿：`impl/14-finder-list:.scratch/annotation-path2-implementation/evidence/14/completion-draft.md`。
- e2e 对照：`impl/14-finder-list:.scratch/annotation-path2-implementation/evidence/14/e2e-baseline.txt`、`e2e-after.txt`。

## 用户的答复

- 2026-11-16：选 A「等那边提交后再合回」（用户在调度会话的选择题里选的推荐项）。答复时主目录那 9 个文件仍未提交；调度会话等主目录没有未提交改动后，再叫执行者接着合回。

## Comments

- 2026-11-16 ticket-14：提出。主目录那批改动最后一次修改在 00:49，提出时已停了约半小时，仍未提交。
