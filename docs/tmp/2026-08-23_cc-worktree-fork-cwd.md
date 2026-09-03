# Claude Code 的 worktree / fork cwd 行为——实测结论

> 日期：2026-08-23 · 起因：`worktree-oat-optuna-blend` 分支来历混乱的归因
> 方法：git 事实核查 + CLI 二进制 v2.1.241 字符串比对 + 两组实测探针

## 〇、本质：`/fork` 把记忆和世界嫁接到了两个分支上

一句话：**`/fork` 让会话的「记忆」和它脚下的「世界」分属不同分支；`/branch` 让两者同源。**

在 worktree 里 `/fork`，新会话拿到的是**两半来自不同分支、彼此不一致**的东西：

| 层 | 来源 | 内容 |
|---|---|---|
| **聊天记录（记忆）** | 源会话（`tune_v1` worktree） | 讨论的是 tune_v1 分支上的文件、路径、已做的改动 |
| **初始 cwd（世界）** | **主 checkout** | dag 分支的工作树 |
| **最终工作树** | 从 dag 的 HEAD 新建的 worktree | dag 的内容 + 一个新分支名 |

正常情况下记忆与世界天然一致——记录本身就是读那个文件系统读出来的。`/fork` 打破这个不变式：
**把在 A 世界里形成的信念，静默地移植进 B 世界**。新会话不会觉得哪里不对，
它的记忆完整、自洽、可信，只是描述的是另一个世界。

**失效边界很精确**，这解释了本次事故那个怪现象——研究结论没失真，文件操作却全废：

| 上下文里的东西 | 移植后还对吗 |
|---|---|
| **读到的内容**（台账数字、`plateau.py` 算法细节） | ✅ **仍然正确**——那是当时如实读出的文本，与文件系统无关 |
| **文件在哪**（`.claude/skills/tune-gates/SKILL.md` 存在） | ❌ 全错——dag 上没有这些文件 |
| **改动已落盘**（SKILL.md 红线已写好） | ❌ 全错——那些编辑在 tune_v1 且**未提交** |

于是派出的 agent 手握**准确的内容**，却在一个**没有那些文件的世界**里找路径，
只能绕到 `/home/yu/PycharmProjects/Trade_Strategy-tune_v1/...` 的绝对路径取文件——
等于绕回 A 世界补 B 世界的缺失。

**规避：worktree 里用 `/branch` 代替 `/fork`**（§3.3 实测三样全占）。


## 一、事故经过

用户在 `Trade_Strategy-tune_v1`（分支 `tune_v1`）研究问题，后台会话却从**主目录**（分支 `dag`）自动创建了新 worktree `worktree-oat-optuna-blend`。两处错误：

1. 未经允许创建 worktree
2. 创建的出发点分支不对（dag，而非 tune_v1）

`dag` 与 `tune_v1` 已分叉（merge-base `d34e023`，tune_v1 领先 19 个提交），tune_v1 上的研究成果不在 dag 上——而新会话的研究恰恰依赖这些成果。用户指出的「矛盾」真实成立。

## 二、机制

### 2.1 自动建 worktree = harness 强制，非模型擅自

后台会话系统提示词（二进制佐证 `already isolated. This is enforced: file edits in the shared check…`）：

> Before making any code changes, use the EnterWorktree tool to isolate your work…
> **This is enforced: file edits in the shared checkout are rejected until you isolate**

即不隔离就改不了文件。关闭方式：项目 `.claude/settings.json` 写 `{"worktree": {"bgIsolation": "none"}}`（二进制确认枚举仅 `"worktree"` / `"none"`），代价是并行后台会话失去隔离、会互相覆盖。

### 2.2 分支起点由 cwd 决定，baseRef 只是执行者

`~/.claude/settings.json` 现设 `{"worktree": {"baseRef": "head"}}`。二进制确认两档：

| 取值 | 语义 | 本仓库结果 |
|---|---|---|
| `baseRef==="head"` | 从 **cwd 的 HEAD** 开分支 | dag（18007e5） |
| `baseRef??"fresh"`（默认） | 从 `origin/<默认分支>` 开 | origin/master（39d7ab4，更旧） |

**两档都到不了 tune_v1。错的不是 baseRef，是 cwd。**

### 2.3 实测：会话级 `/fork` 与 Agent 工具子代理行为相反

| 机制 | cwd 行为 | 建不建 worktree | 验证 |
|---|---|---|---|
| **会话级 `/fork`** | **重置到主 checkout** | 建（从主目录当前分支起）✗ | 用户在 tune_v1 会话执行 `/fork`，新会话首条 `!pwd` = 主目录 |
| **agent view 从 `.claude/worktrees/X` 起** | **继承 X** | **不建，原地写** | 后台会话「bubble sort script」把 `bubble_sort.py` 写进 `oat-optuna-blend` 根目录，`git worktree list` 无新增 |
| **agent view 从主目录起** | 主 checkout | 建（从主 checkout 当前分支起） | **未实测，机制推断**（cwd=主目录 → baseRef head） |
| **Agent 工具 `subagent_type: "fork"`** | **继承当前 worktree** | 不适用（子代理不建） | 探针回报 `PWD=…/worktrees/oat-optuna-blend`、`BRANCH=worktree-oat-optuna-blend`、分支特有文件存在 |
| **Agent 工具 `general-purpose`** | **继承当前 worktree** | 不适用 | 同上，逐行一致 |

探针命令：

```bash
echo "PWD=$(pwd)"; echo "BRANCH=$(git branch --show-current)"; echo "HEAD=$(git log --oneline -1)"
test -f <该分支特有文件> && echo "存在" || echo "不存在"
```

### 2.4 「已隔离」的判定是**路径前缀**，认 `.claude/worktrees/`

隔离指令带例外条款：

> Before making any code changes, use the EnterWorktree tool… — **unless your cwd is already under
> `.claude/worktrees/`, in which case you're already isolated.**

命中时提示词整段换成：

> Edit files directly in your working directory — this session is configured to work in place
> rather than isolating into a worktree. Skip EnterWorktree unless the user explicitly asks…

**实证**：本会话 cwd = `.claude/worktrees/oat-optuna-blend`，收到的正是后一句；而 `bgIsolation`
在用户级 / 项目级 / worktree 级 settings 里**均未设置**（仅 `~/.claude/settings.json` 有
`{"worktree":{"baseRef":"head"}}`）——故该措辞不是配置来的，是路径判定触发的。

**已实证**（§2.6）：`Trade_Strategy-tune_v1` 是手工 `git worktree add` 的、**不在** `.claude/worktrees/` 下，
从它启动的后台 agent **不会**被判「已隔离」，确实新建了 worktree，且基线取 tune_v1 的 HEAD。

### 2.5 HEAD 是 per-worktree 的（git 铁律，已实证）

同一仓库三个目录跑 `git rev-parse HEAD` 得三个值：

```
Trade_Strategy                      HEAD=18007e5  branch=dag
Trade_Strategy-tune_v1              HEAD=dc7c67f  branch=tune_v1
.claude/worktrees/oat-optuna-blend  HEAD=0086b7d  branch=worktree-oat-optuna-blend
```

各有独立 git-dir（`.git` / `.git/worktrees/<名>`），只共享 object 库（`--git-common-dir` 三者相同）。
故 `baseRef: head` 的「current local HEAD」= **执行时所在目录的 HEAD**，不是主 checkout 的。

**已坐实**（§2.6 的区分实验）：EnterWorktree 读的是 **cwd 的 HEAD**，不是主 checkout 的。

### 2.6 区分实验：在 tune_v1 起后台 agent 让它写代码

任务「在根目录创建 py 文件，在其内写冒泡排序」。会话自报「先建隔离 worktree，再写文件」，
创建 `worktree(bubble-sort)` → 分支 `worktree-bubble-sort`，
路径 `/home/yu/PycharmProjects/Trade_Strategy/.claude/worktrees/bubble-sort`。

git 判定：

```
worktree-bubble-sort  HEAD = c73c405（唯一提交：冒泡排序）
merge-base(它, tune_v1) = dc7c67f   ← 正是 tune_v1 的 HEAD
tune_v1 是它的祖先？ 是   领先 tune_v1  1 个提交
dag     是它的祖先？ 否   领先 dag     20 个提交
```

**cwd（tune_v1, dc7c67f）≠ 主 checkout（dag, 18007e5），结果落在 tune_v1 上**——
两种解释被彻底分开，一次证明两件事：

1. 用户自建 worktree 确实触发隔离（不在 `.claude/worktrees/` 前缀下 → 不算已隔离）。
2. `baseRef: head` 读的是 **cwd 的 HEAD**。

**意外细节——路径与基线锚在不同地方**：新 worktree 落在**主 repo 根**的 `.claude/worktrees/` 下，
不是 `Trade_Strategy-tune_v1/.claude/worktrees/`。即：

- **路径**锚在主 repo 根（`git-common-dir` 的父目录）
- **基线**锚在 cwd 的 HEAD

这解释了为何 CC 建的 worktree 全聚在主目录下，不论从哪儿发起。

## 三、结论

**根因只有一个：基线取自 cwd 的 HEAD，而 cwd 未必是你以为的地方。**

```
会话级 /fork  →  cwd 强制重置到主 checkout  →  baseRef=head  →  从主 checkout 当前分支开 worktree
                （父会话在哪个 worktree 无关，无法规避）
agent view    →  cwd = 启动它的那个位置       →  从该位置的分支开（或已在 .claude/worktrees/ 下则不开）
Agent 子代理  →  继承派发它的会话的 cwd       →  不建 worktree，无此问题
```

### 3.0 三选二矩阵（已被 `/branch` 推翻，保留作沿革）

⚠ 早期版本把「从目标 worktree 起 agent view」当成 `/fork` 的规避手段——**错**：
agent view 起的是**空白上下文**会话，丢掉的恰恰是 fork 的理由，不构成替代。
随后据此断言「三个属性任取其二、取不满三个」，存在一个空格。
**该断言已被 §3.3 推翻**——空格一直有东西，只是当时不知道 `/branch` 存在。

| 手段 | 继承上下文 | cwd 在目标 worktree | 独立会话 |
|---|---|---|---|
| **会话级 `/fork`** | ✓ | ✗（强制回主 checkout） | ✓ |
| **agent view 从目标 worktree 起** | ✗（空白） | ✓ | ✓ |
| **`Agent` 工具 `subagent_type: "fork"`** | ✓ | ✓ | ✗（子代理，靠 `SendMessage` 沟通） |
| **会话级 `/branch`** ★ | ✓ | ✓ | ✓ |

**★ `/branch` 三样全占**——正确入口是它，`/fork` 在 worktree 里是坏选项。


### 3.2 全场景 × 全操作 行为矩阵（速查）

图例：**✅实测** = 本次会话直接验证过；**〔推断〕** = 由已验证机制推出、未直接测。
「主 repo 根」= `/home/yu/PycharmProjects/Trade_Strategy`。

| 场景（会话 cwd） | 前台会话改代码 | **后台**会话改代码 | `/fork` | **`/branch`** | agent view / `claude --bg` 起新后台会话 | `Agent` 工具子代理 |
|---|---|---|---|---|---|---|
| **主 checkout**<br>`Trade_Strategy`（现停 dag） | 直接写主 checkout，无隔离〔推断〕 | 写入被拒 → 建 `主repo根/.claude/worktrees/<名>`，**基线 = dag 的 HEAD** ✅实测（本次事故） | 留在主 checkout（本来就在）〔推断〕 | cwd 不动〔推断〕 | 新会话 cwd = 主 checkout；改代码时同左建 worktree〔推断〕 | 继承主 checkout〔推断〕 |
| **内嵌 worktree**<br>`.claude/worktrees/X`（CC 自建） | 直接写 X | 判**「已隔离」→ 原地写 X，不建新 worktree** ✅实测 | **cwd 重置到主 checkout** ✅实测（回显 `runs in the origin tree`） | **cwd / 分支 / 工作树全不动**，新 session id 落**同一** project 目录 ✅实测（§3.3） | 新会话 cwd = X → 同样判已隔离 → **原地写 X** ✅实测（bubble sort script） | **继承 X** ✅实测（双探针） |
| **独立 worktree**<br>`Trade_Strategy-tune_v1`（手工 `git worktree add`） | 直接写 tune_v1 | **不算已隔离** → 建 `主repo根/.claude/worktrees/<名>`，**基线 = tune_v1 的 HEAD** ✅实测（§2.6） | **cwd 重置到主 checkout** ✅实测（用户测试） | cwd 不动〔推断，同内嵌〕 | 新会话 cwd = tune_v1 → 改代码时同左建 worktree ✅实测（§2.6 即由此发起） | 继承 tune_v1〔推断〕 |

**读表要点：**

1. **`/fork` 这一列是唯一的红格**——三种场景全部把 cwd 打回主 checkout，且**无法规避**。
   其余每列都「你在哪就在哪」。**`/branch` 是它的安全对位**。
2. **两个独立的锚点**：CC 建 worktree 时，**路径**恒锚主 repo 根的 `.claude/worktrees/`（不论从哪发起），
   **基线**恒取 cwd 的 HEAD。故「从 tune_v1 发起」建出的 worktree 落在主 repo 目录下，血脉却是 tune_v1 的。
3. **「已隔离」判定认路径前缀**：只有 `.claude/worktrees/` 下算。独立 worktree（第三行）因此比内嵌
   worktree（第二行）多一层隔离——**不是给它加保护，是 CC 认不出那是隔离**。
4. **前台会话不受隔离约束**：`# Background Session` 提示词块仅在 `CLAUDE_CODE_SESSION_KIND==="bg"` 注入。
5. **无论哪一格，`git worktree add` 只带已提交状态**——未提交的编辑永不跟随（§4.2）。

### 3.3 实测：`/branch` 不动 cwd（本 worktree 内执行）

在 `worktree-oat-optuna-blend` 会话里执行 `/branch test`，回显：

```
Branched conversation "test". You are now in the new branch (session 620b1b69-…).
Use /resume b5de96d9-… ("混乱") to return to the original,
or run `claude -r b5de96d9-…` in a new terminal.
```

新会话内实测：

```
PWD    = /home/yu/PycharmProjects/Trade_Strategy/.claude/worktrees/oat-optuna-blend   ← 没动
BRANCH = worktree-oat-optuna-blend                                                    ← 没动
```

三条独立证据：

1. `pwd` / `git branch --show-current` 与 branch 前完全一致。
2. 新会话 scratchpad 路径 slug = `…--claude-worktrees-oat-optuna-blend`（worktree），非主 checkout。
3. **新旧两 session 的 transcript 落在同一个 project 目录**——CC 按 cwd 给 project 目录命名，同目录即同 cwd：
   `~/.claude/projects/-home-yu-PycharmProjects-Trade-Strategy--claude-worktrees-oat-optuna-blend/{620b1b69,b5de96d9,d9db1219}.jsonl`

对照 `/fork`：回显 `runs in the origin tree`，transcript 落到主 checkout 的 project 目录。

**并行性澄清**（早期版本说错）：`/branch` 后两个 session 各有独立 id，**都可随时拉起并行推进**；
「你走进新分支、原件待命」只是分岔那一刻的状态，不是永久约束。两者真实差异只剩一条——
**副本是不是 bg session**：`/fork` 是（吃 cwd 重置 + 自动 worktree），`/branch` 不是。

⚠ 未测：`/resume` 一个 session 时 cwd 从哪来（会话记录 vs resume 时所在目录）。
从 project 目录按 cwd 分桶看，会话应记着自己的 cwd——但属推断。


## 四、实践取舍

**worktree 并行 ⊻ fork 开箱即用**，二选一，没有两全：

- **保留 worktree 并行** → fork 必然错位，只能靠人工/规则对基线。
- **想让 fork 正常** → 在主目录直接切分支工作，放弃 worktree 隔离。
  （git 禁止同一分支在两个 worktree 同时 checkout，所以主 checkout 无法停在已被 worktree 占用的分支上。）

要开后台 agent 时的正解：**先 `cd` 到正在工作的 worktree 再起**（`cd Trade_Strategy-tune_v1 && claude`，然后 agent view / `/bg`）。这对 `/fork` 无效——fork 一律回主目录。

### 4.1 `baseRef` 是配置层的静默单点故障

自动建 worktree（第 4 步）**本身也是独立的分叉风险源**，只是当前配置躲过了：

| `worktree.baseRef` | 从哪开分支 | 在 tune_v1 里建 worktree 的结果 |
|---|---|---|
| **`head`（现设置，非默认）** | cwd 的 HEAD | tune_v1 ✓ |
| **`fresh`（默认）** | `origin/<默认分支>` | **origin/master（39d7ab4，远落后）✗** |

即：**默认配置下第 4 步一定分叉，且无视你在哪个 worktree。** 两个风险源不对称——
第 2 步（`/fork`）无论怎么配都分叉，没有设置能救；第 4 步只要 `baseRef` 保持 `head` 就安全。
**一旦该键被删或回落默认，所有后台 agent 静默改从 origin/master 起。**

### 4.2 血脉正确 ≠ 拿到全部工作：未提交改动不跟随

`git worktree add` 只带**已提交**状态。即便正确地从 tune_v1 的 HEAD 建 worktree，
tune_v1 里那些**未提交**的编辑（tune-gates SKILL.md 红线、scan-wide.py、scan_tune.py、
extract_skeleton 修复、bb_v1 的 peak_age/毒药闸字段）**仍然不会过去**。
「起对分支」和「拿到全部工作」之间还差一次 commit——这正是本次事故更隐蔽的另一半。

### 4.3 同一 worktree 多会话 → 隔离机制失效

「cwd 在 `.claude/worktrees/` 下就算已隔离」这条规则**默认一个 worktree 只有一个会话**。
但 agent view 能不断往同一个 worktree 塞新后台会话，每个都被判「已隔离」，于是**全都在同一份
工作树上写**——隔离在此处形同虚设。

已实际发生：`worktree-oat-optuna-blend` 上前后有三个会话在写——本会话、被叫停的兄弟会话
（提交了 `93ed044` tune_v1 merge 与 `0086b7d` 执行 plan Task 1）、以及测试用的 bubble sort 会话。

## 五、拟定的 CLAUDE.md 规则（尚未写入，待拍板）

> 用户裁定（2026-08-23）：**不需要多层容错**。原先列的「查基线 / 验路径 / 禁 merge」
> 三项都是分叉的**下游后果**——分支起对了就不会发生，把后果当并列风险项等于把一个根因数了四遍。
> 一条规则即可切断整条链，而且**几乎零代价**：`/branch` 完全覆盖 `/fork` 的用途（§3.0 / §3.3）。

```markdown
**worktree 里用 `/branch`，不用 `/fork`**（实测 2026-08-23）：
`/fork` 把副本送进**后台会话**，后台会话的 cwd 一律重置到主 checkout，于是
`baseRef=head` 从主 checkout 当前分支开 worktree——结果是**记忆来自这个 worktree、
文件来自另一个分支**（§〇）。`/branch` 不产生后台会话，cwd / 分支 / 工作树全不动，
新会话独立且可与原会话并行——继承上下文、cwd 正确、独立会话，三样全占。

**派后台 agent 前先 commit**：`git worktree add` 只带已提交状态，未提交的编辑不会跟到
新 worktree。这是 git 常识、非容错措施。
```

（可选、非必需：`~/.claude/settings.json` 的 `worktree.baseRef` 保持 `"head"`；回落默认
`"fresh"` 会让后台 agent 静默改从 `origin/master` 起。见 §4.1。）


## 六、本次事故的实际后果（已查明）

- **研究内容未失真**：tune_v1 的结论通过 fork 继承的对话上下文进入，引用准确（新研究引 `bo_only=随机基线`，与台账 0.471 / 0.470 一致；`plateau.py` 的「容差 = 峰值处 se」「各年区间求交集」细节与真实文件相符）。
- **但派给 agent 的「必读文件」路径当时全部失效**：dag 上不存在 `.claude/skills/tune-gates/SKILL.md`、`docs/research/2026-08-20_tune-bb-v1/结论与台账.md` 等，agent 靠绕到 tune_v1 的绝对路径才拿到。**这是派发时未验证路径的失误。**
- **缺口后被 merge `93ed044`（tune_v1 → 本分支）补上**，同样未经用户许可。
- **`tune_v1` 分支本身未被污染**：HEAD 仍是 `dc7c67f`，不含本分支任何提交。
- 附带发现：本地 `tune_v1` 领先 `origin/tune_v1` 9 个提交（feature-study 双维去簇那条线），**一直未 push**，与云端无关。
