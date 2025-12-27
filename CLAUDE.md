# CLAUDE.md
## 🚀 上下文获取 (Context & Navigation)
**开始任务前，根据需求读取对应文档：**
- **了解进度/查找模块** → `docs/system/current_state.md` (开发状态索引)
- **理解架构/业务逻辑** → `docs/system/PRD.md` (项目需求与设计)
- **查看具体设计细节** → `docs/modules/specs/` (各模块详细设计与架构意图)

## 🗺️ 代码地图 (Code Map)
- `BreakoutStrategy/` (核心包)
  - `analysis/`: 技术分析核心 (突破检测, 特征计算, 质量评分)
  - `observation/`: 观察池系统 (状态管理, 买入信号生成)
    - `strategies/`: 策略实现 (时间提供者, 存储策略)
  - `UI/`: 交互式 UI (原 visualization)
    - `panels/`: UI 面板组件
    - `dialogs/`: 对话框组件
    - `editors/`: 参数编辑器
    - `charts/`: 图表渲染与绘图组件
    - `managers/`: 业务逻辑管理器 (扫描管理)
    - `config/`: 配置管理系统
- `configs/`: 系统配置文件 (YAML)
- `scripts/`: 运行脚本
  - `analysis/`: 批量扫描脚本
  - `backtest/`: 回测脚本 (simple_backtest.py)
  - `visualization/`: 可视化演示脚本
- `docs/`: 项目文档库

## 📝 编码规范 (Coding Standards)
- **语言**: 界面显示用英文，代码注释/文档内容用中文。
- **Docstrings**: `__init__.py` 需包含模块概述；类/函数需说明用途、参数及算法逻辑。
- **术语**: breakout/bo (突破点), peak/pk (峰值/凸点)
- **文档输出**: 若用户要求输出研究/分析文档且未指定路径，默认保存在 `docs/research/`。

## 🤖 代理工作流 (Agent Workflow)
- **自定义代理路由 (Custom Agent Routing)**: 遇到复杂推导或分析任务时，**除非用户指定特定代理**，否则需先评估任务难度：
  - **中高难度 (Tom)**: 适用于深度调研、架构审查、逻辑分析及大多数系统设计任务。当问题定义明确但需要深度挖掘时使用。
  - **极高难度 (Tommy)**: 仅用于极度复杂、需要第一性原理思考、创新算法设计或涉及极多变量权衡的难题。当常规分析可能不足以解决问题时使用。
