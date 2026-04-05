# 文档重构方案（v3）

> 本方案取代 v2。核心变化：严格区分 `.claude/docs/`（AI 上下文，长期、只反映当前代码）与 `docs/`（用户文档，临时、可删）。IMPL 文档整体迁入 `.claude/docs/modules/`，`current_state.md` 整体删除，`update_doc` 由 slash command 拆分为**两个独立的 skill**：`update-ai-context` 维护 `.claude/docs/`，`write-user-doc` 写 `docs/`。

---

## A. 用户观点评估

| # | 用户意见 | 评估 | 结论 |
|---|---------|------|------|
| A.5 | `current_state.md` 整体删除，模块清单并入 `system_outline.md` | v1 仅"砍历史日志、保留清单"是半吊子。模块清单只是若干行表格，不值得独立文件，并入 outline 后 AI 一次读入即获得完整概览，减少一次文件跳转 | **采纳** |
| A.6 | IMPL 也放 `.claude/docs/modules/`，统一 AI 入口 | 已确认 `.gitignore` 不排除 `.claude/`，现有 `.claude/agents/`, `commands/`, `rules/`, `skills/` 全部已纳入 git。IMPL 放 `.claude/docs/modules/` 完全安全，且语义上 IMPL 就是"AI 读代码前的先验"，本就该和其它 AI 上下文放一起 | **采纳** |
| A.7 | 不要"未实现模块清单" | 这是旧 PRD 最大的失败点——12 个模块里 4 个从未实现却占据大量篇幅。`.claude/docs/` 的契约是"只反映现在"，未来清单属于用户的 PM 类文档（可放 `docs/research/`），不属于 AI 上下文。**进一步**：连"探索性但未形成固定流程"的子模块（observation / daily_pool / simple_pool / signals / shadow_pool / backtest）也一并排除，避免未来维护者误以为它们是系统的一部分 | **采纳** |
| C | CLAUDE.md 只暴露 `.claude/docs/`；"文档输出"段落移入 skill 描述 | CLAUDE.md 每次 session 都全量加载，必须最精简。文档输出路径规则只有在运行 `update-context` skill 时才相关，自然应下沉到 skill 描述 | **采纳** |
| D | `system_outline.md` 只列已实现、无"已实现"标签（默认就是） | 符合"默认即现状"的奥卡姆原则，标签是冗余信息 | **采纳** |
| E | `update_doc` 改为 skill；功能解耦为"AI 上下文"与"用户文档"两类 | slash command 不会被按需加载（但 skill description 只占几行索引，真正触发时才加载正文）。更重要的是解耦：AI 上下文文档有严格格式契约（精炼、反映代码），用户文档格式自由，两者混在一起会互相污染 | **采纳** |
| E' | 进一步拆分为两个独立 skill | 两个功能除了"写 markdown"外无共享逻辑：输出目录不同、内容约束不同、触发场景不同、读者不同。合并在一个 skill 内需要 Claude 每次先做 if/else 分流，还要读对方的约束噪声。拆成两个 skill 让 description 精确匹配意图，Claude 直接路由到正确的 skill | **采纳** |

---

## B. 目录结构（新）

```
.claude/
  docs/                          # AI 上下文，长期、只反映当前代码状态
    system_outline.md            # 系统概览（项目定位 + 数据流 + 模块表 + 术语表）
    modules/                     # 各模块架构意图（从 docs/modules/specs/ 迁入，去编号）
      突破扫描模块.md
      数据挖掘模块.md
      新闻情感分析.md
      交互式UI.md
  skills/
    update-ai-context/           # 维护 .claude/docs/ 下的 AI 上下文文档
      SKILL.md
    write-user-doc/              # 生成 docs/ 下的用户文档（研究/解释/临时）
      SKILL.md
  agents/                        # 不变
  rules/                         # 不变
  commands/                      # 保留目录，删除 update_doc.md
docs/                            # 用户文档，临时、可删
  research/                      # 保留：研究报告
  explain/                       # 保留：人类阅读的代码解释
  tmp/                           # 新建：临时计划（合并 plans/ + tmp_plans/）
  setup/                         # 保留：环境搭建等静态文档
  superpowers/                   # 保留：外部 skill 衍生物
```

**被完整移除**：
- `docs/system/` 目录（PRD + current_state 全部删除）
- `docs/modules/` 目录（IMPL 迁走后空壳，连带删除）
- `docs/plans/` 与 `docs/tmp_plans/`（合并为 `docs/tmp/`）
- `.claude/commands/update_doc.md`（被 skill 取代）

---

## C. 文件操作清单

执行顺序自上而下，所有涉及已追踪文件的移动用 `git mv` 保留历史。

| # | 操作 | 命令 |
|---|------|------|
| 1 | 创建 AI 上下文根目录 | `mkdir -p .claude/docs/modules` |
| 2 | 迁移 4 个核心 IMPL（同时去编号前缀与 `_IMPL` 后缀） | `git mv docs/modules/specs/02_突破扫描模块_IMPL.md .claude/docs/modules/突破扫描模块.md`；其余 3 个：`12_交互式UI_IMPL.md`→`交互式UI.md`、`15_数据挖掘模块_IMPL.md`→`数据挖掘模块.md`、`16_新闻情感分析_IMPL.md`→`新闻情感分析.md` |
| 3 | 删除未实现 PLAN | `git rm docs/modules/specs/01_数据层_PLAN.md` |
| 3b | 删除非核心模块 IMPL | `git rm docs/modules/specs/14_Simple_Pool_IMPL.md`（simple_pool 在独立任务中删除） |
| 4 | 删除空目录 | `rmdir docs/modules/specs docs/modules` |
| 5 | 删除旧 system 文档 | `git rm docs/system/PRD.md docs/system/current_state.md` 然后 `rmdir docs/system` |
| 6 | 新建 system_outline | `touch .claude/docs/system_outline.md`（内容见 E 节） |
| 7 | 合并临时计划目录 | `mkdir -p docs/tmp`；如 `docs/plans/` 或 `docs/tmp_plans/` 有活跃文件则 `git mv` 至 `docs/tmp/`；然后删除空的 `docs/plans/` 和 `docs/tmp_plans/` |
| 8 | 删除旧 slash command | `git rm .claude/commands/update_doc.md` |
| 9 | 创建两个 skill 目录 | `mkdir -p .claude/skills/update-ai-context .claude/skills/write-user-doc`，各写入 `SKILL.md`（内容见 F 节） |
| 10 | 改写 `CLAUDE.md` | 覆写为 D 节模板 |
| 11 | 初次填充 outline | 调用 `update-ai-context` skill 执行一次 outline 刷新 |

**重命名前置检查**：执行 #2 前，先 `grep -rn "docs/modules/specs"` 确认没有其它文档硬编码引用旧路径；若有，在此次提交中一并修正。

**与非核心模块删除的配套关系**：本方案假设 `docs/research/module-dependency-analysis.md` 清单中的非核心模块（`signals/`, `backtest/`, `shadow_pool/`, `simple_pool/`, `daily_pool/`, `observation/` 等）将在**独立任务**中被删除。文档重构可在删除之前或之后执行，但两者必须配套——只有非核心代码被删除后，`system_outline.md` 和代码地图里"4 个核心模块"的描述才与代码库实际状态完全一致。

---

## D. 新 CLAUDE.md 模板

```markdown
# CLAUDE.md

## 上下文入口
开始任务前，按需阅读：
- 系统概览（项目定位 / 数据流 / 已实现模块 / 术语表）→ `.claude/docs/system_outline.md`
- 某个模块的架构意图 → `.claude/docs/modules/<模块名>.md`

注：`.claude/docs/` 下的文档只反映当前代码状态，不含历史、不含未实现模块。
需要更新这些文档时，运行 `update-ai-context` skill。
需要生成面向人类阅读的研究报告 / 代码解释 / 临时计划时，运行 `write-user-doc` skill。

## 代码地图
- `BreakoutStrategy/` — 核心策略包
  - `analysis/` — 突破检测、因子计算、质量评分
  - `mining/` — 因子阈值挖掘 + 模板组合生成
  - `news_sentiment/` — 新闻情感分析
  - `UI/` — 交互式界面（批量扫描、参数编辑、图表浏览）
- `configs/` — YAML 配置（`params/`, `scan_config.yaml`, `ui_config.yaml`, `news_sentiment.yaml`, `api_keys.yaml`）
- `datasets/pkls/` — 美股历史数据（Pickle）
- `scripts/` — 运行入口脚本

## 开发环境
- 包管理：`uv`（`uv add` / `uv run` / `uv sync`）

## 编码规范
- 原则：第一性原理 + 奥卡姆剃刀，反对过度设计
- 语言：界面英文，注释/文档中文
- Docstrings：`__init__.py` 含模块概述；类/函数说明用途、参数、算法逻辑
- 术语：breakout/bo（突破点）, peak/pk（峰值/凸点）
- 入口脚本：不使用 argparse，参数声明在 `main()` 起始位置

## 代理工作流
- 复杂推导/分析任务默认使用 `tom` agent（Opus）
- Agent team 模式下全员 `tom`，最终结论归档 `docs/research/`
```

行数：约 28 行。相比原 61 行的 CLAUDE.md，砍掉了：
- 过时的多级代码地图（AI 可以 `ls` 获取）
- 文档输出路径规则（下沉到 skill）
- 数据存放段落（并入代码地图）

---

## E. 新 system_outline.md 模板

```markdown
# System Outline

> 突破选股策略系统 — 美股量化交易，自动识别阻力位突破并驱动观察/交易流程。
>
> 本文档只反映当前代码状态。不含历史演进、不含未实现模块。需要更新时运行 `update-ai-context` skill。

## 核心数据流

```
历史 K 线
   │
   ▼
[analysis] 凸点识别 → 突破检测 → 多因子质量评分
   │                                ↑
   │                          因子阈值 + 模板
   │                                │
   │                   [mining] 因子阈值挖掘 + 模板组合生成
   ▼
模板组合过滤（用 mining 产出的模板对 analysis 的突破打分过滤）
   │
   ▼
[news_sentiment] 新闻情感分析过滤
   │
   ▼
[UI] 展示股票 + 批量扫描 + 模板过滤操作
```

`analysis` 产出突破和评分，`mining` 挖掘阈值并生成模板回写 configs，`news_sentiment` 提供情感过滤，`UI` 作为用户入口驱动全流程。

## 模块

| 模块 | 代码目录 | 文档 | 职责 |
|------|---------|------|------|
| 突破扫描 | `BreakoutStrategy/analysis/` | [modules/突破扫描模块.md](modules/突破扫描模块.md) | 凸点识别 + 突破检测 + 多因子质量评分 |
| 数据挖掘 | `BreakoutStrategy/mining/` | [modules/数据挖掘模块.md](modules/数据挖掘模块.md) | 因子阈值优化 + 模板组合生成 + Trial 物化 |
| 新闻情感 | `BreakoutStrategy/news_sentiment/` | [modules/新闻情感分析.md](modules/新闻情感分析.md) | 多源采集 + LLM 分析 + 时间衰减聚合 |
| 交互式 UI | `BreakoutStrategy/UI/` | [modules/交互式UI.md](modules/交互式UI.md) | 批量扫描、参数编辑、模板过滤、图表浏览 |

> 添加/更新模块文档：运行 `update-ai-context` skill。

## 术语

| 术语 | 含义 |
|------|------|
| breakout / bo | 突破点（价格有效穿越阻力位的 K 线） |
| peak / pk | 凸点，即被识别的阻力位 |
| level | 因子评级（离散化后的因子档位） |
| factor | 评分因子（由 `FACTOR_REGISTRY` 统一注册） |
| trial | 挖掘流水线的一次参数组合实验 |
```

**关键设计点**：
- 无"已实现"列（默认就是）
- 无"计划中模块"段落
- 术语表从 PRD 迁入，是 PRD 中唯一值得保留的长期信息
- **范围严格**：outline 只描述 4 个固定功能模块；探索性/已废弃的子模块不出现在本文档，符合"只反映当前代码状态"的硬约束
- 所有核心模块都有独立 IMPL 文档，无需 docstring fallback

---

## F. 新 skill 设计：双 skill 拆分

两个功能除了"写 markdown"外无共享逻辑。拆为两个独立 skill：
- `update-ai-context` — 维护 `.claude/docs/` 下的 AI 上下文（严格契约）
- `write-user-doc` — 生成 `docs/` 下的用户文档（格式自由）

Claude 根据对话语义匹配 description，直接路由到正确的 skill，无需二次分流。

---

### F.1 `update-ai-context` skill

**文件**：`.claude/skills/update-ai-context/SKILL.md`

```markdown
---
name: update-ai-context
description: Refresh AI context documents in .claude/docs/ — module architecture summaries in .claude/docs/modules/ and the system overview in .claude/docs/system_outline.md. Use when the user asks to "update AI docs", "refresh outline", "提炼模块意图", "update context for module X", or after code changes make existing AI context stale.
---

# Update AI Context Skill

维护 `.claude/docs/` 下的 AI 上下文文档。这些文档**只反映当前代码状态**，是 Claude 下次 session 的先验知识。

## 硬性约束

- ❌ 不写历史演进、不写"之前是 X 现在是 Y"
- ❌ 不写未实现模块、未来计划、TODO
- ❌ 不抄贴函数签名/参数列表（代码本身就是事实）
- ✅ 只写当前代码的架构意图（Why 而非 What）
- ✅ 单个模块文件控制在 200 行以内
- ✅ `system_outline.md` 控制在 100 行以内

## 操作 A：更新单个模块文档

目标：从代码提炼架构意图，写入 `.claude/docs/modules/<编号>_<模块名>.md`。

流程：
1. 定位模块核心代码（`__init__.py` + 公共入口类）。
2. 若文件已存在则读取并增量更新，否则新建。
3. 提炼：
   - 核心流程（Mermaid 流程图）
   - 关键决策与理由（Why）
   - 对外 API / 依赖关系
   - 已知局限与边界
4. 顶部标注 `> 最后更新：YYYY-MM-DD`（无"已实现"标签）。
5. 同步更新 `.claude/docs/system_outline.md` 中该模块的行（若为新模块则追加）。

## 操作 B：刷新 system_outline

目标：重扫 `BreakoutStrategy/` 顶级目录，保证 outline 与代码一致。

流程：
1. `ls BreakoutStrategy/` 列出所有包目录。
2. 对比 outline 模块表：代码有但表里没的 → 追加；表里有但代码没的 → 删除；目录改名的 → 同步。
3. 数据流变化（新增/删除池）→ 更新数据流图。
4. 仅在出现新术语时追加术语表。

## 触发判定

- 用户明确说"更新模块 X"/"提炼 XX 的实现意图" → 操作 A
- 用户说"刷新 outline"/"同步系统概览"/"重新扫描模块" → 操作 B
- 代码结构刚发生变化（新增/删除/重命名模块）→ 主动建议运行操作 B
```

---

### F.2 `write-user-doc` skill

**文件**：`.claude/skills/write-user-doc/SKILL.md`

```markdown
---
name: write-user-doc
description: Generate user-facing documents under docs/ — research reports (docs/research/), code explanations for humans (docs/explain/), or temporary plans (docs/tmp/). Use when the user asks to "write a research report", "写研究报告", "explain this code", "save a temporary plan", "research this and save it", or otherwise produce human-readable documentation outside the AI context zone.
---

# Write User Doc Skill

生成 `docs/` 下面向人类阅读的文档。这些文档**临时**、**格式自由**、**用完可删**。

## 与 AI 上下文的边界

本 skill **绝不**写入 `.claude/docs/`。如果用户请求的是"维护 AI 上下文"/"刷新系统概览"，应使用 `update-ai-context` skill。

不确定时询问用户："这份文档是要作为 AI 的长期上下文（会持续维护），还是一次性的用户文档（用完可删）？"

## 输出目录选择

- `docs/research/` — 研究报告、架构审查、可行性分析、Agent team 研究结论（分析型，含推导过程、权衡、结论）
- `docs/explain/` — 代码解释、模块逻辑讲解，教学型（宏观 → 微观，含 Mermaid，循序渐进）
- `docs/tmp/` — 临时计划、设计草稿、待执行 TODO（自由型，可含尝试记录、未定决策）

## 允许的内容

- ✅ 历史演进、"曾经尝试过 X 但失败"
- ✅ 未来规划、待解决问题、多个备选方案
- ✅ 推导过程、思考脉络、权衡分析
- ✅ 非当前代码状态（研究报告就是某个时间点的快照）

## 命名建议

- research：`<主题>-<简述>.md` 或 `YYYY-MM-DD-<主题>.md`
- explain：`<模块名>_logic_analysis.md`
- tmp：`<日期>-<任务>.md`

## 流程

1. 根据用户意图判断输出目录（询问以消除歧义）。
2. 若为研究报告，结构建议：背景 → 分析 → 结论 → 建议。
3. 若为代码解释，结构建议：概览 → 流程图 → 宏观逻辑 → 微观细节 → 使用说明。
4. 若为临时计划，结构随意，重点是可执行性。
5. 写入文件，向用户确认保存路径。
```

---

### F.3 为什么拆成两个 skill 而非单个双功能 skill

- **description 匹配更精确**：每个 skill 描述单一目标，Claude 根据对话语义直接路由，无需在 skill 内部二次分流
- **加载更轻**：触发一个 skill 只加载自己的 SKILL.md，不会把另一半无关的约束也读进上下文
- **约束自洽**："严格 vs 自由"两套相反约束放在同一文件会互相污染，分开后每个 skill 内部一致
- **独立维护**：改一个 skill 不影响另一个
- **符合 Unix 哲学**：用户按意图选工具，而非学习工具内部的分支逻辑

两者共享的"写 markdown"能力是 Claude 的基础能力，不需要 skill 层面统一。

### F.4 为什么 skill 而非 slash command

- **加载时机**：skill 只在 session 启动时加载 description（约 1 行），调用时才读完整 SKILL.md；slash command 被引用即全量注入
- **触发方式**：skill 可根据对话语义自动路由；slash command 必须输入明确命令
- **适用场景**：文档维护是低频 + 含语义判定的操作，天然适合 skill 形态

---

## G. 风险与应对

| 风险 | 应对 |
|------|------|
| 迁移 IMPL 后旧路径硬编码引用残留 | 执行前 `grep -rn "docs/modules/specs" .` 全量检查，在同一提交中改完 |
| `git mv` 后 IDE/浏览器缓存失效导致链接报错 | 迁移完成后 `grep -rn "_IMPL.md"` 二次确认无残留引用 |
| `.claude/docs/` 与 `.claude/skills/` 职责混淆 | `.claude/docs/` 只放 md 文档；skill 放代码/流程；两者不互相引用内部实现 |
| skill 自动触发过度/误触发 | description 写得足够精确；不确定归属时强制向用户确认 |
| 删除 PRD 后丢失有价值的设计理由 | PRD 中唯一需要长期保留的是术语表，已迁入 outline；其余内容（曾经的模块规划、技术栈说明）属于历史，git log 保留足矣 |
| 合并 `docs/plans/` 和 `docs/tmp_plans/` 时文件重名 | 迁移前 `ls` 两个目录交叉比对；如有重名，以日期前缀重命名解决 |
| 新 skill 首次运行时 outline 是空的 | 迁移流程第 11 步显式调用 `update-ai-context` 的操作 B 初始填充 |
| 两个 skill 边界模糊（用户分不清该调哪个） | 两个 SKILL.md 都含"与另一方的边界"段落；不确定时强制向用户确认 |

---

## H. 执行摘要（TL;DR）

1. `.claude/docs/` = AI 的脑子，只装"当前代码长什么样"。
2. `docs/` = 人的笔记本，想写什么写什么，写完可以撕掉。
3. `CLAUDE.md` 只告诉 Claude 去 `.claude/docs/` 找答案，不再混杂输出路径规则。
4. `system_outline.md` = 项目定位 + 数据流 + 已实现模块表 + 术语表，一页纸看完全局。
5. 两个独立 skill：`update-ai-context` 维护 `.claude/docs/`（严格契约），`write-user-doc` 写 `docs/`（格式自由），互不污染，Claude 按 description 直接路由。
6. 被删除的：`PRD.md`, `current_state.md`, 未实现的 PLAN，slash command `update_doc`，空的 `docs/modules/` 和 `docs/system/`。
