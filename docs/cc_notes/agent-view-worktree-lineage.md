---
title: 后台 session / fork 的工作目录与分支血脉
scope: 后台 session、/fork、Agent 工具子代理各自决定「在哪个目录跑、worktree 建在哪、基于哪个分支」的机制——cwd 从哪来、什么情况跳过隔离、基线取自谁。含全场景 × 全操作行为矩阵与四个静默陷阱。与 agent-view-worktree-recovery.md 互斥：那份讲 worktree 失效后怎么救，这份讲一开始就别建错基线。
category: agent-view
---

# 后台 session / fork 的工作目录与分支血脉

**符号**：`<repo>` = 主 checkout 路径 · `<main-br>` = 主 checkout 当前 checkout 的分支 · `<wt>` = CC 自建 worktree 名 · `<repo>-<x>` = 手工 `git worktree add` 的独立 worktree，其分支 `<x-br>` · `<work-br>` = 你实际在推进工作的分支。

## 三条铁律

1. **worktree 里不用 `/fork`**——它一律把新会话 cwd 打回主 checkout，于是从 `<main-br>` 开分支，与你在哪个 worktree 干活无关，**无法规避**。
2. **派后台 agent 前先 commit**——`git worktree add` 只带已提交状态。
3. **`~/.claude/settings.json` 的 `worktree.baseRef` 保持 `"head"`**——回落默认 `"fresh"` 会让所有后台 agent 静默改从 `origin/<默认分支>` 起。

## 建 worktree 前自查（可粘贴）

```bash
git branch --show-current                      # 当前分支是承载本任务的那个吗
git worktree list                              # 各 worktree 分别停在哪个分支
git cat-file -e HEAD:<本任务依赖的文件路径>     # 上游产物在当前分支真的存在吗
```

任一不对 → **停下，别 EnterWorktree**，更别用 merge / rebase / cherry-pick 去补分支落差。

## 行为矩阵

`✅` = 实测确认 · `〔推〕` = 由已验证机制推出、未直接测。

| 场景（会话 cwd） | 前台会话改代码 | **后台**会话改代码 | `/fork` | agent view / `claude --bg` 起新后台会话 | `Agent` 工具子代理 |
|---|---|---|---|---|---|
| **主 checkout**<br>`<repo>`（停 `<main-br>`） | 直接写，无隔离〔推〕 | 写入被拒 → 建 `<repo>/.claude/worktrees/<新名>`，**基线 = `<main-br>` 的 HEAD** ✅ | 留在 `<repo>`〔推〕 | 新会话 cwd = `<repo>`；它改代码时同左格 〔推〕 | 继承 `<repo>`〔推〕 |
| **内嵌 worktree**<br>`<repo>/.claude/worktrees/<wt>` | 直接写 | 判**「已隔离」→ 原地写，不建新 worktree** ✅ | **cwd 重置到 `<repo>`** ✅（回显 `runs in the origin tree`） | 新会话 cwd = 该 worktree → 同样判已隔离 → **原地写** ✅ | **继承该 worktree** ✅ |
| **独立 worktree**<br>`<repo>-<x>`（分支 `<x-br>`，手工 `git worktree add`） | 直接写 | **不算已隔离** → 建 `<repo>/.claude/worktrees/<新名>`，**基线 = `<x-br>` 的 HEAD** ✅ | **cwd 重置到 `<repo>`** ✅ | 新会话 cwd = `<repo>-<x>`；它改代码时同左格 ✅ | 继承 `<repo>-<x>`〔推〕 |

**读表**：`/fork` 那一列是唯一的红格，其余每列都「你在哪就在哪」。

## 想要什么就用什么：三选二

| 手段 | 继承上下文 | cwd 在目标 worktree | 独立会话 |
|---|---|---|---|
| 会话级 `/fork` | ✓ | ✗（强制回主 checkout） | ✓ |
| agent view 从目标 worktree 起 | ✗（空白） | ✓ | ✓ |
| `Agent` 工具 `subagent_type: "fork"` | ✓ | ✓ | ✗（子代理，靠 SendMessage 沟通） |

三个属性任取其二。**唯一取不到的组合 = 继承上下文 + 对的 cwd + 独立会话**。

⚠ 别把「从目标 worktree 起 agent view」当成 `/fork` 的替代——它给的是**空白上下文**，丢掉的正是 fork 的理由。

## 踩坑：`/fork` 静默把 cwd 换到主 checkout

**现象**：在 `<repo>-<x>`（分支 `<x-br>`）研究问题，`/fork` 出的后台会话却从 `<main-br>` 建了 worktree，拿不到 `<x-br>` 上的成果；派给 agent 的「必读文件」路径全部失效。

**机制**：`/fork` 的副本是 **bg session**，一诞生就吃「cwd 重置 + 自动隔离」；`baseRef=head` 忠实读主 checkout 的 HEAD。

**规避**：worktree 里不用 `/fork`。要独立会话 → agent view 从该 worktree 启动；要带上下文 → `Agent` 工具 `subagent_type: "fork"`。

## 踩坑：`baseRef` 默认值让后台 agent 从 origin 主分支起

| `worktree.baseRef` | 从哪开分支 | 在 `<repo>-<x>` 里建 worktree 的结果 |
|---|---|---|
| `"head"`（**非默认**） | cwd 的 HEAD | `<x-br>` ✓ |
| `"fresh"`（默认） | `origin/<默认分支>` | **origin 主分支（可能远落后）✗** |

**默认配置下无视你在哪个 worktree**。这是配置层的静默单点故障——该键一旦丢失，全部后台 agent 改从 origin 主分支起，且无任何提示。

## 踩坑：同一 worktree 塞多个会话 → 隔离形同虚设

「cwd 在 `.claude/worktrees/` 下就算已隔离」这条规则**默认一个 worktree 只有一个会话**。但 agent view 能不断往同一个 worktree 塞新后台会话，每个都被判「已隔离」，于是**全都在同一份工作树上写**，harness 检测不到。

**规避**：一个 worktree 只放一个写会话。要独立 worktree 就从主 checkout 或非 `.claude/worktrees/` 路径启动。

## 踩坑：bgIsolation 只拦 Edit/Write，bash 重定向能绕过

后台 session 对主 checkout 的写入会被拒（`file edits in the shared checkout are rejected`），
但**这道闸只作用于 Edit / Write 工具**。用 Bash 的 `cat > file`、`>>`、`sed -i`、`mv`
写主 checkout（或任何其他 worktree）会**静默成功**，不报错、不提示。

**典型触发**：skill / 文档 / 脚本里硬编码了绝对路径（如
`/home/…/<repo>/docs/xxx`），而你在某个 worktree 里执行它——文件就落进了别的 worktree
的工作区，提交也会落到那个分支上。

**规避**：任何 skill / 脚本定位仓库内路径一律用
`"$(git rev-parse --show-toplevel)/<相对路径>"`，绝不写绝对路径。别指望隔离闸兜底。

## 踩坑：血脉对了也拿不到未提交的改动

`git worktree add` 只带**已提交**状态。即便正确地从 `<x-br>` 的 HEAD 建 worktree，`<repo>-<x>` 里未提交的编辑**一个都不会跟过去**——「起对分支」和「拿到全部工作」之间还差一次 commit。

## 原理速查

**统一不变式：一个后台会话 = 一个 CC 自己发的私有 worktree。**

| cwd | CC 的判断 | 动作 |
|---|---|---|
| 主 checkout | 共享区，不是私产（**写入被拒**） | 发一个 worktree |
| `.claude/worktrees/<wt>` | 我发过的，已是私产 | 不再叠加 |
| 手工建的独立 worktree | 认不出是隔离，当共享区 | 再发一个 |

三点校正：

- 主 checkout **不是「并行开发区」，是禁写区**——并行发生在挂它下面的各 worktree 之间。
- worktree 内**不是「只支持串行」，是「假定串行且不再检查」**。
- 独立 worktree 触发隔离，**原因不是给它加保护，是 CC 认不出那是隔离**——判据为「是不是我自己发的」，自己发的都在 `.claude/worktrees/` 下（**认路径前缀**）。

**两个独立的锚点**：CC 建 worktree 时，**路径**恒锚在主 repo 根的 `.claude/worktrees/`（不论从哪发起），**基线**恒取 cwd 的 HEAD。

**HEAD 是 per-worktree 的**：各 worktree 有独立 git-dir（`.git` / `.git/worktrees/<名>`），只共享 object 库。故 `baseRef: head` 的「current local HEAD」= 执行时所在目录的 HEAD。

**前台会话不受隔离约束**：`# Background Session` 提示词块仅在 `CLAUDE_CODE_SESSION_KIND==="bg"` 注入。
