# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

---

## 📖 获取项目上下文

**开始任何任务前，请先阅读文档索引获取上下文**：

👉 **首要入口**：[docs/system/current_state.md](docs/system/current_state.md)

这个文档提供：
- 当前开发状态（模块完成情况）
- 模块索引（快速定位到设计文档和代码位置）
- 下一步开发计划
- 研究报告索引

👉 **完整导航**：[docs/README.md](docs/README.md)

这个文档提供：
- 文档体系说明
- 按场景查找文档的指南
- 文档管理规则

👉 **项目概览**：[docs/system/PRD.md](docs/system/PRD.md)

这个文档提供：
- 项目目标和核心策略
- 系统架构和模块划分
- 技术栈和成功标准
- 风险评估和术语表

---

## 🚀 开发工作流

### 任务开始前

1. **读取索引**：查看 [current_state.md](docs/system/current_state.md) 了解当前状态
2. **判断任务类型**：
   - **模块开发** → 阅读 `docs/modules/plans/XX_模块名设计.md`
   - **已完成模块的修改** → 阅读设计文档 + 代码（使用 Grep/Read 工具）
   - **研究型问题** → 委托给研究型子代理（输出到 `docs/research/`）
3. **获取相关上下文**：根据索引指引，阅读相关设计文档和代码实现

### 任务执行中

**模块开发流程**：
```
设计文档 (modules/plans/) → 代码实现（详细注释） → 完成
```

**研究型问题流程**：
```
复杂问题 → 委托子代理 → 研究报告 (research/)
```

**修改已完成模块**：
- 查看设计文档了解原始设计意图
- 使用 Grep/Read 工具阅读代码和注释
- 代码是唯一的真实来源

### 自动更新文档的规则
**plan mode 运行结束**：
请你弹出选项，询问是否保存计划文档("是/否")
   - 选择"否"：
      不创建任何文档

   - 选择"是"：继续弹出选项，询问保存方式
      - 选项1: 临时文档
            如果选择此项, 则将 plan 的内容作为临时文档保存到 `docs/tmp_plans`：
      - 选项1: 正式 module 设计文档
            如果选择此项, 则将 plan 的内容作为正式设计文档保存到 `docs/modules/plans/`，可以通过直接调用 "/update_doc plan 创建设计文档" 命令实现。



**模块开发完成**：
2. 更新 `docs/system/current_state.md` 标注模块完成状态（使用 `/update_doc module` 命令）

**研究工作完成**：
1. 子代理在 `docs/research/` 创建研究报告
2. 可选：更新 `current_state.md` 添加研究报告索引

**重大架构调整**：
1. 更新对应的设计文档
2. 更新代码注释反映新架构
3. 更新 `current_state.md` 的架构说明

---

## 💡 子代理使用

### 研究型子代理 solution-architect
**何时使用**：
任何需要深入分析或调研的任务，如：
- 算法对比研究（如 SMA vs EMA）
- 技术选型调研（如 Backtrader vs 自研回测）
- 数据分析报告（如回测结果分析）
- 架构方案评估

**不使用的场景**：
- 简单的代码查找（使用 Grep/Glob）
- 临时推理（直接回答）
- 代码实现（主代理负责）

**输出要求**：
- 保存到 `docs/research/` 目录
- 文件名格式：`YYYYMMDD_研究主题.md`
- 内容：只保存结论和建议，不保存试错过程

---

---

## 📝 编码规范

详见：[.claude/doc_write_standard.md](.claude/doc_write_standard.md#代码文档code-documentation)

**核心要求**：
- 代码是唯一的真实来源，不再维护独立的总结文档
- 模块级 docstring（`__init__.py`）：模块概述、主要类/函数、使用示例、设计文档链接
- 类级 docstring：用途、核心创新、使用场景
- 函数级 docstring：功能、参数、返回值、算法步骤
- 关键代码注释：中文注释，解释算法逻辑和设计决策

---

**文档版本**：v4.1（统一编码规范）
**最后更新**：2025-11-28
**核心原则**：
- 代码是唯一的真实来源
- 详细的 docstring 和注释替代总结文档
- 界面显示全部用英文
- 代码注释采用中文
- 文档内容采用中文

## 项目专属名词术语
- breakout = breakthrough = bt = 突破点
- peak = 峰值 =pk