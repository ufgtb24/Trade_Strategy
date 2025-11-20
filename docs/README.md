# 文档系统说明

**用途**：AI 获取项目文档结构和索引的入口

---

## 核心入口

**primary**: [system/current_state.md](system/current_state.md)
- 模块完成状态（已完成/待开发）
- 下一步开发计划
- 研究报告索引

**secondary**: [system/PRD.md](system/PRD.md)
- 项目概述和核心策略
- 系统架构和模块划分
- 术语表

---

## 文档结构

```
docs/
├── README.md              # 文档系统说明
├── system/
│   ├── PRD.md            # 项目需求文档（静态）
│   └── current_state.md  # 开发状态索引（动态）
├── modules/
│   ├── plans/           # 模块设计文档（开发前）
│   ├── README.md        # 模块文档说明
└── research/            # 研究报告（子代理输出）
```

## 文档类型

| 文档类型 | 位置 | 何时创建 | 何时更新 |
|---------|------|---------|---------|
| PRD.md | system/ | 项目初期 | 很少 |
| current_state.md | system/ | 项目初期 | 频繁 |
| 模块设计 | modules/plans/ | 开发前 | 设计调整时 |
| 研究报告 | research/ | 研究完成后 | 很少 |
| 代码文档 | 代码中 | 开发时 | 代码修改时 |

**获取已完成模块信息的方式**：
1. **开发前**：阅读 `plans/XX_模块名设计.md`（接口定义、算法伪代码、数据结构）
2. **开发后**：
   - 查看代码位置（如 `BreakthroughStrategy/analysis/`）
   - 阅读模块 `__init__.py` 的 docstring（模块概述）
   - 阅读关键类的 docstring 和注释（实现细节）
   - 运行示例脚本（如 `scripts/visual_demo.py`）

**更新 current_state.md 时机**：
- 模块开发完成（使用 `/update_doc module` 命令）
- 重大架构调整
- 研究报告生成（可选）

---

## 相关路径

- 代码仓库：`/home/yu/PycharmProjects/Trade_Strategy/BreakthroughStrategy/`
- 主配置：`CLAUDE.md`
- 手动更新命令：`.claude/commands/update_doc.md`

---

**版本**：v3.0（代码即文档）
**更新日期**：2025-11-28
