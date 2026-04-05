# 文档系统重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 AI 上下文文档迁入 `.claude/docs/`（长期、只反映现状），`docs/` 降级为用户临时文档区，`update_doc` slash command 拆分为 `update-ai-context` 和 `write-user-doc` 两个独立 skill，精简 CLAUDE.md。

**Architecture:** 严格区分两个文档空间——`.claude/docs/`（AI 永久上下文，严格契约：无历史、无未实现、只反映当前代码）与 `docs/`（用户文档：临时、可删、格式自由）。通过两个独立 skill 分别维护，CLAUDE.md 只指向 `.claude/docs/`，减少 session 启动开销。

**Tech Stack:** Markdown, Bash, Git（`git mv` 保留历史）

**参考规范**：本计划严格按照 `docs/research/doc-restructure-plan.md` v3 的目录结构、模板、操作清单执行。

---

### Task 1: 迁移 4 个核心 IMPL 到 `.claude/docs/modules/`

**Files:**
- Create dir: `.claude/docs/modules/`
- Rename (git mv): `docs/modules/specs/02_突破扫描模块_IMPL.md` → `.claude/docs/modules/突破扫描模块.md`
- Rename (git mv): `docs/modules/specs/12_交互式UI_IMPL.md` → `.claude/docs/modules/交互式UI.md`
- Rename (git mv): `docs/modules/specs/15_数据挖掘模块_IMPL.md` → `.claude/docs/modules/数据挖掘模块.md`
- Rename (git mv): `docs/modules/specs/16_新闻情感分析_IMPL.md` → `.claude/docs/modules/新闻情感分析.md`

- [ ] **Step 1: 创建目标目录**

```bash
mkdir -p .claude/docs/modules
```

- [ ] **Step 2: 用 git mv 迁移 4 个核心 IMPL（同时去编号与 `_IMPL` 后缀）**

```bash
git mv docs/modules/specs/02_突破扫描模块_IMPL.md .claude/docs/modules/突破扫描模块.md
git mv docs/modules/specs/12_交互式UI_IMPL.md .claude/docs/modules/交互式UI.md
git mv docs/modules/specs/15_数据挖掘模块_IMPL.md .claude/docs/modules/数据挖掘模块.md
git mv docs/modules/specs/16_新闻情感分析_IMPL.md .claude/docs/modules/新闻情感分析.md
```

- [ ] **Step 3: 验证 4 个文件已迁移**

```bash
ls .claude/docs/modules/
```

Expected:
```
交互式UI.md  新闻情感分析.md  数据挖掘模块.md  突破扫描模块.md
```

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "$(cat <<'EOF'
docs: 迁移 4 个核心 IMPL 到 .claude/docs/modules/

保留 git 历史，同时去掉文件名编号前缀和 _IMPL 后缀。
这是文档系统重构的第一步：.claude/docs/ 成为 AI 上下文的唯一入口。

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: 删除废弃文档（未实现 PLAN、非核心 IMPL、旧 system 文档）

**Files:**
- Delete: `docs/modules/specs/01_数据层_PLAN.md`
- Delete: `docs/modules/specs/14_Simple_Pool_IMPL.md`
- Delete: `docs/system/PRD.md`
- Delete: `docs/system/current_state.md`
- Delete empty dirs: `docs/modules/specs/`, `docs/modules/`, `docs/system/`

- [ ] **Step 1: 删除未实现的 PLAN**

```bash
git rm docs/modules/specs/01_数据层_PLAN.md
```

- [ ] **Step 2: 删除非核心模块 IMPL**

```bash
git rm docs/modules/specs/14_Simple_Pool_IMPL.md
```

- [ ] **Step 3: 删除旧 system 文档（PRD + current_state）**

```bash
git rm docs/system/PRD.md docs/system/current_state.md
```

- [ ] **Step 4: 清理空目录**

```bash
rmdir docs/modules/specs docs/modules docs/system 2>/dev/null
ls docs/modules docs/system 2>&1
```

Expected: `ls: cannot access 'docs/modules': No such file or directory`

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "$(cat <<'EOF'
docs: 删除废弃文档 (PRD, current_state, 未实现 PLAN, 非核心 IMPL)

PRD 和 current_state 充斥过时信息，术语表已迁入 system_outline。
01_数据层_PLAN.md 从未实现；14_Simple_Pool_IMPL.md 对应的 simple_pool
已不属于固定流程模块。

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: 删除旧 slash command 和过时的文档规范

**Files:**
- Delete: `.claude/commands/update_doc.md`
- Delete: `.claude/doc_write_standard.md`

- [ ] **Step 1: 删除 update_doc slash command**

```bash
git rm .claude/commands/update_doc.md
```

- [ ] **Step 2: 删除过时的文档写作规范**

`.claude/doc_write_standard.md` 引用 `modules/plans/`（已不存在），即将被两个新 skill 的 SKILL.md 取代，删除。

```bash
git rm .claude/doc_write_standard.md
```

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "$(cat <<'EOF'
chore(.claude): 删除旧 update_doc slash command 及过时文档规范

update_doc 将被拆分为 update-ai-context 和 write-user-doc 两个 skill。
doc_write_standard.md 的内容即将被 skill 的 SKILL.md 取代。

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: 创建 `update-ai-context` skill

**Files:**
- Create: `.claude/skills/update-ai-context/SKILL.md`

- [ ] **Step 1: 创建 skill 目录**

```bash
mkdir -p .claude/skills/update-ai-context
```

- [ ] **Step 2: 写入 SKILL.md**

Write to `.claude/skills/update-ai-context/SKILL.md`:

````markdown
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
- ✅ 模块文档文件名不使用数字编号前缀（直接用 `<模块名>.md`）

## 操作 A：更新单个模块文档

目标：从代码提炼架构意图，写入 `.claude/docs/modules/<模块名>.md`。

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
3. 数据流变化（新增/删除核心模块）→ 更新数据流图。
4. 仅在出现新术语时追加术语表。

## 触发判定

- 用户明确说"更新模块 X"/"提炼 XX 的实现意图" → 操作 A
- 用户说"刷新 outline"/"同步系统概览"/"重新扫描模块" → 操作 B
- 代码结构刚发生变化（新增/删除/重命名模块）→ 主动建议运行操作 B

## 与另一 skill 的边界

本 skill **绝不**写入 `docs/` 下的任何目录。如果用户请求的是"写研究报告"/"写代码解释"/"保存临时计划"，应使用 `write-user-doc` skill。
````

- [ ] **Step 3: 验证 skill 文件存在且格式正确**

```bash
test -f .claude/skills/update-ai-context/SKILL.md && head -5 .claude/skills/update-ai-context/SKILL.md
```

Expected: 显示 frontmatter 的前 5 行，包含 `name: update-ai-context`。

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/update-ai-context/
git commit -m "$(cat <<'EOF'
feat(skill): 新增 update-ai-context skill

维护 .claude/docs/ 下的 AI 上下文文档（模块总结 + system_outline）。
硬性约束：只反映当前代码状态，不写历史/未实现/TODO。

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: 创建 `write-user-doc` skill

**Files:**
- Create: `.claude/skills/write-user-doc/SKILL.md`

- [ ] **Step 1: 创建 skill 目录**

```bash
mkdir -p .claude/skills/write-user-doc
```

- [ ] **Step 2: 写入 SKILL.md**

Write to `.claude/skills/write-user-doc/SKILL.md`:

````markdown
---
name: write-user-doc
description: Generate user-facing documents under docs/ — research reports (docs/research/), code explanations for humans (docs/explain/), or temporary plans (docs/tmp/). Use when the user asks to "write a research report", "写研究报告", "explain this code", "save a temporary plan", "research this and save it", or otherwise produce human-readable documentation outside the AI context zone.
---

# Write User Doc Skill

生成 `docs/` 下面向人类阅读的文档。这些文档**临时**、**格式自由**、**用完可删**。

## 与 AI 上下文的边界

本 skill **绝不**写入 `.claude/docs/`。如果用户请求的是"维护 AI 上下文"/"刷新系统概览"/"提炼模块意图"，应使用 `update-ai-context` skill。

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
````

- [ ] **Step 3: 验证 skill 文件存在且格式正确**

```bash
test -f .claude/skills/write-user-doc/SKILL.md && head -5 .claude/skills/write-user-doc/SKILL.md
```

Expected: 显示 frontmatter 前 5 行，包含 `name: write-user-doc`。

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/write-user-doc/
git commit -m "$(cat <<'EOF'
feat(skill): 新增 write-user-doc skill

生成 docs/ 下的用户文档（research/explain/tmp），格式自由、临时可删。
明确与 update-ai-context skill 的边界：绝不写入 .claude/docs/。

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: 创建 `system_outline.md`

**Files:**
- Create: `.claude/docs/system_outline.md`

- [ ] **Step 1: 写入 system_outline.md**

Write to `.claude/docs/system_outline.md`:

````markdown
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
````

- [ ] **Step 2: 验证文件存在且内部链接有效**

```bash
test -f .claude/docs/system_outline.md
for f in 突破扫描模块 数据挖掘模块 新闻情感分析 交互式UI; do
  test -f ".claude/docs/modules/${f}.md" && echo "OK: ${f}.md" || echo "MISSING: ${f}.md"
done
```

Expected: 全部 4 个 `OK: ...`。

- [ ] **Step 3: Commit**

```bash
git add .claude/docs/system_outline.md
git commit -m "$(cat <<'EOF'
docs(.claude): 新增 system_outline.md

项目定位 + 核心数据流 + 4 个模块表 + 术语表，一页纸看完全局。
替代旧 PRD + current_state。严格反映当前代码，无历史、无未实现。

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: 重写 `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md` (完整覆写)

- [ ] **Step 1: 覆写 CLAUDE.md**

Write to `CLAUDE.md`:

````markdown
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
````

- [ ] **Step 2: 验证新 CLAUDE.md 不再引用旧路径**

```bash
grep -n "docs/modules/specs\|docs/system/PRD\|docs/system/current_state\|docs/tmp_plans" CLAUDE.md
```

Expected: 无输出（退出码非 0）。

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs: 重写 CLAUDE.md，指向 .claude/docs/

从 61 行砍到约 30 行：
- 上下文入口只指向 .claude/docs/
- 代码地图精简为 4 个核心模块（analysis/mining/news_sentiment/UI）
- 文档输出路径规则下沉到 write-user-doc skill
- 去掉过时的多级目录地图

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: 清理临时文档目录，创建 `docs/tmp/`

**Files:**
- Create dir: `docs/tmp/` (with `.gitkeep`)
- Delete empty dir: `docs/plans/` (确认为空后)

- [ ] **Step 1: 确认 docs/plans/ 为空**

```bash
find docs/plans -type f 2>/dev/null
ls docs/tmp_plans 2>&1
```

Expected: `docs/plans/` 无输出文件；`docs/tmp_plans/` 不存在（`No such file or directory`）。

- [ ] **Step 2: 删除空的 docs/plans/ 目录**

```bash
rmdir docs/plans 2>/dev/null && echo "removed" || echo "not empty or not exist"
```

Expected: `removed`。

- [ ] **Step 3: 创建 docs/tmp/ 并放入 .gitkeep**

```bash
mkdir -p docs/tmp
touch docs/tmp/.gitkeep
```

- [ ] **Step 4: Commit**

```bash
git add docs/tmp/.gitkeep
git commit -m "$(cat <<'EOF'
docs: 新建 docs/tmp/，删除空的 docs/plans/

docs/tmp/ 由 write-user-doc skill 用于写临时计划和设计草稿。

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: 终检 —— 确认无残留旧路径引用

**Files:**
- Read-only verification across entire repo

- [ ] **Step 1: 检查是否还有文件引用旧路径**

```bash
grep -rn "docs/modules/specs\|docs/system/PRD\|docs/system/current_state\|docs/tmp_plans\|_IMPL\.md\|update_doc\.md" --include="*.md" --exclude-dir=.git --exclude-dir=superpowers --exclude-dir=research 2>&1 | head -30
```

Expected: 无输出或仅匹配 `docs/research/doc-restructure-plan.md`（设计方案本身，合理）和 `docs/superpowers/plans/` 下的历史 plan（归档，合理）。

**如有其它匹配**：说明有文件硬编码引用了已删除路径，需要一一修正（`grep -l` 定位文件 → Edit 工具修正 → 补 commit）。

- [ ] **Step 2: 检查 .claude/docs/ 结构完整**

```bash
find .claude/docs -type f
```

Expected:
```
.claude/docs/system_outline.md
.claude/docs/modules/突破扫描模块.md
.claude/docs/modules/数据挖掘模块.md
.claude/docs/modules/新闻情感分析.md
.claude/docs/modules/交互式UI.md
```

- [ ] **Step 3: 检查两个 skill 都已注册**

```bash
ls .claude/skills/update-ai-context/SKILL.md .claude/skills/write-user-doc/SKILL.md
```

Expected: 两个文件都存在。

- [ ] **Step 4: 检查旧文件/目录已全部清理**

```bash
ls docs/modules docs/system .claude/commands/update_doc.md .claude/doc_write_standard.md 2>&1
```

Expected: 全部 `No such file or directory`。

- [ ] **Step 5: 检查 git 状态干净**

```bash
git status
```

Expected: `nothing to commit, working tree clean`（若 Task 1-8 都已 commit）。

- [ ] **Step 6: 如有终检发现的问题，修复并追加 commit**

如 Step 1 发现残留引用：

```bash
# 示例：某个 .md 文件还引用旧路径，修正后
git add <fixed_files>
git commit -m "$(cat <<'EOF'
docs: 清理遗留的旧路径引用

<简要说明哪些文件引用了什么旧路径，改成了什么>

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review Summary

### Spec 覆盖检查
- ✅ B 节目录结构：Task 1 创建 `.claude/docs/modules/`，Task 4/5 创建两个 skill 目录，Task 6 创建 system_outline，Task 8 创建 `docs/tmp/`
- ✅ C 节操作清单：Task 1 覆盖 #1-#2，Task 2 覆盖 #3-#5，Task 3 覆盖 #8，Task 4/5 覆盖 #9，Task 6 覆盖 #6，Task 7 覆盖 #10，Task 8 覆盖 #7
- ✅ D 节 CLAUDE.md 模板：Task 7 完整写入
- ✅ E 节 system_outline.md 模板：Task 6 完整写入
- ✅ F.1 `update-ai-context` SKILL.md：Task 4 完整写入（已修正为无编号前缀）
- ✅ F.2 `write-user-doc` SKILL.md：Task 5 完整写入
- ✅ G 节风险：Task 9 终检覆盖"旧路径残留"风险
- ⚠️  C 节 #11 "初次填充 outline" 由 update-ai-context 执行 —— 在本方案中 outline 由 Task 6 直接写入（内容来自 E 节模板），无需 skill 执行，因为 4 个模块文档已迁移且 outline 模板已定义完整。初次刷新作为 skill 的触发场景之一，待后续代码变更时再自动执行。

### Placeholder 扫描
- 无 TBD/TODO/fill in/Similar to Task N 等占位符
- 所有 bash 命令、文件内容均为完整可执行形式
- 每个 Task 都有明确的 verification step

### Type/路径一致性
- 4 个核心模块文件名在 Task 1（迁移）、Task 6（system_outline 链接）、Task 7（CLAUDE.md 示例）中完全一致：`突破扫描模块.md / 数据挖掘模块.md / 新闻情感分析.md / 交互式UI.md`
- 两个 skill 名在 Task 4/5（创建）、Task 7（CLAUDE.md 引用）、Task 6（system_outline 引用）中完全一致：`update-ai-context / write-user-doc`

### 已知偏差（与 spec v3 的微小差异）
- Spec C 节 #11 建议"调用 skill 初次填充"。本计划 Task 6 直接用 E 节模板写入 outline，跳过 skill 调用。原因：E 节已提供完整模板，直接写入更可靠；skill 是"维护"而非"首次填充"的工具。
- Spec C 节未提及删除 `.claude/doc_write_standard.md`，但该文件内容即将被两个新 skill 取代，属于"过时文档清理"的合理附加操作，已列入 Task 3。
