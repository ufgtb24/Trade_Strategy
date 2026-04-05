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
