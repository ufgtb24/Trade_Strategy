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
