---
name: merging-branches
description: 用户要把一个分支的工作合入另一个分支时调——"把 A 合并到 B"、"合并到 xx 分支"、"合并分支"、"让两个分支 HEAD 一致"、"分支提交太碎先压缩再合"、"分支合完了帮我同步远程"。用户手动合并分支时也按本流程核对。
---

# merging-branches

把源分支 A 的工作压成一个提交、rebase 到目标分支 B 上、再 ff 合入，使 A/B 两分支 HEAD 完全一致。

**核心不变量**：整个过程 A 的**工作树内容**不能变。`git rev-parse A^{tree}` 在 squash 前后必须逐字相同（rebase 后因为 B 的改动进来会变，那是预期的）。这条断言能抓住 90% 的手滑。

**术语**：A = 源分支（会被重写历史），B = 目标分支（只被 fast-forward，绝不重写）。

## 解析用户说法 → 定 A / B

| 用户说 | A | B |
|---|---|---|
| 「合并 X 到 Y」「把 X 合并到 Y」 | X | Y |
| 「合并到 Y」（只点名目标） | **当前分支** | Y |
| 「合并分支」（没点名任何分支） | **当前分支** | 用 `AskUserQuestion` 让用户从本地分支里选 |

- 当前分支 = `git branch --show-current`（本 worktree 所在分支），**不要问用户**——前两种说法里 A 是确定的
- 「合并分支」的候选列表：`git branch --format='%(refname:short)' --sort=-committerdate`，去掉当前分支、`backup/*`、`worktree-agent-*`；取前 4 个作选项（最近提交的在前），其余用户可在「Other」手输
- 定完后用一句话复述「A=…，B=…」再进阶段 0，给用户纠正的机会；A == B 直接停

## 阶段 0：前置闸（任一不过就停下问用户，不要"顺手修一下"）

```bash
# 0.1 两分支各自所在 worktree（本 repo 常态：分支被别的 worktree 占用，checkout 会 fatal）
git worktree list --porcelain | grep -B2 'branch refs/heads/\(A\|B\)$'

# 0.2 工作区干净（在每个相关 worktree 内各跑一次；输出必须为空）
git -C <worktree> status --porcelain

# 0.3 与远程双向同步（输出必须是 "0<TAB>0"）
git rev-list --left-right --count A...origin/A
git rev-list --left-right --count B...origin/B
```

- **0.1 占用处理**：分支被别的 worktree 占用时，**不要** `git checkout`（直接 fatal），改用 `git -C <该 worktree 路径>` 在它自己的 worktree 里操作。两分支各自的操作各回各家。
- **0.2 不干净怎么办**：停下，把 `git status --porcelain` 的输出原样贴给用户，等他指示后再继续。**不得自行创建任何提交、不得 stash、不得 pull**，也不要替他提议这些做法——由他处理完，重跑阶段 0 再往下走。
- **0.3 为什么要查 behind 而不只是"已 push"**：本地若落后远程，squash 会把远程独有的提交丢掉。ahead≠0 → 先 push；behind≠0 → 先 pull/rebase，**都由用户拍板**，skill 不自作主张。
- untracked 文件不影响 reset/rebase，但仍要报给用户看一眼——避免它们是本该提交的东西。

## 阶段 1：定分叉点 + 退化判定

```bash
MB=$(git merge-base A B)
git log --oneline "$MB..A"        # A 分叉后的提交清单，给用户看
git rev-list --count "$MB..A"     # N = 待压缩的提交数
```

先判退化，别硬跑全流程：

| 情况 | 判据 | 处理 |
|---|---|---|
| A 已是 B 的祖先 | `git merge-base --is-ancestor A B` 为真 | A 无新工作，**无事可做**，报告后停止 |
| N = 0 | `rev-list --count` 为 0 | 同上，`git commit` 会报 nothing to commit |
| N = 1 | — | 跳过阶段 2（已经是单提交），直接 rebase |
| B 已是 A 的祖先 | `--is-ancestor B A` 为真 | 无分叉，rebase 是 no-op，仍照跑（squash 有效） |

A 分叉后**含 merge commit（A 曾 merge 过 B）也照跑**——merge-base 就是当时被并入的 B 提交，squash 只会吸收 A 自己的改动，实测 tree 不变量成立。

## 阶段 2：备份 + squash A

```bash
git branch backup/A-<YYYYMMDD-HHMM> A          # 强制：重写历史前必须留本地锚点
TREE_BEFORE=$(git rev-parse A^{tree})

git -C <A 的 worktree> reset --soft "$MB"
git -C <A 的 worktree> commit -m "<message>"

[ "$TREE_BEFORE" = "$(git rev-parse A^{tree})" ] || echo "✗ tree 变了，立即停手"
```

**commit message 必须问用户**：把阶段 1 的提交清单摆出来，问他要沿用哪条 / 怎么概括。不要自己拍一个含糊的 "update"。

## 阶段 3：rebase A onto B

```bash
git -C <A 的 worktree> rebase B
```

冲突时（exit≠0）：

```bash
git diff --name-only --diff-filter=U      # 冲突文件清单
```

- **能确定**（一侧是纯新增、另一侧未动；或明显是同一改动的两次表述）→ 解决，`git add`，`git rebase --continue`。
- **不确定**（两侧都实质改了同一逻辑、涉及语义取舍、看不出哪边是想要的）→ **停下问用户**，把双方 hunk 原文贴出来让他选。**不许猜、不许"两边都留"凑合、不许 `--skip`**。
- 要中止：`git rebase --abort`（回到 squash 后的状态，不回到 squash 前）。

rebase 后核对 `git log --oneline --graph A -3`：A 应该是 B 的直接后代 + 1 个提交。

## 阶段 4：ff 合入 B

```bash
git -C <B 的 worktree> merge --ff-only A
git rev-parse A; git rev-parse B          # 两行必须逐字相同
```

**必须 `--ff-only`**：它是断言不是选项。若报 "Not possible to fast-forward"，说明阶段 3 没跑成或中途 B 动过——停下查原因，**不要**退化成普通 merge。

## 阶段 5：同步远程（执行前把两条命令原样给用户确认）

```bash
git push --force-with-lease origin A       # A 历史被重写，普通 push 必被拒
git push origin B                          # B 是 ff，普通 push
```

`--force-with-lease` 而非 `--force`：远程若在此期间被别人推过，前者会拒绝、后者会覆盖。

## 回滚

任何阶段出错：`git reset --hard backup/A-<stamp>`（A）/ `git reset --hard origin/B`（B，B 未 push 前）。确认无误后再删备份分支——**不要在同一回合里顺手删**。

## Red flags — 出现即停

- 想用 `git push --force`（不带 `-with-lease`）
- 想把 `--ff-only` 去掉让 merge 过去
- 阶段 0 有未提交改动，想"先 stash 一下"把工作区腾干净——本 repo stash 栈是全仓库共享的，别的 worktree 里的会话一 pop 就把它取走且从栈里删掉（见 CLAUDE.md）。停下问用户，不要提议 stash
- 阶段 0 不过，想"帮用户先提交了再说"——任何提交都必须他明示
- 冲突"看着差不多"就自己定了
- 没建 backup 分支就 reset --soft
- 反向操作：想 rebase B 或 force push B——B 永远只被 ff
