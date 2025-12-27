# evaluator_demo.py 说明文档

## 文件概述

`evaluator_demo.py` 是一个**买入时机评估器演示脚本**，用于展示多维度买入时机评估系统的功能和使用方法。该脚本通过多个演示场景，详细说明了评估系统的四维度评估机制、综合评分机制以及与观察池系统的集成方式。

**文件路径**: `/home/yu/PycharmProjects/Trade_Strategy/scripts/backtest/evaluator_demo.py`

**运行方式**:
```bash
python scripts/backtest/evaluator_demo.py
```

---

## 功能说明

### 核心功能

该演示脚本展示的买入时机评估系统采用**四维度评估机制**：

| 维度 | 说明 | 评估内容 |
|------|------|----------|
| **时间窗口** | 评估买入时段 | 最佳时段 10:00-11:30 AM ET |
| **价格确认** | 评估价格位置 | 突破价上方 1%-2% |
| **成交量验证** | 评估成交量强度 | 量比 >= 1.5x |
| **风险过滤** | 过滤高风险场景 | 跌破3%移出，跳空>8%跳过 |

### 综合评分机制

- **强买入信号**: 综合评分 >= 70 分
- **普通买入信号**: 综合评分 >= 50 分
- **继续观察**: 综合评分 < 50 分
- **移出观察池**: 触发风险红线条件

---

## 代码结构分析

### 文件结构

```
evaluator_demo.py
├── demo_single_evaluation()    # 演示1: 单次买入条件评估
├── demo_pool_integration()     # 演示2: 观察池集成
├── demo_risk_filter()          # 演示3: 风险过滤场景
├── demo_config_customization() # 演示4: 自定义配置
├── print_result()              # 辅助函数: 打印评估结果
└── main()                      # 主入口函数
```

### 演示函数详解

#### 1. `demo_single_evaluation()` - 单次买入条件评估

演示如何使用评估器对单个股票条目进行多种场景评估：

- **场景1: 理想买入条件** - 价格在峰值上方+1.96%，成交量放大
- **场景2: 价格回踩** - 价格回踩到支撑位附近
- **场景3: 跌破支撑** - 价格跌破阈值，触发移出信号
- **场景4: 缩量** - 价格位置正确但成交量不足

```python
# 关键代码结构
pool_mgr = create_backtest_pool_manager(...)
entry = PoolEntry(...)
bar = pd.Series({...})  # 当日K线数据
result = pool_mgr.buy_evaluator.evaluate(entry, bar, pool_mgr.time_provider, {...})
```

#### 2. `demo_pool_integration()` - 观察池集成

模拟多日回测流程，展示：
- 突破检测后添加到实时观察池
- 次日检查买入信号
- 生成买入信号详情（价格、止损、仓位建议）
- 标记已买入状态

```python
# 关键流程
pool_mgr.realtime_pool.add(entry)           # 添加到观察池
pool_mgr.time_provider.advance(1)           # 推进时间
signals = pool_mgr.check_buy_signals(price_data)  # 检查买入信号
pool_mgr.mark_bought(sig.symbol)            # 标记已买入
```

#### 3. `demo_risk_filter()` - 风险过滤场景

演示风险过滤器的工作方式：
- **跳空过高场景**: 开盘跳空+10%超过8%阈值，触发跳过
- **正常跳空场景**: 开盘跳空+3%在正常范围内，正常评估

#### 4. `demo_config_customization()` - 自定义配置

展示如何创建和使用自定义配置：
```python
custom_config = BuyConditionConfig()
custom_config.price_confirm.min_breakout_margin = 0.005  # 调整为 0.5%
custom_config.scoring.strong_buy_threshold = 80          # 更严格的阈值

pool_mgr = create_backtest_pool_manager(
    start_date=date(2024, 1, 1),
    config={'buy_condition_config': custom_config}
)
```

#### 5. `print_result()` - 结果打印辅助函数

格式化输出评估结果，包括：
- 动作类型（强买入/普通买入/继续观察/移出/转移）
- 总评分和买入信号判断
- 建议入场价和止损价
- 各维度评分详情

---

## 使用方法

### 基础使用

```python
from datetime import date
from BreakoutStrategy.observation import (
    create_backtest_pool_manager,
    PoolEntry,
)

# 1. 创建观察池管理器
pool_mgr = create_backtest_pool_manager(
    start_date=date(2024, 1, 1),
    config={'buy_condition_config_path': 'configs/buy_condition_config.yaml'}
)

# 2. 创建观察池条目
entry = PoolEntry(
    symbol='AAPL',
    add_date=date(2024, 1, 1),
    breakout_date=date(2024, 1, 1),
    quality_score=75,
    breakout_price=100.0,
    highest_peak_price=102.0,
    pool_type='realtime'
)

# 3. 准备K线数据
bar = pd.Series({
    'open': 103.0,
    'high': 104.5,
    'low': 102.5,
    'close': 104.0,
    'volume': 1800000
})

# 4. 执行评估
result = pool_mgr.buy_evaluator.evaluate(
    entry, bar, pool_mgr.time_provider,
    {'volume_ma20': 1000000}
)

# 5. 查看结果
print(f"动作: {result.action.value}")
print(f"总评分: {result.total_score}")
print(f"是否买入: {result.is_buy_signal}")
```

### 批量检查买入信号

```python
# 准备多只股票的价格数据
price_data = {
    'AAPL': pd.Series({...}),
    'GOOGL': pd.Series({...}),
    'MSFT': pd.Series({...}),
}

# 批量检查买入信号
signals = pool_mgr.check_buy_signals(price_data)

for sig in signals:
    print(f"股票: {sig.symbol}")
    print(f"信号价格: ${sig.signal_price:.2f}")
    print(f"信号强度: {sig.signal_strength:.2f}")
    print(f"建议止损: ${sig.suggested_stop_loss:.2f}")
    print(f"建议仓位: {sig.suggested_position_size_pct*100:.0f}%")
```

---

## 依赖关系

### 外部依赖

| 包名 | 用途 |
|------|------|
| `pandas` | 数据处理，构建K线数据 |

### 内部模块依赖

```
BreakoutStrategy/observation/
├── __init__.py                    # 模块入口，导出主要类和函数
│   ├── create_backtest_pool_manager  # 工厂函数
│   ├── PoolEntry                     # 观察池条目数据类
│   ├── BuyConditionConfig            # 买入条件配置类
│   └── EvaluationAction              # 评估动作枚举
│
├── pool_manager.py                # 观察池管理器
├── pool_entry.py                  # 池条目定义
├── evaluators/                    # 评估器模块
│   ├── composite.py               # 组合评估器
│   ├── config.py                  # 配置类定义
│   ├── result.py                  # 评估结果类
│   └── components/                # 四维度评估组件
│       ├── time_window.py         # 时间窗口评估
│       ├── price_confirm.py       # 价格确认评估
│       ├── volume_verify.py       # 成交量验证
│       └── risk_filter.py         # 风险过滤
│
└── strategies/                    # 策略模块
    └── storages.py                # 存储策略
```

### 配置文件依赖

- **配置文件路径**: `configs/buy_condition_config.yaml`
- **配置内容**: 时间窗口、价格确认、成交量验证、风险过滤、综合评分等参数

---

## 注意事项

### 1. 路径配置

脚本通过以下方式自动添加项目根目录到Python路径：
```python
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
```

请确保从项目根目录运行脚本，或确保 `PYTHONPATH` 包含项目根目录。

### 2. 配置文件

- 默认配置文件位于 `configs/buy_condition_config.yaml`
- 可通过 `buy_condition_config_path` 参数指定自定义配置路径
- 也可通过 `buy_condition_config` 参数直接传入配置对象

### 3. 评估模式

配置文件中 `mode` 字段支持两种模式：
- `realtime`: 实时模式，使用完整的四维度评估
- `backtest`: 回测模式，简化时间窗口评估

### 4. 评估动作类型

| 动作 | 说明 |
|------|------|
| `strong_buy` | 强买入信号，评分 >= 70 |
| `normal_buy` | 普通买入信号，评分 >= 50 |
| `hold` | 继续观察，评分 < 50 |
| `remove` | 移出观察池，触发风险红线 |
| `transfer` | 转移到其他池（如从实时池转移到日线池）|

### 5. 关键阈值说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `min_breakout_margin` | 1% | 价格需高于参考价至少 1% |
| `max_breakout_margin` | 2% | 超过 2% 开始降低评分 |
| `pullback_tolerance` | 3% | 回踩不超过 3% 仍可接受 |
| `remove_threshold` | 3% | 跌破 3% 移出观察池 |
| `min_volume_ratio` | 1.5x | 成交量需达基准的 1.5 倍 |
| `gap_skip_threshold` | 8% | 跳空超过 8% 当日跳过 |

---

## 输出示例

运行脚本后的典型输出：

```
============================================================
买入时机评估器演示
============================================================

此演示展示多维度买入时机评估系统的功能：

  四维度评估:
    1. 时间窗口 - 最佳买入时段 10:00-11:30 AM ET
    2. 价格确认 - 突破价上方 1%-2%
    3. 成交量验证 - 量比 >= 1.5x
    4. 风险过滤 - 跌破3%移出，跳空>8%跳过

  综合评分:
    - 强买入: >= 70分
    - 普通买入: >= 50分
    - 继续观察: < 50分
    - 移出: 触发风险红线

============================================================
演示1: 单次买入条件评估
============================================================

--- 场景1: 理想买入条件 ---
  动作: strong_buy
  总评分: 82.5
  是否买入: 是
  原因: 价格确认+放量突破
  建议入场: $104.00
  建议止损: $99.00
  维度评分:
    [✓] time_window: 100 (权重 20%)
    [✓] price_confirm: 85 (权重 30%)
    [✓] volume_verify: 90 (权重 25%)
    [✓] quality_score: 75 (权重 25%)
```

---

## 相关文档

- 观察池系统设计: `docs/modules/specs/observation_pool.md`
- 买入条件配置: `configs/buy_condition_config.yaml`
- 项目需求文档: `docs/system/PRD.md`
