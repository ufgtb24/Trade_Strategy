# 票 13 合不回去：主目录里有别处正在改、还没提交的文件

Status: open
Blocks: 13
Raised: 2026-11-15 ticket-13
Recommended: 等那边提交后再合回

## 在决定什么

票 13（顶栏加 `scan` 档）已经做完：
- 代码、测试、独立审查、截图都在分支 `impl/13-scan-tier` 上；
- 单测全过；
- e2e 和开工前比没有新增失败。

只差最后一步：把分支合回 `annotation-path2`。

合不回去，是因为主目录里有 7 个文件改了、还没提交：
- 看内容是在做「点记号后直接按 Delete 删反馈」，22:29～22:35 还在改；
- 不是本票改的；
- 其中 `.scratch/annotation-path2/manual.md` 和 `path2_web_ui/src/components/ChartArea.vue` 本票也改了，git 会拒绝合并。

本票不会去动别人没提交的改动（不替它提交、不 stash）。

没人处理的话，票 13 一直停在「做完没合回」。票 14 依赖它，也派不出去。

## 路线

### A. 等那边提交后再合回

做法：
1. 主目录那批改动由正在做它的会话（或你）提交。
2. 之后你说「继续 13」。
3. 执行者把新的调度分支合进票分支。`ChartArea.vue` 两边改的地方挨得近，多半要手工合一下。
4. 重核票 13 引用的 spec 条款，因为那边也改了 `spec.md`。
5. 重跑单测和 e2e，再合回、写完成记录。

代价：要等那边做完，合并时多一轮冲突处理和重测，约半小时。

不改任何决定或 spec。

### B. 那边先不提交，把它的改动挪走再合

做法：由那边的会话或你，把这 7 个文件的改动先收起来（commit 到别的分支或 stash），票 13 立刻合回；那边再在新的调度分支上接着做。

代价：打断正在做的事，那边回来时要自己解同样的冲突。

不改任何决定或 spec。

## 为什么推荐 A

- 那边看着是一件小而完整、正在收尾的事，等它提交最省事。
- 冲突只有两个文件，由本票执行者在票分支上解，不会碰那边的工作现场。
- 票 13 的验收不受影响。

## 证据

- 主目录 `git status --short`（2026-11-15 22:51）：
  - `.scratch/annotation-path2/manual.md`、`.scratch/annotation-path2/spec.md`；
  - `path2_web_ui/e2e/feedback.spec.ts`、`path2_web_ui/src/components/ChartArea.vue`、`path2_web_ui/src/components/FeedbackPanel.vue`、`path2_web_ui/src/stores/feedback.ts`、`path2_web_ui/tests/components.feedback-clicks.spec.ts`。
- 票分支尖 `impl/13-scan-tier` 449aace，测试与审查所在提交 105d280。
- 完成记录草稿：`impl/13-scan-tier:.scratch/annotation-path2-implementation/evidence/13/completion-draft.md`。
- e2e 对照：`impl/13-scan-tier:.scratch/annotation-path2-implementation/evidence/13/e2e-baseline.txt`、`e2e-after.txt`。

## 用户的答复

（待答）

## Comments

- 2026-11-15 ticket-13：提出。合回前等了约 4 分钟，主目录那批改动仍未提交。
