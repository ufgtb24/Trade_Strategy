# CLAUDE.md
## 🚀 上下文获取 (Context & Navigation)
**开始任务前，根据需求读取对应文档：**
- **了解进度/查找模块** → `docs/system/current_state.md` (开发状态索引)
- **理解架构/业务逻辑** → `docs/system/PRD.md` (项目需求与设计)
- **查看具体设计细节** → `docs/modules/specs/` (各模块详细设计与架构意图)

## 代码地图 (Code Map)
- `BreakoutStrategy/` (核心包)
  - `analysis/`: 技术分析核心 (突破检测, 特征计算, 质量评分)
  - `observation/`: Realtime 观察池 (加权评分模型, 5分钟级评估)
    - `strategies/`: 策略实现 (时间提供者, 存储策略)
    - `evaluators/`: 四维评估器 (时间窗口, 价格确认, 成交量, 风险)
  - `daily_pool/`: Daily 观察池 (阶段状态机模型, 日K级评估)
    - `models/`: 数据模型 (Phase, DailyPoolEntry, DailySignal)
    - `state_machine/`: 阶段状态机 (PhaseStateMachine)
    - `analyzers/`: 三维分析器 (价格模式, 波动率, 成交量)
    - `evaluator/`: 评估器 (DailyPoolEvaluator)
    - `manager/`: 池管理器 (DailyPoolManager)
    - `backtest/`: 回测引擎 (DailyBacktestEngine)
  - `mining/`: 数据挖掘 (因子注册, 统计分析, 阈值优化, 可执行入口)
  - `UI/`: 交互式 UI (原 visualization)
    - `panels/`: UI 面板组件
    - `dialogs/`: 对话框组件
    - `editors/`: 参数编辑器
    - `charts/`: 图表渲染与绘图组件
    - `managers/`: 业务逻辑管理器 (扫描管理)
    - `config/`: 配置管理系统
- `configs/`: 系统配置文件 (YAML)
  - `daily_pool/`: Daily 池配置
- `datasets/`: 美股历史数据存储
  - `pkls/`: 股票历史数据 (Pickle格式)
- `scripts/`: 运行脚本
  - `backtest/`: 回测脚本 (simple_backtest.py)
  - `visualization/`: 可视化演示脚本
- `docs/`: 项目文档库

## 数据存放 (Data Storage)
- **美股历史数据**: `datasets/pkls/` (可用于分析与回测的美股 .pkl 文件)

## 开发环境 (Development Environment)
- **包管理**: 强制使用 `uv` 管理 Python 环境与依赖。
- **操作**: 优先使用 `uv add`, `uv run`, `uv sync` 等命令维护 `pyproject.toml`。

## 编码规范 (Coding Standards)
- **核心原则**: 奉行第一性原理 (First Principles) 和奥卡姆剃刀 (Occam's Razor) 原则。重视探寻需求的本质，避免过度设计，解决方案应简洁有效。
- **语言**: 界面显示用英文，代码注释/文档内容用中文。
- **Docstrings**: `__init__.py` 需包含模块概述；类/函数需说明用途、参数及算法逻辑。
- **术语**: breakout/bo (突破点), peak/pk (峰值/凸点)
- **文档输出**: 若用户未指定输出目录，请遵循以下规则：
  - **临时计划/分析**: `docs/tmp_plans/`
  - **代码解释**: `docs/explain/`
  - **研究报告**: `docs/research/`

## 🤖 代理工作流 (Agent Workflow)
- **自动代理规划**: 当被要求使用子代理执行任务时，如果没有明确的指定，那么根据任务的复杂度和子问题独立性等因素自行分析任务需要的子代理类型和数量。
- **自定义代理路由 (Custom Agent Routing)**: 遇到复杂推导或分析任务时，**除非用户指定特定代理**，否则使用 `tom` agent（Opus 模型）。适用于深度调研、架构审查、逻辑分析、第一性原理思考、创新算法设计等各类复杂任务。
- **Agent Team**: 当使用 agent team 模式时：
  - **成员选择**: 默认采用 `tom` agent 作为所有团队成员（包括 leader）。
  - **结果归档**: 完成问题分析后，必须将最终研究结果沉淀为文档，并保存至 `docs/research/` 目录。
