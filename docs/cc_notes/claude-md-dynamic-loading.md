---
title: CLAUDE.md 内容动态化：何时迁成按需加载、怎么迁、实测边界
scope: CLAUDE.md / .claude/rules 里的常驻指令何时该迁成按需加载（rules `paths:` / skill / hook additionalContext），三种触发信号各自的实测边界（Read 才触发、subagent 生效、skill 靠相关性判断），以及"读者是谁"的判据。与 vision-nonvision-models.md 互斥（那份是具体一条指令的迁出实例）。
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

## 原理（一句话版）

- 省 token ≈ 0：常驻内容走 prompt cache，按缓存价计费
- 真收益 = 到位时机（注入点贴近使用点，长 session 里比开头的系统提示更近）+ 允许写全（不占常驻预算）+ 按 agent 数倍乘（每个 subagent 都加载一遍 CLAUDE.md）
- 真代价 = 召回不保证（skill 靠相关性判断、rules 只认 Read）+ 每处要实测
