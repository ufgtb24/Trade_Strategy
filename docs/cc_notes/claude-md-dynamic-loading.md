---
title: CLAUDE.md 内容动态化：何时迁成按需加载、怎么迁、实测边界
scope: CLAUDE.md / .claude/rules 里的常驻指令何时该迁成按需加载（rules `paths:` / skill / hook additionalContext），三种触发信号各自的实测边界（Read 才触发、subagent 生效、skill 靠相关性判断），"读者是谁"的判据，以及常驻指令漏召回的失败模式（含 paths: 与省 context 纪律互相拆台）。与 vision-nonvision-models.md 互斥（那份是具体一条指令的迁出实例）。
category: hooks-skills-plugins
---

# CLAUDE.md 内容动态化

## 判据（改 CLAUDE.md 前先过一遍）

三个必答，答不上来就留常驻：

| 问题 | 答案决定 |
|---|---|
| **读者是谁**——主会话、subagent、还是独立启动的后台 session？ | 后台 session 只读 CLAUDE.md，没人替它调 skill → 只能常驻或 hook |
| **场景开始的信号是什么** | 文件路径 → rules `paths:`；用户口径词 → skill；工具/生命周期事件 → hook；都没有 → 常驻 |
| **到位时机来不来得及** | rules 在 Read 时才注入，"建文件前该怎么命名"这类指导会来晚 → 用 skill（任务开始即加载） |

值得迁的内容 = **长 且 少用**（例：agent team 约定 20 行、五次 session 用一次）。又短又常用的迁了只有代价没有收益。

**长 且 常用**（例：术语表）是第四格，三种机制都不理想：`paths:` 被 Bash 读法绕过（见「## 冲突」）、skill 靠相关性判断召回不保证、hook 要挑得出事件。这一格该常驻，但**常驻的是内容本身、不是「记得去查」那句指令**——例：`path2/CONTEXT.md` 45 个词头，**只列词头不含释义仅 766 字节**，常驻它就能在自造词之前撞见正确的词，释义仍走 grep。

## 三种机制的最小写法

### rules `paths:`（按文件路径）

```markdown
---
paths:
  - "docs/research/**"
  - "path2_web/**"
---
# 规则标题
正文……
```

- 放 `.claude/rules/<name>.md`；没有 `paths:` 的 rule 与 CLAUDE.md 同批无条件加载
- glob 相对 repo root；`dir/**` 匹配目录下所有文件；支持 `{ts,tsx}` 展开

### skill（按用户口径词）

```markdown
---
name: agent-team
description: Use when 用户说「agent team」「团队」「teammates」——在 spawn 任何 teammate 之前必读。
---
```

- description 只写触发条件、用用户会说的词，不总结流程（写了流程 Claude 会照 description 干、跳过正文）
- CLAUDE.md 留一句"用户说 X 时必须先调 Y skill"当召回兜底，别删

### hook additionalContext（按事件）

`SessionStart` / `PreToolUse` / `PostToolUse` 等事件的脚本 stdout 可注入上下文。适合"没有词也没有路径、但有可观测状态"的场景，例：后台 agent 的 worktree 都在 `.claude/worktrees/agent-*` → SessionStart 检查 `$PWD` 注入交付约定。成本是多一个 hook，7 行以内的常驻内容不值得。

## 实测边界（2026-08-27，三个 subagent 各测一次）

| 触碰方式 | rules `paths:` 是否注入 |
|---|---|
| Read 工具读匹配文件 | **是**（主会话与 subagent 都是） |
| Write 工具新建匹配文件 | **否** |
| Bash 里 cat / sed 触碰 | **否** |

- 官方原文 "trigger when Claude reads files" 是字面意思：只有 Read
- 非 fork subagent 自己 Read 时按同一逻辑触发；fork 直接继承父会话已加载的规则；内置 Explore/Plan agent 跳过 CLAUDE.md 那批
- 迁出后每处都要 GREEN 实测：起一个 subagent 给场景，看它是否主动调 skill / 是否收到注入

## 踩坑：读者认错

把「后台 agent 交付约定」迁成 skill，触发词写成"用户说后台 agent"——但用户从不这么说（用 agent view / `←` / `/fork` 起），且真正需要这条的是后台 session 自己，它启动只读 CLAUDE.md，看到"派发前先调 skill"不会用到自己身上。当场还原成常驻。教训：先问读者是谁，再问触发词。

## 踩坑：召回靠自觉（术语表案例）

**现象**：项目 `CLAUDE.md` 有一条常驻纪律「输出里提到领域概念时，用 `CONTEXT.md` 里定下的那个词」，`path2/CONTEXT.md` 里 45 个词头齐全（引用槽 / 复合事件 / 事件流 / 物化 / instance_id …）。一次跨 4 个 agent、几十轮的技术讨论中，主会话与 3 个 teammate **一个都没查过词表**，全程用自造词（「对象引用」「容器」「贴身份」）解释，直到用户指出读不懂。

三条独立失败源，少任何一条都不会全漏：

1. **判据里含一个需要先分类的词。** 纪律写的是「提到**领域概念**时」。当时讲的是引擎内部四步流程，被主观归类成「实现细节」，纪律就没触发——而词表实际收了这些词（「引用槽」= `ref_slots`/`ref_ids`，「复合事件」= `child_slots`）。**触发条件本身需要一次判断，判断错了这条纪律等于不存在。**
2. **另一条指令把方向带反。** 用户的「白话解释」被额外理解成「少用专有名词」，于是主动去术语化、自造替代词。而词表里的词本身就是白话，比自造词更准。**两条常驻指令在同一处冲突而没有裁决规则时，模型会选错边。**
3. **漏召回按 agent 数倍乘。** 派 teammate 的 prompt 写了工具调用纪律、写了实测优先、写了归档路径，**没写一个字要求用词表**。「按 agent 数倍乘」是动态化的收益，反过来手动 pull 的漏召回也一样倍乘。

**修法**：在 CLAUDE.md 里把「白话 ≠ 少用专有名词、词表里的词优先用」写死，并明确「动笔讲机制前先 grep 一遍词表」。**但这仍是靠自觉的 pull**——为什么不能靠 `paths:` 兜底，见下节。

## 冲突：省 context 纪律 vs rules `paths:`

`paths:` 只认 **Read 工具**（见「## 实测边界」）。而「读文件省上下文：先 grep/glob 定位，再 Read 用 `offset`/`limit`」这类纪律，会让 agent 用 Bash 的 `grep`/`sed` 代替 Read 去看代码——**越守省 context 的纪律，越收不到 `paths:` 注入**。两条配置互相拆台，且都不会报错。

实例：上面那轮讨论里 `path2/dag/engine.py`、`core.py`、`nodes.py`、`spec.py`、`_solve.py` 全部用 Bash grep/sed 读，**一个都没走 Read**。即使当时给 `path2/**` 挂了 rule，也一次都不会触发。

**判据**：给一个「agent 会用 Bash 看」的目录挂 `paths:` rule ≈ 无效。`paths:` 只对**会走 Read 工具**的文件有效——通常是需要整段读的文档，不是被 grep 定点取用的代码。

## 原理（一句话版）

- 省 token ≈ 0：常驻内容走 prompt cache，按缓存价计费
- 真收益 = 到位时机（注入点贴近使用点，长 session 里比开头的系统提示更近）+ 允许写全（不占常驻预算）+ 按 agent 数倍乘（每个 subagent 都加载一遍 CLAUDE.md）
- 真代价 = 召回不保证（skill 靠相关性判断、rules 只认 Read）+ 每处要实测
