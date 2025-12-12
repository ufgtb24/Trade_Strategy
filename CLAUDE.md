# CLAUDE.md
## 🚀 上下文获取 (Context & Navigation)
**开始任务前，根据需求读取对应文档：**
- **了解进度/查找模块** → `docs/system/current_state.md` (开发状态索引)
- **理解架构/业务逻辑** → `docs/system/PRD.md` (项目需求与设计)
- **查看具体设计细节** → `docs/modules/specs/` (各模块详细设计与架构意图)

## 🗺️ 代码地图 (Code Map)
- `BreakthroughStrategy/` (核心包)![img.png](img.png)
  - `analysis/`: 技术分析核心 (突破检测, 质量评分)
  - `UI/`: 交互式 UI (原 visualization)
    - `panels/`: UI 面板组件
    - `dialogs/`: 对话框组件
    - `editors/`: 参数编辑器
    - `charts/`: 图表渲染与绘图组件
    - `managers/`: 业务逻辑管理器
    - `config/`: 配置管理系统
- `configs/`: 系统配置文件 (YAML)
- `scripts/`: 运行脚本 (扫描, 演示, 测试)
- `docs/`: 项目文档库

## 📝 编码规范 (Coding Standards)
- **文档**: 界面显示用英文，代码注释/文档内容用中文。
- **Docstrings**: `__init__.py` 需包含模块概述；类/函数需说明用途、参数及算法逻辑。
- **术语**: breakout/breakthrough/bt (突破点), peak/pk (峰值/凸点)
