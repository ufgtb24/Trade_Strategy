# BreakthroughStrategy 开发计划

**项目路径**: `BreakthroughStrategy/`
**当前状态**: 技术分析模块已完成（v2.0 增量式架构）
**更新日期**: 2025-11-18

---

## 一、当前进度

### ✅ 已完成模块

#### 1. 技术分析模块（analysis/）

**完成度**: 100%
**版本**: v2.0（增量式重构）

**核心成果**：
- ✅ `BreakthroughDetector` - 增量式突破检测器
  - 支持峰值共存（密集阻力区）
  - 支持多峰值突破
  - 支持持久化缓存（可选）
  - O(1) 增量更新
- ✅ `FeatureCalculator` - 特征计算器
- ✅ `QualityScorer` - 改进的质量评分系统
  - 修复密集度评分bug
  - 综合所有被突破峰值的质量
  - 阻力强度评分（数量+密集度+质量）
- ✅ 测试验证（AAPL 1255天数据）
  - 识别59个突破（vs 旧版18个）
  - 10个多峰值突破
  - 最高评分49.0/100
- ✅ 文档完善
  - `docs/summaries/技术分析模块算法总结.md`

**架构优势**：
- 统一的增量式算法（回测=实盘）
- 实时监控O(1)性能
- 程序重启可恢复

---

## 二、接下来的开发计划（按优先级排序）

### 优先级说明

```
基础层 > 核心功能 > 验证系统 > 实盘功能 > 优化
```

---

## 【优先级1】基础设施层

### 1.1 配置管理模块（config/）

**重要性**: ⭐️⭐️⭐️⭐️⭐️（最高优先级）
**原因**: 所有模块都依赖配置管理
**预计工作量**: 3-5天

**核心目标**：
- 统一的参数配置管理
- 支持YAML配置文件
- 参数验证和默认值
- 支持多环境配置（开发/测试/生产）

**子模块**：
```
config/
├── __init__.py
├── config_manager.py      # 配置管理器
├── parameter_validator.py # 参数验证器
├── defaults.py            # 默认配置
└── schemas.yaml           # 配置schema定义
```

**关键配置项**：
```yaml
# 技术分析参数
analysis:
  window: 5
  exceed_threshold: 0.005
  peak_merge_threshold: 0.03

# 搜索参数
search:
  market_cap_min: 1000000000
  avg_volume_min: 1000000
  price_min: 5.0

# 质量评分参数
quality:
  peak_quality_min_score: 60
  breakthrough_quality_min_score: 70

# 风险管理参数
risk:
  stop_loss_pct: 0.05
  target_profit_pct: 0.15
  max_position_size_pct: 0.10
```

**验收标准**：
- ✓ 能从YAML文件加载配置
- ✓ 支持参数验证（范围、类型）
- ✓ 支持默认值回退
- ✓ 能导出当前配置到文件

**文档产出**：
- `docs/modules/配置管理设计.md`

---

### 1.2 工具与辅助模块（utils/）

**重要性**: ⭐️⭐️⭐️⭐️⭐️（最高优先级）
**原因**: 日志、数据库等基础设施
**预计工作量**: 4-6天

**核心目标**：
- 统一的日志系统
- 数据库管理工具
- 数据可视化工具
- 日期时间工具

**子模块**：
```
utils/
├── __init__.py
├── logger.py              # 日志系统
├── database.py            # 数据库管理
├── visualizer.py          # 可视化工具
├── date_utils.py          # 日期工具
└── common.py              # 通用工具函数
```

**核心功能**：

1. **日志系统**：
   - 多级别日志（DEBUG, INFO, WARNING, ERROR）
   - 文件日志 + 控制台日志
   - 日志轮转

2. **数据库管理**：
   - SQLite封装（开发/测试）
   - 连接池管理
   - 表结构管理

3. **可视化工具**：
   - K线图绘制
   - 峰值/突破点标注
   - 收益曲线绘制

4. **日期工具**：
   - 交易日判断
   - 日期范围生成
   - 时区转换

**数据库表设计**（初版）：
```sql
-- 峰值信息表
CREATE TABLE peaks (
    id INTEGER PRIMARY KEY,
    symbol TEXT,
    date DATE,
    price REAL,
    index_position INTEGER,
    quality_score REAL,
    created_at TIMESTAMP
);

-- 突破信息表
CREATE TABLE breakthroughs (
    id INTEGER PRIMARY KEY,
    symbol TEXT,
    date DATE,
    price REAL,
    num_peaks_broken INTEGER,
    quality_score REAL,
    created_at TIMESTAMP
);

-- 搜索结果表
CREATE TABLE search_results (
    id INTEGER PRIMARY KEY,
    symbol TEXT,
    search_date DATE,
    breakthrough_id INTEGER,
    FOREIGN KEY(breakthrough_id) REFERENCES breakthroughs(id)
);
```

**验收标准**：
- ✓ 日志系统能正确记录到文件和控制台
- ✓ 数据库表能正确创建和查询
- ✓ 能绘制基本的K线图和标注
- ✓ 日期工具能处理常见场景

**文档产出**：
- `docs/modules/工具与辅助设计.md`

---

## 【优先级2】数据集成层

### 2.1 数据管理模块（data/）

**重要性**: ⭐️⭐️⭐️⭐️
**原因**: 集成现有数据源，为后续模块提供数据
**预计工作量**: 5-7天

**核心目标**：
- 集成现有 `DataProcess/` 模块
- 提供统一的数据接口
- 支持本地缓存
- （可选）集成Tiger API

**子模块**：
```
data/
├── __init__.py
├── data_loader.py         # 数据加载器（复用DataProcess）
├── data_cache.py          # 数据缓存管理
├── stock_pool.py          # 股票池管理
└── tiger_adapter.py       # Tiger API适配器（可选）
```

**阶段性实施**：

**阶段1（立即实施）**：复用现有数据
```python
# 集成现有DataProcess模块
from DataProcess.data_download import multi_download_stock
from DataProcess.preprocess import StockPreprocessor

class DataLoader:
    def load_stock_data(self, symbol):
        """加载本地pkl数据"""
        return pickle.load(f'datasets/process_pkls/{symbol}.pkl')

    def get_stock_pool(self):
        """获取股票池"""
        return pickle.load('datasets/stock_list.pkl')
```

**阶段2（后期）**：集成Tiger API
```python
class TigerDataAdapter:
    def get_historical_data(self, symbol, start, end):
        """从Tiger API获取历史数据"""
        ...

    def get_realtime_quote(self, symbol):
        """获取实时报价"""
        ...
```

**验收标准**：
- ✓ 能加载本地pkl数据
- ✓ 能获取股票池列表
- ✓ 数据格式统一（DataFrame）
- ✓ 支持缓存机制

**文档产出**：
- `docs/modules/数据管理设计.md`

---

## 【优先级3】核心应用层

### 3.1 搜索系统模块（search/）

**重要性**: ⭐️⭐️⭐️⭐️⭐️（最高优先级）
**原因**: 核心功能，扫描市场找突破
**预计工作量**: 6-8天

**核心目标**：
- 扫描股票池，找到历史突破
- 应用基础过滤器（市值、流动性、价格）
- 质量评分和排序
- 输出候选股票列表

**子模块**：
```
search/
├── __init__.py
├── scanner.py             # 历史扫描器
├── filters.py             # 股票过滤器
├── search_engine.py       # 搜索引擎主控
└── result_formatter.py    # 结果格式化
```

**核心流程**：
```python
# 使用示例
search_engine = SearchEngine()

# 配置搜索参数
config = {
    'time_range': 7,  # 过去7天
    'min_quality_score': 40,
    'filters': {
        'market_cap_min': 1e9,
        'avg_volume_min': 1e6,
        'price_min': 5.0
    }
}

# 执行搜索
results = search_engine.search(config)

# 结果格式
# [
#   {
#     'symbol': 'AAPL',
#     'breakthrough_date': '2024-11-15',
#     'quality_score': 49.0,
#     'num_peaks_broken': 1,
#     'peak_info': {...},
#     'breakthrough_info': {...}
#   },
#   ...
# ]
```

**搜索流程**：
```
1. 获取股票池
   ↓
2. 应用基础过滤器（市值、流动性、价格）
   ↓
3. 对每只股票：
   - 加载历史数据
   - 创建BreakthroughDetector
   - 批量添加历史数据
   - 获取突破列表
   ↓
4. 计算特征和质量评分
   ↓
5. 筛选和排序
   ↓
6. 输出结果（JSON/数据库/文件）
```

**输出格式**：
- JSON文件：`ext_file/search_results/YYYY-MM-DD_HH-MM-SS.json`
- 数据库：`search_results` 表
- 控制台：Top 10 结果

**验收标准**：
- ✓ 能扫描指定时间范围的突破
- ✓ 过滤器正常工作
- ✓ 质量评分准确
- ✓ 结果格式规范
- ✓ 性能可接受（100只股票<10分钟）

**文档产出**：
- `docs/modules/搜索系统设计.md`

---

## 【优先级4】验证系统

### 4.1 回测系统模块（backtest/）

**重要性**: ⭐️⭐️⭐️⭐️⭐️（最高优先级）
**原因**: 验证策略有效性
**预计工作量**: 7-10天

**核心目标**：
- 使用历史数据回测策略
- 计算性能指标
- 生成回测报告
- 参数优化（Optuna）

**子模块**：
```
backtest/
├── __init__.py
├── backtest_engine.py     # 回测引擎
├── performance.py         # 性能分析器
├── optimizer.py           # 参数优化器
└── reporter.py            # 报告生成器
```

**回测流程**：
```python
# 使用示例
engine = BacktestEngine(
    start_date='2020-01-01',
    end_date='2024-12-31',
    initial_capital=100000,
    config=config
)

# 运行回测
results = engine.run()

# 性能分析
analyzer = PerformanceAnalyzer(results)
metrics = analyzer.calculate_metrics()

# 生成报告
reporter = BacktestReporter(results, metrics)
reporter.generate_html_report('backtest_report.html')
```

**核心逻辑**：
```
1. 对于每个交易日：
   - 运行搜索系统（找突破）
   - 生成买入信号
   - 执行买入（模拟）
   - 更新持仓
   - 检查止盈止损
   - 执行卖出（模拟）
   ↓
2. 记录所有交易
   ↓
3. 计算性能指标
```

**性能指标**：
- 总收益率、年化收益率
- 夏普比率、最大回撤
- 胜率、盈亏比
- 交易次数、平均持仓天数

**参数优化**（Optuna）：
```python
def objective(trial):
    # 优化参数
    window = trial.suggest_int('window', 3, 10)
    exceed_threshold = trial.suggest_float('exceed_threshold', 0.003, 0.01)
    peak_merge_threshold = trial.suggest_float('peak_merge_threshold', 0.01, 0.05)

    # 运行回测
    results = backtest_engine.run(window, exceed_threshold, peak_merge_threshold)

    # 返回目标函数（如夏普比率）
    return results['sharpe_ratio']

# 优化
study = optuna.create_study(direction='maximize')
study.optimize(objective, n_trials=100)
```

**验收标准**：
- ✓ 回测引擎能正确模拟交易
- ✓ 性能指标计算准确
- ✓ 能生成HTML报告
- ✓ 参数优化能找到合理的参数组合
- ✓ 回测结果与手工计算一致

**文档产出**：
- `docs/modules/回测系统设计.md`

---

## 【优先级5】实盘准备（后期）

### 5.1 观察池系统（observation/）

**重要性**: ⭐️⭐️⭐️⭐️
**预计工作量**: 5-7天

**核心目标**：
- 双观察池管理（实时池、日K池）
- 池间转换逻辑
- 持久化存储

### 5.2 监测系统（monitoring/）

**重要性**: ⭐️⭐️⭐️⭐️
**预计工作量**: 6-8天

**核心目标**：
- 实时监控观察池股票
- 买入信号检测
- 警报通知

### 5.3 交易执行（trading/）

**重要性**: ⭐️⭐️⭐️⭐️
**预计工作量**: 7-10天

**核心目标**：
- Tiger API交易接口封装
- 订单管理
- 持仓追踪

### 5.4 风险管理（risk/）

**重要性**: ⭐️⭐️⭐️⭐️⭐️
**预计工作量**: 5-7天

**核心目标**：
- 止盈止损策略
- 仓位管理
- 风险控制

---

## 【优先级6】优化与部署（最后）

### 6.1 性能优化

**预计工作量**: 3-5天

- 多进程并行处理
- 代码性能优化
- 缓存优化

### 6.2 参数调优

**预计工作量**: 5-7天

- 大规模Optuna优化
- 交叉验证
- 最优参数确定

### 6.3 生产部署

**预计工作量**: 3-5天

- 部署文档编写
- 环境配置
- 监控系统搭建

---

## 三、近期开发路线图

### 第1周：基础设施（配置管理 + 工具）

**目标**：完成配置管理和工具模块

**任务清单**：
- [ ] 创建目录结构
- [ ] 实现ConfigManager
- [ ] 实现Logger
- [ ] 实现DatabaseManager
- [ ] 实现基础可视化工具
- [ ] 编写单元测试
- [ ] 编写技术文档

**验收**：
- ✓ 能加载YAML配置
- ✓ 日志系统正常工作
- ✓ 数据库表创建成功
- ✓ 能绘制基本K线图

---

### 第2周：数据集成

**目标**：集成现有数据源

**任务清单**：
- [ ] 实现DataLoader（复用DataProcess）
- [ ] 实现StockPool
- [ ] 实现DataCache
- [ ] 编写单元测试
- [ ] 编写技术文档

**验收**：
- ✓ 能加载本地pkl数据
- ✓ 能获取股票池
- ✓ 数据格式统一

---

### 第3周：搜索系统（上）

**目标**：实现历史扫描器和过滤器

**任务清单**：
- [ ] 实现HistoricalScanner
- [ ] 实现StockFilter
- [ ] 编写单元测试

**验收**：
- ✓ 能扫描单只股票的历史突破
- ✓ 过滤器正常工作

---

### 第4周：搜索系统（下）

**目标**：完成搜索引擎和结果格式化

**任务清单**：
- [ ] 实现SearchEngine（整合扫描器和过滤器）
- [ ] 实现ResultFormatter
- [ ] 性能优化（多进程）
- [ ] 编写技术文档
- [ ] 端到端测试

**验收**：
- ✓ 能完整扫描股票池
- ✓ 结果格式规范
- ✓ 性能达标

---

### 第5-6周：回测系统

**目标**：实现完整的回测系统

**任务清单**：
- [ ] 实现BacktestEngine
- [ ] 实现PerformanceAnalyzer
- [ ] 实现BacktestReporter
- [ ] 实现ParameterOptimizer（Optuna）
- [ ] 编写技术文档
- [ ] 大规模回测验证

**验收**：
- ✓ 回测结果准确
- ✓ 性能指标计算正确
- ✓ 能生成报告
- ✓ 参数优化有效

---

## 四、里程碑

### 里程碑1：基础设施完成（第2周末）
- ✓ 配置管理模块
- ✓ 工具与辅助模块
- ✓ 数据管理模块

**成果**：基础设施可用，为核心功能做好准备

---

### 里程碑2：搜索系统完成（第4周末）
- ✓ 搜索系统模块
- ✓ 能扫描市场找突破
- ✓ 结果质量可控

**成果**：能找到候选交易机会

---

### 里程碑3：回测系统完成（第6周末）
- ✓ 回测系统模块
- ✓ 策略验证完成
- ✓ 参数优化完成

**成果**：策略有效性得到验证，确定最优参数

---

### 里程碑4：实盘准备完成（第10-12周）
- ✓ 观察池系统
- ✓ 监测系统
- ✓ 交易执行
- ✓ 风险管理

**成果**：可以进行实盘交易（小资金测试）

---

## 五、技术文档规划

按照开发顺序，需要编写以下技术文档：

1. **第1周**：
   - `docs/modules/配置管理设计.md`
   - `docs/modules/工具与辅助设计.md`

2. **第2周**：
   - `docs/modules/数据管理设计.md`

3. **第3-4周**：
   - `docs/modules/搜索系统设计.md`

4. **第5-6周**：
   - `docs/modules/回测系统设计.md`

5. **后期**（按需）：
   - `docs/modules/观察池系统设计.md`
   - `docs/modules/监测系统设计.md`
   - `docs/modules/交易执行设计.md`
   - `docs/modules/风险管理设计.md`

---

## 六、关键决策点

### 决策1：数据源选择

**当前方案**：
- 阶段1：复用现有DataProcess（本地pkl数据）
- 阶段2：集成Tiger API（后期）

**原因**：
- ✓ 快速启动，无需等待API权限
- ✓ 现有数据足够验证策略
- ✓ 降低早期风险

### 决策2：回测框架选择

**方案A**：基于Backtrader（复用现有）
**方案B**：自研回测引擎

**推荐**：方案A（快速验证），后期可扩展

### 决策3：开发顺序

**选择**：基础设施 → 搜索 → 回测 → 实盘

**原因**：
- 先验证策略有效性（搜索+回测）
- 再投入实盘开发（降低风险）
- 迭代式开发，每阶段可交付

---

## 七、风险与应对

### 风险1：回测表现不佳

**应对**：
- 调整算法参数
- 优化质量评分系统
- 引入更多特征
- 考虑机器学习

### 风险2：开发时间超期

**应对**：
- MVP优先（最小可用版本）
- 灵活调整范围
- 后期功能可延后

### 风险3：数据质量问题

**应对**：
- 严格的数据验证
- 异常值检测和处理
- 多数据源备份

---

## 八、下一步行动

### 立即开始（本周）

1. **创建目录结构**
   ```bash
   cd BreakthroughStrategy
   mkdir -p config/{schemas,environments}
   mkdir -p utils/{tests}
   mkdir -p data/{tests}
   mkdir -p search/{tests}
   mkdir -p backtest/{tests}
   mkdir -p docs/modules
   ```

2. **开始配置管理模块开发**
   - 定义配置schema
   - 实现ConfigManager
   - 编写单元测试

3. **编写技术文档**
   - `docs/modules/配置管理设计.md`

### 本周目标

- ✓ 配置管理模块基本可用
- ✓ 日志系统基本可用
- ✓ 数据库管理基本可用
- ✓ 技术文档完成

---

## 九、成功标准

### 技术标准

- ✓ 代码覆盖率 > 80%
- ✓ 单元测试通过率 100%
- ✓ 文档完整度 > 90%

### 性能标准

- ✓ 搜索100只股票 < 10分钟
- ✓ 回测5年数据 < 30分钟
- ✓ 参数优化100次迭代 < 2小时

### 策略标准（回测）

- ✓ 年化收益率 > 15%
- ✓ 夏普比率 > 1.0
- ✓ 最大回撤 < 20%
- ✓ 胜率 > 50%

---

**计划版本**: v1.0
**创建日期**: 2025-11-18
**负责人**: Yu
**状态**: 执行中
