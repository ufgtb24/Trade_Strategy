# Daily 池架构分析报告

> 创建日期: 2026-01-04
> 分析目的: 评估在现有观察池架构上扩展 Daily 池 vs 重新设计的决策

---

## Executive Summary

**核心结论**：当前观察池系统确实是"Realtime-first"设计，但核心抽象层（策略模式、池基类、存储接口）设计优秀。问题集中在评估器层，该层对 Daily 池的"过程评估"需求支持不足。

**推荐方案**：重构评估器层，保留优秀的基础设施。不需要完全重新设计，但也不建议简单扩展。

| 方案 | 开发周期 | 推荐度 |
|------|----------|--------|
| A. 简单扩展现有架构 | ~3 天 | 不推荐（会产生妥协代码） |
| B. 完全重新设计 | ~6.5 天 | 不推荐（浪费已验证代码） |
| **C. 重构评估器层** | ~4 天 | **推荐** |

---

## 一、当前架构的设计本质

### 1.1 架构分层结构

```
┌────────────────────────────────────────────────────────────────┐
│ 第4层：应用层 (BacktestEngine, UI集成)                         │
├────────────────────────────────────────────────────────────────┤
│ 第3层：评估器层 (CompositeBuyEvaluator, 四维度组件)   ← 问题区  │
├────────────────────────────────────────────────────────────────┤
│ 第2层：管理层 (PoolManager, 双池协调, 事件分发)       ← 稳定    │
├────────────────────────────────────────────────────────────────┤
│ 第1层：基础层 (ObservationPoolBase, PoolEntry)        ← 优秀    │
├────────────────────────────────────────────────────────────────┤
│ 第0层：策略层 (ITimeProvider, IPoolStorage)           ← 优秀    │
└────────────────────────────────────────────────────────────────┘
```

### 1.2 各层质量评估

| 层级 | 代码行数 | 设计质量 | 扩展性 | 问题点 |
|------|----------|----------|--------|--------|
| 策略层 | ~300行 | 优秀 | 极好 | 无 |
| 基础层 | ~450行 | 优秀 | 极好 | 无 |
| 管理层 | ~750行 | 良好 | 良好 | 双池逻辑可解耦 |
| 评估器层 | ~800行 | 中等 | 需改进 | **Daily 场景支持不足** |
| 应用层 | ~550行 | 良好 | 良好 | 无 |

### 1.3 Realtime-first 设计的证据

| 证据 | 代码位置 | 说明 |
|------|---------|------|
| `pool_type` 默认值是 `'realtime'` | `pool_entry.py:61` | 设计心智偏向 Realtime |
| TimeWindow 回测模式返回固定 100 分 | `time_window.py:75-83` | 承认 Daily 场景无法评估 |
| 成交量配置是 5 分钟窗口 | `config.py:97-98` | 分时粒度，日 K 无法使用 |
| 生命周期描述 | `pool_entry.py:29-34` | Daily 池被定位为"降级容器" |
| `monitoring_start_time` 字段 | `pool_entry.py:71` | 分时监控概念，日 K 不适用 |

### 1.4 四维度评估器的 Daily 池适用性

| 评估器 | 设计场景 | Daily 池适用性 | 问题 |
|--------|----------|---------------|------|
| TimeWindowEvaluator | 盘中时间窗口 | **不适用** | 日 K 无时间维度，回测返回固定 100 分 |
| PriceConfirmEvaluator | 突破后价格确认 | 部分适用 | 只做点比较，不识别过程 |
| VolumeVerifyEvaluator | 分时成交量放大 | **不适用** | 需日均量替代 5 分钟量 |
| RiskFilterEvaluator | 通用风险过滤 | 适用 | 门槛条件通用 |

---

## 二、Realtime 池 vs Daily 池的本质差异

### 2.1 核心差异：状态 vs 过程

| 维度 | Realtime 池 | Daily 池 |
|------|------------|---------|
| **关注对象** | 当前状态 | 变化过程 |
| **核心问题** | "此刻是否买入？" | "经历了什么变化？" |
| **输入数据** | 单条 K 线快照 | N 天历史序列 |
| **评估方式** | 点比较（当前价 vs 参考价） | 模式识别（回调→企稳→再启动） |
| **时间粒度** | 分钟级 | 日级 |
| **评估频率** | 盘中多次 | 每日收盘后一次 |

### 2.2 Daily 池的业务目标

**捕捉"回调-企稳-再启动"的过程**：

```
价格
  ^
  │      ┌──┐
  │     /    \_______________/\
  │    /     ↓回调    ↓企稳   ↑再启动
  │   /  ----突破价--------------------
  │  /
  └─────────────────────────────────────> 时间
     D0  D1-D5     D6-D15    D16+
              ↓              ↓
            不买入         最佳买点
```

### 2.3 为什么加权评分模型不适合 Daily 池

当前 `CompositeBuyEvaluator` 使用加权求和模型：
```
score = time_weight × time_score + price_weight × price_score + ...
```

**问题**：
1. 各维度不是"并行贡献"，而是"阶段证据"
2. 无法表达"先回调、再企稳、最后启动"的时序关系
3. TimeWindow 返回固定 100 分，导致 20% 权重失效

---

## 三、纯 Daily 池的理想架构

### 3.1 阶段状态机模型

如果从零设计 Daily 池，应该使用阶段状态机替代加权评分：

```
状态转换图：

INITIAL ──────────────────────────────────┐
    │                                     │
    │ 价格下跌 > 0.3 ATR                  │ 直接企稳（无明显回调）
    ▼                                     ▼
PULLBACK                            CONSOLIDATION
    │                                     │
    │ 波动收敛 +                          │ 放量 + 突破企稳区间
    │ 支撑形成                            │
    ▼                                     ▼
CONSOLIDATION ────────────────────→ REIGNITION
    │                                     │
    │ 跌破支撑                            │ 确认信号
    ▼                                     ▼
  FAILED                               SIGNAL
```

### 3.2 理想架构的核心差异

| 维度 | 当前架构 | 理想 Daily 架构 |
|------|---------|-----------------|
| **评估模型** | 加权评分 (0-100) | 阶段状态机 |
| **输入数据** | `pd.Series`（单 bar） | `pd.DataFrame`（历史序列） |
| **核心维度** | TimeWindow, PriceConfirm, Volume, Risk | 阶段识别, 波动收敛, 支撑形成, 放量启动 |
| **输出类型** | `EvaluationResult`（分数 + 动作） | `PhaseEvaluation`（阶段 + 信号） |
| **状态管理** | 简单三态（active/bought/expired） | 完整阶段机 + 过程历史 |

### 3.3 理想架构类图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Daily Pool System                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────────┐        ┌──────────────────────┐                  │
│  │   DailyPoolManager   │───────>│   DailyPoolEvaluator │                  │
│  ├──────────────────────┤        ├──────────────────────┤                  │
│  │ + entries: Dict      │        │ + price_analyzer     │                  │
│  │ + config: DailyConfig│        │ + volatility_analyzer│                  │
│  │                      │        │ + volume_analyzer    │                  │
│  │ + add_entry()        │        │ + phase_machine      │                  │
│  │ + evaluate_all()     │        │                      │                  │
│  │ + get_signals()      │        │ + evaluate()         │                  │
│  └──────────────────────┘        └──────────────────────┘                  │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                          分析器组件                                  │   │
│  ├─────────────────────────────────────────────────────────────────────┤   │
│  │                                                                     │   │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │   │
│  │  │ PricePattern     │  │ Volatility       │  │ Volume           │  │   │
│  │  │ Analyzer         │  │ Analyzer         │  │ Analyzer         │  │   │
│  │  ├──────────────────┤  ├──────────────────┤  ├──────────────────┤  │   │
│  │  │ - 回调深度       │  │ - ATR 序列       │  │ - 成交量趋势     │  │   │
│  │  │ - 支撑位识别     │  │ - 波动率收敛     │  │ - 放量比率       │  │   │
│  │  │ - 企稳区间       │  │ - 收敛分数       │  │ - 启动放量检测   │  │   │
│  │  └──────────────────┘  └──────────────────┘  └──────────────────┘  │   │
│  │                                                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌──────────────────────┐                                                  │
│  │  PhaseStateMachine   │                                                  │
│  ├──────────────────────┤                                                  │
│  │ + current_phase      │                                                  │
│  │ + transitions        │                                                  │
│  │ + evaluate()         │                                                  │
│  └──────────────────────┘                                                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.4 阶段转换条件表

| 当前阶段 | 目标阶段 | 转换条件 |
|---------|---------|---------|
| INITIAL | PULLBACK | 从突破高点回落 > 0.3 ATR |
| INITIAL | CONSOLIDATION | 波动率开始收敛 + 无明显回调 |
| PULLBACK | CONSOLIDATION | 波动收敛 + 支撑形成 (tests >= 2) |
| PULLBACK | FAILED | 跌破突破价 1.5 ATR |
| CONSOLIDATION | REIGNITION | 放量 (>1.5x) + 突破企稳区间上沿 |
| CONSOLIDATION | FAILED | 跌破支撑位 0.5 ATR |
| REIGNITION | SIGNAL | 维持突破 + 确认条件满足 |
| REIGNITION | CONSOLIDATION | 假突破（回落到企稳区间内） |
| ANY | EXPIRED | 观察期满 (30 天) |

---

## 四、方案对比分析

### 4.1 方案 A：简单扩展现有架构

**做法**：在 `CompositeBuyEvaluator.evaluate()` 中添加 `if pool_type == 'daily'` 分支

**优点**：
- 开发周期短（~3 天）
- 改动范围小

**缺点**：
- 违反单一职责原则
- 评估器职责混乱
- 会产生大量 if-else 分支
- 未来维护困难

**代码坏味道示例**：
```python
def evaluate(self, entry, bar, ...):
    if entry.pool_type == 'daily':
        # 80行 Daily 专用逻辑
    else:
        # 50行 Realtime 逻辑
```

### 4.2 方案 B：完全重新设计

**做法**：为 Daily 池创建完全独立的架构，不复用现有代码

**优点**：
- 架构纯净
- Daily 池专用设计

**缺点**：
- 开发周期长（~6.5 天）
- 浪费已验证的优秀代码（ITimeProvider, IPoolStorage 等）
- 维护两套并行架构

### 4.3 方案 C：重构评估器层（推荐）

**做法**：保留优秀的基础设施，重新设计评估器层

```
保留（复用）                    重构（新设计）
─────────────                   ─────────────
✓ ITimeProvider                 ✗ CompositeBuyEvaluator
✓ IPoolStorage                  ✗ TimeWindowEvaluator
✓ ObservationPoolBase           ✗ VolumeVerifyEvaluator
✓ PoolEntry（核心字段）
✓ BacktestEngine（大部分）       新建
✓ EvaluationResult              ─────────────
✓ BuySignal                     + DailyPoolEvaluator
                                + PhaseStateMachine
                                + PricePatternAnalyzer
                                + VolatilityAnalyzer
                                + VolumeAnalyzer
```

**优点**：
- 复用高质量的已验证代码
- Daily 池获得专用的阶段机模型
- 代码职责清晰
- 未来可扩展性好

**缺点**：
- 开发周期中等（~4 天）
- 需要理解现有架构

---

## 五、成本收益分析

### 5.1 开发成本对比

| 方案 | 工时估算 | 说明 |
|------|----------|------|
| A. 简单扩展 | ~24h (3天) | 快但产生技术债 |
| B. 完全重写 | ~52h (6.5天) | 慢且浪费已验证代码 |
| **C. 重构评估器** | ~32h (4天) | 平衡点 |

### 5.2 风险评估

| 风险类型 | 方案 A | 方案 B | 方案 C |
|----------|--------|--------|--------|
| 技术风险 | 低 | 中 | 低 |
| 时间风险 | 低 | 中 | 低 |
| 质量风险 | **高** | 低 | 低 |
| 维护风险 | **高** | 中 | 低 |

### 5.3 长期收益

| 收益点 | 方案 A | 方案 B | 方案 C |
|--------|--------|--------|--------|
| 代码复用 | 高 | 低 | 高 |
| 架构清晰度 | 低 | 高 | 高 |
| 可测试性 | 中 | 高 | 高 |
| 可扩展性 | 低 | 高 | 高 |

---

## 六、实施路线图（方案 C）

### Phase 1: 新建 Daily 评估器（2天）

```
Day 1 (8h)
├── 设计 Daily 池评估维度（4h）
│   ├── 回调支撑判断逻辑
│   ├── 企稳信号定义
│   └── 参数范围确定
└── 实现 PhaseStateMachine（4h）

Day 2 (8h)
├── 实现 PricePatternAnalyzer（3h）
├── 实现 VolatilityAnalyzer（2h）
├── 实现 VolumeAnalyzer（2h）
└── 单元测试（1h）
```

### Phase 2: 适配池管理器（1天）

```
Day 3 (8h)
├── 创建 DailyPoolEvaluator（门面类）（3h）
├── PoolManager.evaluate_daily_entries()（新方法）（3h）
└── 集成测试（2h）
```

### Phase 3: 回测验证（1天）

```
Day 4 (8h)
├── BacktestEngine 适配（3h）
├── 历史数据回测（3h）
└── 参数调优（2h）
```

---

## 七、核心配置参数

### 7.1 阶段转换参数

```yaml
phase:
  # INITIAL -> PULLBACK 触发条件
  pullback_trigger_atr: 0.3      # 回调深度 > 0.3 ATR 视为进入回调

  # PULLBACK -> CONSOLIDATION 触发条件
  consolidation_trigger:
    min_convergence_score: 0.5   # 波动率收敛分数 > 0.5
    min_support_tests: 2         # 支撑位测试次数 >= 2

  # CONSOLIDATION -> REIGNITION 触发条件
  reignition_trigger:
    min_volume_expansion: 1.5    # 成交量放大倍数 >= 1.5x
    price_break_required: true   # 必须突破企稳区间上沿

  # 失败条件
  failure:
    max_drop_from_breakout_atr: 1.5  # 跌破突破价 1.5 ATR 失败
    support_break_buffer_atr: 0.5    # 跌破支撑位 0.5 ATR 失败
```

### 7.2 分析器参数

```yaml
price_analyzer:
  consolidation_window: 10       # 企稳区间计算窗口（天）
  support_detection:
    min_touches: 2               # 最少触及次数
    touch_tolerance_atr: 0.1     # 触及容差

volatility_analyzer:
  lookback_days: 20              # 波动率回看天数
  atr_period: 14                 # ATR 计算周期
  contraction_threshold: 0.8     # 收敛判定阈值

volume_analyzer:
  baseline_type: 'ma20'          # 基准类型
  expansion_threshold: 1.5       # 放量阈值
```

---

## 八、结论

### 8.1 核心发现

1. **当前架构是 Realtime-first 设计**：这不是缺陷，而是历史演化的结果
2. **核心抽象层设计优秀**：ITimeProvider, IPoolStorage, ObservationPoolBase 值得保留
3. **问题集中在评估器层**：加权模型不适合"过程评估"
4. **理想架构需要阶段机模型**：更准确地建模"回调-企稳-再启动"

### 8.2 最终建议

| 决策项 | 结论 |
|--------|------|
| 推荐方案 | **方案 C：重构评估器层** |
| 开发周期 | ~4 天 |
| 核心工作 | 新建 DailyPoolEvaluator + PhaseStateMachine |
| 复用代码 | 策略层、基础层、回测引擎核心 |
| 风险等级 | 低 |

### 8.3 一句话总结

**当前架构的"骨架"是好的，问题在"肌肉"（评估器）。不需要换骨架，但需要为 Daily 池重新设计评估肌肉。**

---

## 附录：可复用资产清单

| 组件 | 文件位置 | 复用程度 |
|------|---------|----------|
| ITimeProvider | `strategies/time_provider.py` | 100% |
| IPoolStorage | `strategies/storage.py` | 100% |
| BacktestTimeProvider | `strategies/time_provider.py` | 100% |
| MemoryStorage | `strategies/storage.py` | 100% |
| ObservationPoolBase | `pool_base.py` | 90% |
| PoolEntry（核心字段） | `pool_entry.py` | 80% |
| EvaluationResult | `evaluators/result.py` | 100% |
| BuySignal | `buy_signal.py` | 100% |
| RiskFilterEvaluator | `evaluators/components/risk_filter.py` | 100% |
| BaseEvaluator 辅助方法 | `evaluators/base.py` | 100% |

---

*报告完成于 2026-01-04*
