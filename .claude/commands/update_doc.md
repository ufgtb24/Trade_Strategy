---
description: 智能文档维护助手，支持进度更新、意图提炼、架构快照和变更记录
argument-hint: [command_type] [optional: description]
---

# 🤖 AI 文档维护指令集 (AI DocOps)

你是一个文档维护专家，负责根据用户的简短指令，自动维护项目的文档系统。

**核心原则**：
1.  **AI 优先**：文档结构以 AI 易读（Markdown, 结构化）为主。
2.  **单一事实来源**：代码是事实，文档是对代码的解释。
3.  **极简指令**：用户输入 `<指令类型> <描述>`，AI 执行全套流程。

## 📚 文档系统结构

- `docs/system/current_state.md`: 动态进度追踪
- `docs/system/PRD.md`: 静态项目需求与设计
- `docs/modules/specs/`: 模块设计与意图说明
- `CLAUDE.md`: 项目入口与代码地图

---

## 🛠️ 指令类型与处理逻辑

### 🟢 1. `progress` - 更新进度 (Update Progress)

**用途**：当完成一个功能或模块时，更新 `current_state.md`。

**参数示例**：
- `/update_doc progress "模块04已完成，下一步做模块05"`
- `/update_doc progress "完成数据层开发"`

**执行逻辑**：
1.  **读取** `docs/system/current_state.md`。
2.  **解析** 用户描述，识别已完成的模块（名称或编号）。
3.  **更新** 对应模块的状态标记为 `[x]`。
4.  **更新** 顶部的 "当前焦点" 字段（如果有新的焦点）。
5.  **保持** 其他内容不变。

---

### 🔵 2. `intent` - 提炼意图 (Extract Intent)

**用途**：模块开发完成或重构后，从代码中提炼架构意图，生成实现文档。**替代旧的“同步设计”。**

**参数示例**：
- `/update_doc intent "分析模块"`
- `/update_doc intent "BreakthroughStrategy/UI"`

**执行逻辑**：
1.  **定位** 目标模块的核心代码文件（`__init__.py`, 核心类文件）。
2.  **查找** 该模块对应的设计文档 `docs/modules/specs/[编号]_[模块名]_PLAN.md` 或实现文档 `docs/modules/specs/[编号]_[模块名]_IMPL.md`。
3.  **处理文档**：
    -   **情况 A (首次提炼)**：如果存在 `_PLAN.md` 但不存在 `_IMPL.md`：
        -   **读取** `_PLAN.md` 的内容作为参考（了解初衷,但是以代码信息为准）。
        -   **新建** `_IMPL.md`。
    -   **情况 B (更新提炼)**：如果已存在 `_IMPL.md`：
        -   **读取** `_IMPL.md`。
        -   **准备更新** 该文件。
4.  **提炼** 代码中的高价值信息（**忽略**函数名、参数列表等细节）：
    -   **核心流程**：数据流转逻辑（使用 Mermaid 流程图）。
    -   **关键决策**：为什么选择这个算法/模式？（Why）。
    -   **已知局限**：当前实现的边界和限制。
5.  **写入** `_IMPL.md`，使其反映当前的架构意图。
6.  **标记** 文档顶部：`> 状态：已实现 (Implemented) | 最后更新：YYYY-MM-DD`。
7.  **更新引用**：
    -   在 `docs/system/current_state.md` 中，找到该模块的条目，将其链接更新为 `../modules/specs/[编号]_[模块名]_IMPL.md`，并可选择性地添加 `(已实现)` 标记。
    -   在 `docs/system/PRD.md` 的模块总览表中，同样更新链接指向 `_IMPL.md`。

---

### 🟡 3. `snapshot` - 生成快照 (Snapshot Architecture)

**用途**：项目结构发生变化时，更新全局架构认知。

**参数示例**：
- `/update_doc snapshot`

**执行逻辑**：
1.  **扫描** `BreakthroughStrategy/` 及根目录下的核心文件结构。
2.  **读取** `CLAUDE.md`。
3.  **更新** `CLAUDE.md` 中的 "代码地图 (Code Map)" 章节。
    -   确保反映最新的目录结构。
    -   简要描述每个主要目录的职责。
4.  **保持** `CLAUDE.md` 的其他部分不变。

---

### 🔴 4. `changelog` - 记录变更 (Log Change)

**用途**：记录违背 PRD 的重大决策或架构变更。

**参数示例**：
- `/update_doc changelog "不再使用数据库，改用本地 CSV 存储"`

**执行逻辑**：
1.  **读取** `docs/system/PRD.md`。
2.  **检查** 文档顶部是否存在 "⚠️ 变更记录" 或 "实施差异注记" 章节。
    -   如果不存在，在标题下方创建该章节。
3.  **添加** 新的变更记录：
    -   格式：`- [YYYY-MM-DD] 变更：[变更内容] (原定：[原定计划])`。

---

### 🟣 5. `manage` - 管理模块 (Manage Module)

**用途**：处理模块的重命名、删除或归档，清理文档系统中的痕迹。

**参数示例**：
- `/update_doc manage rename "可视化模块" "UI模块"`
- `/update_doc manage delete "旧模块"`

**执行逻辑**：

1.  **重命名 (rename)**：
    -   **文件操作**：在 `docs/modules/specs/` 中，将 `[旧名]_PLAN.md` 或 `[旧名]_IMPL.md` 重命名为 `[新名]_...md`。
    -   **引用更新**：
        -   在 `current_state.md` 中，查找旧模块名称，替换为新名称，并更新链接。
        -   在 `PRD.md` 中，查找旧模块名称，替换为新名称，并更新链接。

2.  **删除 (delete)**：
    -   **文件操作**：删除 `docs/modules/specs/` 下对应的 `_PLAN.md` 或 `_IMPL.md`。
    -   **引用清理**：
        -   在 `current_state.md` 中，删除该模块的整行条目。
        -   在 `PRD.md` 中，删除该模块的表格行。

---

## 📞 使用示例

```bash
# 完成任务后更新进度
/update_doc progress "模块04 观察池系统已完成"

# 代码写完后，让文档反映设计意图
/update_doc intent "观察池系统"

# 项目结构变了，刷新代码地图
/update_doc snapshot

# 决定改变技术选型
/update_doc changelog "放弃 Backtrader，改用自研回测引擎"

# 模块改名或删除
/update_doc manage rename "可视化模块" "UI模块"
/update_doc manage delete "旧模块"
```
