# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

这是一个**突破选股策略系统**（BreakthroughStrategy），用于美股市场量化交易的Python项目。系统通过识别历史阻力位（凸点）和价格突破来生成交易信号。

**核心策略**：
- 识别股价的历史峰值（凸点）作为阻力位
- 检测价格突破这些阻力位的时机
- 使用双观察池系统（实时观察池 + 日K观察池）监测突破后的走势
- 自动交易执行和风险管理

**关键特性**：
- **增量式架构**：支持实时监控和历史回测，算法一致性保证
- **多峰值突破识别**：一次突破可能同时突破多个密集阻力位
- **质量评分系统**：综合评估峰值强度和突破质量

## 开发环境配置

### Python环境
- **Python版本**：3.8+
- **包管理**：使用配置的快速pip镜像（用户已配置）
- **依赖**：pandas, numpy, scipy, matplotlib, tigeropen（Tiger API SDK）

### 重要配置
- **入口程序参数**：不使用argparse，所有参数作为变量声明在main()函数起始位置
- **MCP工具**：可使用context7 MCP查询文档（配置在.mcp.json）

## 代码架构

### 目录结构

```
Trade_Strategy/
└── BreakthroughStrategy/          # 突破策略系统（主模块）
    ├── analysis/                   # 技术分析模块（已实现）
    │   ├── breakthrough_detector.py  # 增量式突破检测核心
    │   ├── peak_detector.py          # 峰值识别
    │   ├── breakout_detector.py      # 突破检测
    │   ├── quality_scorer.py         # 质量评分
    │   ├── features.py               # 特征计算
    │   ├── indicators.py             # 技术指标
    │   └── test/                     # 集成测试
    ├── data/                       # 数据层（待实现）
    ├── search/                     # 搜索系统（待实现）
    ├── observation/                # 观察池系统（待实现）
    ├── monitoring/                 # 监测系统（待实现）
    ├── trading/                    # 交易执行（待实现）
    ├── risk/                       # 风险管理（待实现）
    ├── backtest/                   # 回测系统（待实现）
    ├── config/                     # 配置管理（待实现）
    ├── utils/                      # 工具模块（待实现）
    └── docs/                       # 技术文档
        ├── plans/                  # 开发计划
        ├── module_plans/           # 模块设计文档（10个）
        └── module_summaries/       # 模块开发总结文档
```

### 模块分层

**基础层**：
- `data/`：Tiger API数据获取、缓存、实时订阅
- `config/`：YAML配置管理、参数验证
- `utils/`：日志、数据库、可视化、日期工具

**分析层**：
- `analysis/`：凸点识别、突破检测、质量评分（**已实现核心算法**）

**应用层**：
- `search/`：历史突破搜索、股票过滤
- `observation/`：双观察池管理（实时观察池、日K观察池）
- `monitoring/`：实时监控、信号检测
- `trading/`：Tiger API交易、订单管理
- `risk/`：止盈止损、仓位管理

**验证层**：
- `backtest/`：策略回测、参数优化

## 核心算法（analysis模块）

### 增量式突破检测

系统使用**增量式架构**维护活跃峰值列表：

### 关键算法特性

1. **峰值共存策略**：价格相近（<3%）的峰值可以同时存在，形成密集阻力区
2. **多峰值突破**：一次突破可能突破1-5个峰值，阻力越强突破意义越大
3. **质量评分维度**：
   - 峰值质量：放量(25%) + 长K线(20%) + 压制时间(25%) + 相对高度(15%)
   - 突破质量：涨跌幅(20%) + 跳空(10%) + 放量(20%) + 连续性(15%) + 稳定性(15%) + **阻力强度(20%)**
   - 阻力强度：峰值数量 + 密集度 + 峰值质量

## 运行测试

### 集成测试

```bash
cd BreakthroughStrategy/analysis/test
python test_integrated_system.py
```

测试验证：
- 增量式突破检测正确性
- 多峰值突破识别
- 改进的质量评分系统

## 开发阶段

项目采用**两步开发法**：先编写技术设计文档，再进行代码实现。

**当前状态**：
- ✅ 阶段一（核心基础）：技术分析模块已实现并测试
- 🔜 阶段二：搜索系统与回测系统
- 🔜 阶段三：观察池与监测系统
- 🔜 阶段四：交易执行与风险管理
- 🔜 阶段五：优化与部署

**技术设计文档**：
- 所有模块的详细设计文档位于 `docs/modules/`
- 包含10个模块的接口定义、算法伪代码、数据结构设计

## Tiger API集成

数据源和交易接口使用Tiger Open API：
- 历史日K/分钟K数据：`get_bars()`
- 实时行情：WebSocket订阅
- 交易执行：`place_order()`, `cancel_order()`
- API凭证通过环境变量配置（`TIGER_ID`, `TIGER_ACCOUNT`, `TIGER_PRIVATE_KEY_PATH`）

## 关键约束

### 参数配置
- 配置使用YAML格式（参考 `docs/modules/09_配置管理设计.md`）
- 所有参数集中管理，支持验证和多环境配置

### 数据处理
- 历史数据缓存到SQLite/PostgreSQL避免重复请求
- 实时数据使用WebSocket推送，不缓存
- 数据验证包括：必需列检查、价格逻辑验证、异常值过滤

### 算法一致性
**重要**：相同的增量式算法用于回测和实时监控，保证结果一致性：
- 回测场景：`use_cache=False`
- 实时监控：`use_cache=True`（支持程序重启后恢复状态）

## 常见任务

### 添加新功能模块

1. 查阅对应的技术设计文档（`docs/modules/`）
2. 按照设计文档中的接口定义和算法实现
3. 编写单元测试验证功能
4. 更新模块的`__init__.py`导出接口


### 扩展技术指标

在 `analysis/indicators.py` 中添加新指标函数，然后在 `FeatureCalculator` 中调用。

## 文档管理

本项目采用**三层文档体系**（规划-设计-总结）管理开发过程。

→ 详见 @BreakthroughStrategy/docs/CLAUDE.md 了解完整的文档管理策略

### 核心文档

- **文档管理说明**：`BreakthroughStrategy/docs/CLAUDE.md`（三层文档体系说明）
- **开发计划**：`BreakthroughStrategy/docs/plans/initial_plan.md`（宏观规划，标注模块完成状态）
- **模块设计**：`BreakthroughStrategy/docs/module_plans/`（10个模块的详细设计，01-10编号）
- **模块总结**：`BreakthroughStrategy/docs/module_summaries/`（与设计文档一一对应，编号一致）

**文档对应关系**：
```
module_plans/02_技术分析模块设计.md  ←→  module_summaries/02_技术分析模块总结.md
    （开发前）                              （开发后，✅ 已完成）
```

### 外部文档

- **Tiger API文档**：https://quant.itigerup.com/openapi/zh/python/overview/introduction.html

## 质量标准

### 技术标准
- 单元测试通过率 > 90%
- 实时监控延迟 < 5秒
- 数据获取成功率 > 99%

### 策略标准（回测目标）
- 年化收益率 > 15%
- 夏普比率 > 1.0
- 最大回撤 < 20%
- 胜率 > 50%
