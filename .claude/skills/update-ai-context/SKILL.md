---
name: update-ai-context
description: Refresh the code map in CLAUDE.md — the per-layer boundaries, invariants and negative knowledge that are the AI's cold-start context. Use when the user asks to "更新 AI 文档" / "刷新代码地图" / "同步系统概览" / "提炼模块意图" / "update AI docs", or after code changes (new/removed/renamed module, layer boundary change) make the existing map stale.
---

# Update AI Context Skill

维护根目录 `CLAUDE.md` 的**「代码地图」节**——它是 Claude 下次 session 冷启动的唯一系统概览，
**只反映当前代码状态**。

术语表（`CONTEXT-MAP.md` → `path2/CONTEXT.md` / `path2_web/CONTEXT.md`）**不归本 skill 管**，
由 `/grill-with-docs` 维护；本 skill 也**绝不**写入 `docs/` 下的任何目录（那是 `write-user-doc` 的地盘）。

## 核心原则：文档写代码给不了的东西

文档和代码不是二选一，是**按信息类型分工**。判断每一句该不该进文档，只问一件事：

> **这句话会不会因为有人改个函数名、加个字段就变错？**

- **会 → 别写进文档，或改写到抗漂移的粗粒度。** 签名、字段名、字段数、阈值、枚举清单、工厂清单——这些"是什么"的事实，代码是唯一权威，`grep` 一下就能核实。文档去镜像它们**纯是负债**：一份**陈旧的镜像比没有更糟**——它会把冷启动的 reader 引向一个已经不存在的概念（如文档写 `class_id 注册表`，而 `class_id` 早就整体消灭了）。省略只是把 reader 送去代码（权威），镜像却把他送错。所以宁可用**指针**代替复刻：写「`c1_off` 的各个来源见 `_solve.py::compile_plan`」，别把那几条抄进来。
- **不会 → 这才是文档挣钱的地方，写准写透。** 为什么这么设计、什么**不变式**必须成立、模块**边界**在哪，以及**负知识**——"试过 X、会静默弄坏 Y""顶层 clause 恒 AND、别拆成平级 clause""改 INV-C 剪枝核心必须先 fuzz"。这些要么根本不在代码树里（理由散在早已消失的 commit / fuzz 结论里），要么要遍历一堆文件才能重建。**代码只说"有什么"，说不了"为什么"和"别做什么"。**

一句话：**Why / 不变式 / 边界 / 负知识 → 写；能一 grep 核实的 What → 指过去，别复刻。**

粒度推论：越细的内容（逐字段、逐签名）与代码耦合越紧、烂得越快；越粗的内容（边界、理由）越抗漂移。**别为了凑架构意图硬写**——某层若确实没有 why 可讲，一行边界 + 指向代码即可，不要注水。

## 机械约束

- ❌ 不写历史演进、不写"之前是 X 现在是 Y"（陈旧对比本身也会烂）
- ❌ 不写未实现模块、未来计划、TODO
- ❌ 不建新文档文件。这个仓库只有 `CLAUDE.md` + `CONTEXT.md` 两份 AI 上下文，**不要重新长出 `.claude/docs/` 那样的中间层**（2026-09-03 已整体删除，原因是它与 CLAUDE.md 大面积重叠且集体过时）
- ✅ 「代码地图」节 ≤ 60 行；`CLAUDE.md` 整体 ≤ 200 行。超了就是该往代码 docstring 沉，不是该新开文件
- ✅ 每层最多写一条不变式。第二条重要的，写进代码 docstring

## 操作：刷新 CLAUDE.md 的代码地图

目标：让「代码地图」节与当前代码一致，并且只留代码给不了的东西。

流程：

1. 列出各顶级包目录（`path2/` `path2_apps/` `path2_web*/` `scripts/` + 前身 `BreakoutStrategy/`），
   与地图逐行对比：代码有但地图没的 → 追加；地图有但代码没的 → 删除；目录改名的 → 同步。
2. **先抓漂移**：把地图里出现的每个代码标识符（类名 / 字段名 / 函数名 / 枚举 / 目录名 / 数量断言，
   如"唯一应用 X""per-role 诊断"）逐个回代码核实。对不上的，按核心原则处理——删掉、或改写成
   指针，**绝不原样留着**（陈旧镜像是本 skill 要消灭的头号目标）。
3. 增量补新内容时，每句同样过那道关：**"改名会不会烂？"** 会烂的换成指针或提到更粗的粒度。
4. 按此优先级提炼（越靠前越该写）：
   - **该层的边界**（它管什么、不管什么）；
   - **一条不变式或红线**（违反了会静默弄坏什么）；
   - **主链路**（数据/控制流走向，不画字段级细节）。
5. 若某层的 why 只对某个 skill 有用（如 detector 编写契约、app 声明契约），**下沉到那个 skill 的
   `reference.md`**，不要塞进代码地图。

## 触发判定

- 用户说"更新 AI 文档"/"刷新代码地图"/"同步系统概览"/"提炼 XX 的实现意图" → 执行上述操作
- 代码结构刚发生变化（新增/删除/重命名模块、层边界变动）→ 主动建议跑一次

## 与另外两个 skill 的边界

- 术语（某个词是什么意思）→ `/grill-with-docs` 维护 `CONTEXT.md`，本 skill 不碰
- 研究报告 / 代码解释 / 临时计划 → `write-user-doc` skill，本 skill 不写 `docs/`
