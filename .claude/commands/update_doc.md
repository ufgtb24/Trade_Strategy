---
description: 智能文档维护助手，支持意图提炼、架构快照和模块管理
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

### 🔵 1. `intent` - 提炼意图 (Extract Intent)

**用途**：模块开发完成或重构后，从代码中提炼架构意图，生成实现文档。**替代旧的“同步设计”。**

**参数示例**：
- `/update_doc intent "分析模块"`
- `/update_doc intent "BreakoutStrategy/UI"`

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

### 🟡 2. `snapshot` - 生成快照 (Snapshot Architecture)

**用途**：项目结构发生变化时，更新全局架构认知。

**参数示例**：
- `/update_doc snapshot`

**执行逻辑**：
1.  **扫描** `BreakoutStrategy/` 及根目录下的核心文件结构。
2.  **读取** `CLAUDE.md`。
3.  **更新** `CLAUDE.md` 中的 "代码地图 (Code Map)" 章节。
    -   确保反映最新的目录结构。
    -   简要描述每个主要目录的职责。
4.  **保持** `CLAUDE.md` 的其他部分不变。

---

### 🟣 3. `manage` - 管理模块 (Manage Module)

**用途**：处理模块的**创建**、重命名、删除或归档，维护文档系统的一致性。

**参数示例**：
- `/update_doc manage create "模块06" "高级回测模块"`
- `/update_doc manage rename "可视化模块" "UI模块"`
- `/update_doc manage delete "旧模块"`

**执行逻辑**：

1.  **创建 (create)**：
    -   **检查代码**：判断该模块的代码是否已存在。
    -   **分支处理**：
        -   **若代码已存在**：跳过创建 PLAN，直接调用 `intent` 逻辑提取代码意图生成 `_IMPL.md`。
        -   **若代码未存在**：在 `docs/modules/specs/` 中创建 `[编号]_[模块名]_PLAN.md`，写入标准设计模板（包含背景、目标、核心架构、接口设计等章节）。
    -   **引用更新**：
        -   在 `current_state.md` 中，追加新模块条目（若已实现则标记 `[x]` 并链接 `_IMPL.md`，否则 `[ ]` 链接 `_PLAN.md`）。
        -   在 `PRD.md` 的模块总览表中，追加新行。

2.  **重命名 (rename)**：
    -   **文件操作**：在 `docs/modules/specs/` 中，将 `[旧名]_PLAN.md` 或 `[旧名]_IMPL.md` 重命名为 `[新名]_...md`。
    -   **引用更新**：
        -   在 `current_state.md` 中，查找旧模块名称，替换为新名称，并更新链接。
        -   在 `PRD.md` 中，查找旧模块名称，替换为新名称，并更新链接。

3.  **删除 (delete)**：
    -   **文件操作**：删除 `docs/modules/specs/` 下对应的 `_PLAN.md` 或 `_IMPL.md`。
    -   **引用清理**：
        -   在 `current_state.md` 中，删除该模块的整行条目。
        -   在 `PRD.md` 中，删除该模块的表格行。

---

### 🟢 4. `explain` - 生成说明 (Explain Logic)

**用途**：为特定模块、功能或目录生成**面向人类阅读**的详细逻辑说明文档。**这是唯一的面向人类教学的文档指令**，需要以最有利于让人类快速接受新知识的方式去编写。

**参数示例**：
- `/update_doc explain "BreakoutStrategy/analysis/"`
- `/update_doc explain "UI模块"`

**执行逻辑**：
1.  **深入分析** 目标范围内的代码，理解其运行机制、数据流向和核心架构。
2.  **创建文件** 在 `docs/explain/` 目录下创建新文档，文件名应具有描述性（如 `[模块名]_logic_analysis.md`）。
3.  **编写内容**（**核心要求：宏观到细节，结构清晰**）：
    -   **概览 (Overview)**：一句话讲清楚这个模块/功能的作用。
    -   **流程图 (Flowchart)**：使用 Mermaid 绘制核心运行流程图。
    -   **宏观逻辑 (Macro Logic)**：解释模块的设计思想、在系统中的位置以及与其他模块的交互。
    -   **微观细节 (Micro Logic)**：对关键类 (Classes) 和函数 (Functions) 进行解释说明。重点解释“它做了什么”和“为什么这么做”，而不是单纯粘贴代码。
    -   **使用说明 (Usage)**：(如果适用) 简述如何配置或调用。
4.  **润色**：确保语言通顺，逻辑连贯，让人类可以迅速理解代码功能。

---

## 📞 使用示例

```bash
# 代码写完后，让文档反映设计意图
/update_doc intent "观察池系统"

# 项目结构变了，刷新代码地图
/update_doc snapshot

# 创建新模块
/update_doc manage create "模块06" "高级回测模块"

# 模块改名或删除
/update_doc manage rename "可视化模块" "UI模块"
/update_doc manage delete "旧模块"

# 生成人类易读的逻辑说明
/update_doc explain "BreakoutStrategy/analysis/"
```
