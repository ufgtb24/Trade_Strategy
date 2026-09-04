---
title: mattpocock grill-with-docs / domain-modeling 的 CONTEXT.md 读写触发机制
scope: mattpocock-skills 里 CONTEXT.md 的读 / 写触发全表（每条是内置还是要在 CLAUDE.md 自定义）、R1 因果循环、R1 只抓同词异义（词表在上下文也不纠正异词同义的实测）、四个外层封装谁补了读取前提、「读取挂在探索阶段」的结构性偏斜、claude -p 五臂对照实验的方法与数据。与 claude-md-dynamic-loading.md 互斥：那份讲 CLAUDE.md / rules 侧「常驻指令为什么漏召回」，这份讲 plugin 侧「skill 包自己有没有安排读取」。
category: hooks-skills-plugins
---

# mattpocock 词表（CONTEXT.md）读写触发机制

**一句话**：`domain-modeling` 是写表 skill——写表 4 条触发全内置；读表 10 条里能真正把词表搬进上下文的只有 2 条内置（探索前 / 用户按 `/wait-what`）。**而且词表进了上下文也不够**：它唯一的用户侧检查 R1 只抓同词异义，「用户用非正式同义词」「Claude 自造替代词」这两种最常见的漂移，读没读词表都没有条款管。「对齐对话用语」这件事只能在项目 CLAUDE.md 里自己补。

版本：mattpocock-skills 1.2.3 · Claude Code 2.1.260 · 实测 2026-09-04。

## 对策

| 状态 | 做法 | 治哪条失败源 |
|---|---|---|
| [已做] | 项目 `CLAUDE.md`「用户指令映射」节 4 条：白话 ≠ 少用专有名词 / 该回避的是没定义过的行话 / 回避办法是换成词表的词而不是自造 / 讲机制前先 grep 词头 | 「白话解释」被理解成去术语化（裁决规则）；对话格空缺（pull） |
| [未做] | **45 个词头（766 字节，只列词头不含释义）常驻 CLAUDE.md** | 唯一不依赖判断、不依赖触发的一条——词直接在上下文里，自造词之前就撞见；也是唯一直接作用于 Claude 生产端的一条（R1 / R2 只看用户输入，且不管异词同义）。判据见 `claude-md-dynamic-loading.md`「第四格」 |
| [升级后] | 重跑下面的实验，看上游有没有把「读词表」补进 `grill-with-docs` | — |

## 复现实验

```bash
bash "$(git rev-parse --show-toplevel)/docs/cc_notes/mattpocock-glossary-triggers-experiment.sh" \
  "$(git rev-parse --show-toplevel)" /tmp/glossary-exp
```

- 作用：起 3 个 fresh `claude -p` 会话（完整项目配置 / 多上下文无 CLAUDE.md / 单上下文无 CLAUDE.md），同一个故意全用野词的 prompt 走 `/grill-with-docs`，度量「有没有打开词表、第几次工具调用打开、输出用了哪些规范词」
- 前置：`claude` CLI 可用；源仓库有 `CONTEXT-MAP.md` + `path2/CONTEXT.md` + `path2_web/CONTEXT.md`；每臂约 2–4 分钟、并行跑
- 只读源仓库；证据留在输出目录（`*.jsonl` / `*.final.txt`），仓库副本跑完即删

## 读表触发（10 条）

「真」= 会产生一次实际读取（词表从磁盘进上下文）；「假」= 假定词表已在上下文、用它但不去取。

### 真·读触发

| # | 触发场景 | 出处 | 内置 / 自定义 |
|---|---|---|---|
| R3 | **探索代码库之前**读 `CONTEXT-MAP.md` + 各 `CONTEXT.md` | `docs/agents/domain.md`「Before exploring, read these」 | 内置模板（setup 装进项目侧，与 `setup-matt-pocock-skills/domain.md` 逐字相同），**靠 CLAUDE.md「Agent skills · Domain docs」的 "See" 指针才可达** |
| R6 | **用户**按 `/wait-what` → 用词表的词重讲（正文明写 "follow `CONTEXT-MAP.md` to the right one"） | `wait-what/SKILL.md` | 内置，但 `disable-model-invocation: true`——**Claude 调不了，只有用户能按** |
| R8 | 遇到不认识的词 → `grep` 查它指什么 | `CLAUDE.md`「上下文入口」节 | **纯自定义**（消费方向；捞不到「不知道自己不知道」的词） |
| R10 | **对话里讲机制之前** → 先 grep 一遍 45 个词头 | `CLAUDE.md`「用户指令映射」节 | **纯自定义**（2026-09-04 事后新增；唯一覆盖「对话」的一条） |

### 假·读触发

| # | 触发场景 | 出处 | 内置 / 自定义 | 问题 |
|---|---|---|---|---|
| **R1** | **用户**用了和词表冲突的词 → 当场指出 | `domain-modeling/SKILL.md`「Challenge against the glossary」 | 内置 | **条件本身不可求值——因果循环**；且只抓同词异义、不抓异词同义（见下两节） |
| R2 | **用户**用了模糊 / 重载的词 → 提出规范词 | `domain-modeling/SKILL.md`「Sharpen fuzzy language」 | 内置 | 条件可求值，但词表不在时会**自造**一个「规范词」，比不做更糟 |
| R4 | **书面产物**里命名领域概念（issue 标题 / 重构提案 / 假设 / 测试名）→ 用词表的词 | `docs/agents/domain.md`「Use the glossary's vocabulary」 | 内置模板，项目侧 | 只列书面产物，**对话回复不在其列**；没安排读取动作 |
| R5 | 写 spec → 通篇用词表的词 | `to-spec/SKILL.md` step 1 | 内置 | 靠同一步的 "Explore the repo" 间接接上 R3 |
| R7 | 定位有哪几个 context → 读 `CONTEXT-MAP.md` | `domain-modeling/CONTEXT-FORMAT.md`「Locating」 | 内置 | 该文件只在**写词条**时被链接到（SKILL.md「Update CONTEXT.md inline」） |
| R9 | 输出提到领域概念 → 用词表定的词 | `CLAUDE.md`「编码规范 · 术语」条 | 纯自定义 | 要先判断「算不算领域概念」（判错即失效）；只说「要用」没说「先查」 |

## 写表触发（4 条）

| # | 触发场景 | 出处 | 内置 / 自定义 |
|---|---|---|---|
| W1 | 一个术语被敲定 → **当场**写进去，明令 "Don't batch these up" | `domain-modeling/SKILL.md`「Update CONTEXT.md inline」 | 内置 |
| W2 | 词表不存在 → 第一个术语敲定时懒创建 | `domain-modeling/SKILL.md`「File structure」 | 内置 |
| W3 | ADR：难逆转 + 无上下文会困惑 + 真取舍，三条全满足才提议 | `domain-modeling/SKILL.md`「Offer ADRs sparingly」 | 内置 |
| W4 | 用户明确要求 | — | — |

**两表合看**：写表全内置、装上就有；读表 7 条内置里没有一条覆盖「Claude 在对话里解释」——R1/R2 只监听用户说话、R3 挂在探索阶段、R4/R5 限书面产物、R6 只有用户能按、R7 得先写才会读。

## 踩坑：R1 是因果循环

> "When the user uses a term that **conflicts with the existing language in `CONTEXT.md`**, call it out immediately."

要判断「冲突」，词表必须已在上下文里；R1 自己却不安排读取。

- 词表已在 → 只对**同词异义**能工作（下节实测），且它不是读触发，是在用已读到的东西
- 词表不在 → 条件无法求值，永远不触发

**失败时不报错**：「词表不在所以检测不出冲突」和「检查过了没冲突」行为完全一样——都是什么都不说。"During the session" 里排第一、最像在守词表的那条，恰恰是失效时最安静的。

这不是疏漏，是作者写明的架构假设（`domain-modeling/SKILL.md` 首段括号）：

> Merely *reading* `CONTEXT.md` for vocabulary is not this skill: that's a one-line habit any skill can do. **This skill is for when you're changing the model, not just consuming it.**

读取被外包给「随便哪个 skill 都能做的一行习惯」，而全包里承接这行习惯的只有项目侧的 `domain.md`，且限定在探索阶段。

## 踩坑：词表在上下文也不管用——R1 只抓同词异义，不抓异词同义

五臂全部读了词表；prompt 里故意用的野词（「身份字段」「身份字符串」「槽位」「容器声明核对」）在词表里都有对应词条（instance_id / 引用槽 / 复合事件的 child 槽）。结果：

| 臂 | 读了词表 | 沿用野词（甚至当小标题） | 输出里「引用槽」 | 「复合事件」 |
|---|---|---|---|---|
| A1 | ✅ | 「容器声明核对（C1/C2/C3）…」 | 0 | 1 |
| A2 | ✅ 两份 | 「身份字段：能沿用，但有三个洞」 | 0 | 0 |
| A3 | ✅ | 「身份字段照贴、引用照译、容器核对照做」 | 0 | 0 |
| A4 | ✅ | — | 0 | 0 |
| A5 | ✅ | 「身份字段：不是贴不贴的问题」「容器声明核对：三处照常成立」 | 4 | 0 |

没有一臂说「你说的容器声明核对，词表里叫复合事件的 child 槽校验」；写词表 0 次（第一轮只提问、未敲定术语，合理）。

原因不是触发失败，是**条款不存在**。R1 原文与例句：

> "…conflicts with the existing language… '**Your glossary defines "cancellation" as X, but you seem to mean Y**'"

抓的是**同词异义**（同一个词、意思与词表定义不同）。用户用非正式说法指代词表已有概念是**异词同义**——在 R1 不算「冲突」，在 R2 不算「模糊」（模型刚读完代码，「容器声明核对」对它足够精确）。`domain-modeling` 里没有任何一条管这个，读没读词表都一样。

**推论**（两个 skill 的全文就各一句）：

```
grill-me         = grilling
grill-with-docs  = grilling + domain-modeling
                 = grill-me + (W1–W3 写词表) + (R1 同词异义检测)
```

「Claude 用词表的词说话」和「用户用非正式同义词时纠正」都不在这个加法里。词表进上下文只补齐 R1 的前提，而 R1 管的事与术语漂移不是同一件。

## 踩坑：四个外层封装，只有一个补了 R1 的前提

`domain-modeling` 不由用户直接调，靠外层封装 "Call the Skill tool twice"。谁补了读取：

| 封装 | 读词表指令 | 原文位置 |
|---|---|---|
| `improve-codebase-architecture` | ✅ 显式无条件："**Read** the project's domain glossary (`CONTEXT.md`) and any ADRs in the area you're touching **first**." | `SKILL.md`「### 1. Explore」节下 |
| `triage` | ⚠️ 半条："Explore the codebase **using** the project's domain glossary"——说用没说读 | `SKILL.md` step 1「Gather context」 |
| `wayfinder` | ❌ 三处都只是 "Call the Skill tool twice" | — |
| **`grill-with-docs`** | ❌ 全文 35 词就一句调用；目录里除 `SKILL.md` 只有 `agents/openai.yaml` 界面清单 | — |

有读指令的两个是**要翻代码库**的 skill；没有的两个是**以对话为主体**的 skill。`grill-with-docs` 是 ask-matt 写的主 flow 第 1 步、四个里最需要 R1 的那个。

## 原理：读取挂在探索阶段，从不挂在对话上

全包唯一的读取入口（R3）和唯一补前提的封装（`improve-codebase-architecture`）都把指令放在 **"Explore"** 标题下；setup 装进项目的 `domain.md` 小标题也是 "Before exploring"——项目侧补丁原样继承了上游的偏斜。

平时**读取**有效：fresh session 被任务逼着探索代码库，读取顺带发生（五臂实验全读了）——但读取有效 ≠ 对齐有效，见上节。只在一种情况失效：**探索已在会话更早时发生过**。那时 `grill-with-docs` 进来没有任何一句话让 Claude 再读一次，R1 又假定已经读过——两边一撞。

作者的隐含前提是「对话和产物分开」（聊完 → `/to-spec` 才受词表约束，对话说岔了用户当场 `/wait-what`）。当对话本身就是设计载体、用户是唯一读者时，这条豁免正好豁免掉唯一要紧的部分。

## 证据：本次会话时间线（2026-09-04，session 921aaf5c）

| 行 | 事件 |
|---|---|
| 1–400 | agent team 研究（4 agent、几十轮），`CONTEXT.md` **零次触碰** |
| 413 | 唯一一次：`grep "stream\|流\|detector\|node" path2/CONTEXT.md`——pattern 对「引用槽」「复合事件」命中 0 |
| 437–447 | 用户调 `/grill-with-docs`，加载 grilling + domain-modeling |
| 479 | 用户问「白话解释」→ 自造词回答（「贴身份」「对象引用」「容器」） |
| 493 | 用户纠正术语 |
| 496–498 | grep 的是 `engine.py` / `core.py`——**仍没碰 CONTEXT.md**，对照表从代码符号造出、还在用「容器」 |
| 515–528 | 用户问「何时沉淀到 CONTEXT.md」后，**第一次真正打开**词表；发现「引用槽」「复合事件」「事件流」「物化」早已在里面 |

整条会话 Read 工具 **0 次**、Bash 65 次（52 次读文件）——`.claude/rules/` 的 `paths:` 只认 Read，在此会话结构性不可达（bypass 模式下 harness 还主动命令用 Bash 读文件，比省 context 纪律更硬）。3 个 teammate prompt 里 2 个没提词表。

## 证据：五臂对照数据（fresh `claude -p`，同一野词 prompt）

| 臂 | 配置 | 打开词表 | 第 N 次工具调用 / 总数 |
|---|---|---|---|
| A1 | 完整项目配置（CLAUDE.md + domain.md + 分级） | ✅ | 9 / 10 |
| A2 | 多上下文，无 CLAUDE.md | ✅ **两份都读** | 7 / 11 |
| A3 | 单上下文，无 CLAUDE.md | ✅ | 6 / 8 |
| A4 | 逐字复刻真实入口（有 final_report +「根据 final_report 实施」） | ✅ | 16 / 21 |
| A5 | 有 final_report + 设计措辞 | ✅ | 31 / 80 |

- **分级上下文（CONTEXT-MAP 多一跳）不是原因**：A2 vs A3 唯一差别是分级，结果一样
- **实施型入口也不是原因**：A4 逐字复刻仍读了
- 全部在探索扫描的**尾段**才读——读取行为挂在探索上，不挂在 skill 上
- 读了之后**仍全部沿用野词**、写词表 0 次——见「踩坑：词表在上下文也不管用」
- 脚本默认只跑 A1–A3（A4/A5 依赖会话特定的 final_report，不可移植）
