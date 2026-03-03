# CLAUDE.md
## 🚀 上下文获取 (Context & Navigation)
**开始任务前，根据需求读取对应文档：**
- **了解进度/查找模块** → `docs/system/current_state.md` (开发状态索引)
- **理解架构/业务逻辑** → `docs/system/PRD.md` (项目需求与设计)
- **查看具体设计细节** → `docs/modules/specs/` (各模块详细设计与架构意图)

## 代码地图 (Code Map)
- `BreakoutStrategy/` (核心包)
  - `analysis/`: 技术分析核心 (突破检测, 特征计算, 质量评分)
  - `signals/`: 绝对信号系统 (4 种信号检测器, 聚合排序)
    - `detectors/`: 信号检测器 (BO, HV, VR, BY)
  - `simple_pool/`: MVP 观察池 (即时判断模型, 4 核心参数)
  - `UI/`: 交互式 UI
    - `panels/`: UI 面板组件
    - `dialogs/`: 对话框组件
    - `editors/`: 参数编辑器
    - `charts/`: 图表渲染与绘图组件
    - `managers/`: 业务逻辑管理器 (扫描管理)
    - `config/`: 配置管理系统
- `configs/`: 配置文件
  - `signals/`: 信号检测配置 (absolute_signals.yaml)
- `datasets/`: 美股历史数据存储
  - `pkls/`: 股票历史数据 (Pickle格式)
- `scripts/`: 运行脚本
  - `backtest/`: 回测脚本 (simple_backtest.py)
  - `signals/`: 信号扫描脚本 (scan_signals.py)
- `docs/`: 项目文档库

## 数据存放 (Data Storage)
- **美股历史数据**: `datasets/pkls/` (可用于分析与回测的美股 .pkl 文件)
- **调试数据**: `datasets/test_pkls/` (可用于debug的样例数据)

## 开发环境 (Development Environment)
- **包管理**: 强制使用 `uv` 管理 Python 环境与依赖。
- **操作**: 优先使用 `uv add`, `uv run`, `uv sync` 等命令维护 `pyproject.toml`。

## 编码规范 (Coding Standards)
- **核心原则**: 奉行第一性原理 (First Principles) 和奥卡姆剃刀 (Occam's Razor) 原则。重视探寻需求的本质，避免过度设计，解决方案应简洁有效。采用渐进式复杂度，先实现基础功能，再逐步优化。
- **语言**: 界面显示用英文，代码注释/文档内容用中文。
- **Docstrings**: `__init__.py` 需包含模块概述；类/函数需说明用途、参数及算法逻辑。
- **术语**: breakout/bo (突破点), peak/pk (峰值/凸点)
- **文档输出**: 若用户未指定输出目录，请遵循以下规则：
  - **临时计划/分析**: `docs/tmp_plans/`
  - **代码解释**: `docs/explain/`
  - **研究报告**: `docs/research/`

## 🤖 代理工作流 (Agent Workflow)
- **自动代理规划**: 当被要求使用子代理执行任务时，如果没有明确的指定，那么根据任务的复杂度和子问题独立性等因素自行分析任务需要的子代理类型和数量。
- **自定义代理路由 (Custom Agent Routing)**: 遇到复杂推导或分析任务时，**除非用户指定特定代理**，否则需先评估任务难度：
  - **中高难度 (Tom)**: 适用于深度调研、架构审查、逻辑分析及大多数系统设计任务。当问题定义明确但需要深度挖掘时使用。
  - **极高难度 (Tommy)**: 仅用于极度复杂、需要第一性原理思考、创新算法设计或涉及极多变量权衡的难题。当常规分析可能不足以解决问题时使用。
- **代理协作 (Agent Collaboration)**: 对于需要多个 Tommy 代理协同工作的任务，默认情况下在完成工作时，主代理会整合各个子代理的输出，给用户汇总后的摘要结果，并且将具体分析内容保存为报告
