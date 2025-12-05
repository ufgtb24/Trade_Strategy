# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

---

## 📖 获取项目上下文

**开始任何任务前，请先阅读文档索引获取上下文**：
👉 **项目概览**：[docs/system/PRD.md](docs/system/PRD.md)

这个文档提供：
- 项目目标和核心策略
- 系统架构和模块划分
- 技术栈和成功标准
- 风险评估和术语表
---

👉 **首要入口**：[docs/system/current_state.md](docs/system/current_state.md)

这个文档提供：
- 当前开发状态（模块完成情况）
- 模块索引（快速定位到设计文档和代码位置）
- 下一步开发计划
- 研究报告索引

👉 **文档结构**：
   ```
   docs/
   ├── system/
   │   ├── PRD.md            # 项目需求文档（静态）
   │   └── current_state.md  # 开发状态索引（动态）
   ├── modules/
   │   ├── plans/           # 模块设计文档（开发前）
   └── research/            # 研究报告（子代理输出）
   ```




## 📝 编码规范

详见：[.claude/doc_write_standard.md](.claude/doc_write_standard.md#代码文档code-documentation)

**核心要求**：
- 模块级 docstring（`__init__.py`）：模块概述、主要类/函数、使用示例、设计文档链接
- 类级 docstring：用途、核心创新、使用场景
- 函数级 docstring：功能、参数、返回值、算法步骤
- 关键代码注释：中文注释，解释算法逻辑和设计决策

---

**最后更新**：2025-11-28
**核心原则**：
- 详细的 docstring 和注释
- 界面显示全部用英文
- 代码注释采用中文
- 文档内容采用中文

## 项目专属名词术语
- breakout = breakthrough = bt = 突破点
- peak = 峰值 =pk