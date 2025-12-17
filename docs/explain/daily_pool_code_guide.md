# Daily Pool 代码指南

> 快速理解 `BreakoutStrategy/daily_pool/` 模块的运行逻辑

## 一句话总结

Daily Pool 是一个**阶段状态机系统**，监控突破后股票的"回调-企稳-再启动"过程，当完成完整周期后生成买入信号。

---

## 数据流程图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              回测/实时调用                                    │
│                                                                             │
│   Breakout 对象 ──────┬──────────────────────────────────────────────────►  │
│   (从 JSON 加载)       │                                                     │
│                       ▼                                                     │
│              ┌─────────────────┐                                            │
│              │ DailyPoolManager │  入口：管理所有池条目                        │
│              │   (manager/)     │                                            │
│              └────────┬────────┘                                            │
│                       │ add_entry_from_breakout()                           │
│                       │ update_all()                                        │
│                       ▼                                                     │
│              ┌─────────────────┐                                            │
│              │ DailyPoolEntry   │  每个突破对应一个条目                        │
│              │   (models/)      │  包含状态机实例                             │
│              └────────┬────────┘                                            │
│                       │                                                     │
│   DataFrame ──────────┼──────────────────────────────────────────────────►  │
│   (价格历史)           │                                                     │
│                       ▼                                                     │
│   ┌───────────────────────────────────────────────────────────────────┐    │
│   │                    DailyPoolEvaluator                              │    │
│   │                      (evaluator/)                                  │    │
│   │  ┌─────────────────────────────────────────────────────────────┐  │    │
│   │  │                   三维度分析器 (analyzers/)                   │  │    │
│   │  │                                                             │  │    │
│   │  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │  │    │
│   │  │  │PricePattern  │ │ Volatility   │ │   Volume     │        │  │    │
│   │  │  │  Analyzer    │ │  Analyzer    │ │  Analyzer    │        │  │    │
│   │  │  ├──────────────┤ ├──────────────┤ ├──────────────┤        │  │    │
│   │  │  │回调深度      │ │ATR收敛分数   │ │放量倍数      │        │  │    │
│   │  │  │支撑位检测    │ │波动状态      │ │量能趋势      │        │  │    │
│   │  │  │企稳区间      │ │              │ │              │        │  │    │
│   │  │  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘        │  │    │
│   │  │         │                │                │                │  │    │
│   │  └─────────┼────────────────┼────────────────┼────────────────┘  │    │
│   │            └────────────────┼────────────────┘                   │    │
│   │                             ▼                                    │    │
│   │                    ┌─────────────────┐                           │    │
│   │                    │AnalysisEvidence │  聚合三个分析结果           │    │
│   │                    │ (state_machine/)│                           │    │
│   │                    └────────┬────────┘                           │    │
│   │                             │                                    │    │
│   └─────────────────────────────┼────────────────────────────────────┘    │
│                                 ▼                                         │
│                    ┌─────────────────────┐                                │
│                    │  PhaseStateMachine   │  核心决策引擎                   │
│                    │   (state_machine/)   │                                │
│                    ├─────────────────────┤                                │
│                    │ INITIAL             │                                │
│                    │    ↓ (回调>0.3ATR)   │                                │
│                    │ PULLBACK            │                                │
│                    │    ↓ (收敛+支撑)     │                                │
│                    │ CONSOLIDATION       │                                │
│                    │    ↓ (放量突破)      │                                │
│                    │ REIGNITION          │                                │
│                    │    ↓ (确认)          │                                │
│                    │ SIGNAL ─────────────┼──► DailySignal 买入信号         │
│                    │                     │                                │
│                    │ FAILED / EXPIRED    │  (终态，移出池)                  │
│                    └─────────────────────┘                                │
│                                                                           │
└───────────────────────────────────────────────────────────────────────────┘
```

---

## 核心运行逻辑

### 每日更新流程 (`DailyPoolManager.update_all`)

```python
# 伪代码
for entry in active_entries:
    df = price_data[entry.symbol]  # 获取该股票价格数据

    # 1. 三维度分析
    price_result = price_analyzer.analyze(df, entry)      # 回调/支撑/区间
    volatility_result = volatility_analyzer.analyze(df)   # ATR收敛
    volume_result = volume_analyzer.analyze(df)           # 放量检测

    # 2. 聚合证据
    evidence = AnalysisEvidence(price_result, volatility_result, volume_result)

    # 3. 状态机判断
    transition = entry.phase_machine.process(evidence)

    # 4. 如果到达 SIGNAL 阶段，生成买入信号
    if entry.phase_machine.can_emit_signal():
        signal = generate_signal(entry, evidence)
        signals.append(signal)
```

### 状态机转换条件

| 当前阶段 | 目标阶段 | 转换条件 |
|---------|---------|---------|
| INITIAL | PULLBACK | `pullback_depth >= 0.3 ATR` |
| INITIAL | CONSOLIDATION | `convergence >= 0.5 AND pullback < 0.3` |
| PULLBACK | CONSOLIDATION | `convergence >= 0.5 AND support_tests >= 2` |
| CONSOLIDATION | REIGNITION | `volume >= 1.5x AND price > consolidation_top` |
| REIGNITION | SIGNAL | `days >= 1 AND still_above_top` |
| REIGNITION | CONSOLIDATION | 假突破回退 |
| ANY | FAILED | `pullback > 1.5 ATR` 或阶段超时 |
| ANY | EXPIRED | `total_days >= 30` |

---

## 目录结构与核心文件

```
BreakoutStrategy/daily_pool/
│
├── __init__.py              # 模块入口，导出26个组件
│
├── models/                  # 数据模型
│   ├── phase.py            # Phase 枚举 (7个阶段)
│   ├── entry.py            # DailyPoolEntry - 池条目核心类
│   ├── signal.py           # DailySignal - 买入信号
│   └── history.py          # PhaseTransition - 阶段转换记录
│
├── config/                  # 配置系统
│   ├── config.py           # 6个配置 dataclass
│   └── loader.py           # YAML 加载/保存
│
├── state_machine/           # 状态机 (核心决策)
│   ├── evidence.py         # AnalysisEvidence - 聚合证据
│   ├── transitions.py      # PhaseTransitionResult
│   └── machine.py          # PhaseStateMachine - 状态机实现 ⭐
│
├── analyzers/               # 三维度分析器
│   ├── results.py          # 5个结果数据类
│   ├── price_pattern.py    # PricePatternAnalyzer - 回调/支撑/区间
│   ├── volatility.py       # VolatilityAnalyzer - ATR收敛
│   └── volume.py           # VolumeAnalyzer - 放量检测
│
├── evaluator/               # 评估器
│   └── daily_evaluator.py  # DailyPoolEvaluator - 协调分析与状态机 ⭐
│
├── manager/                 # 管理器
│   └── pool_manager.py     # DailyPoolManager - 池管理入口 ⭐
│
└── backtest/                # 回测引擎
    └── engine.py           # DailyBacktestEngine
```

**核心文件 (⭐)**:
- `manager/pool_manager.py` - 外部调用入口
- `evaluator/daily_evaluator.py` - 评估流程协调
- `state_machine/machine.py` - 状态机决策逻辑

---

## 关键类速查

### DailyPoolEntry (池条目)

```python
@dataclass
class DailyPoolEntry:
    symbol: str                    # 股票代码
    entry_id: str                  # 唯一ID: "AAPL_2024-01-15"
    breakout_date: date            # 突破日期
    breakout_price: float          # 突破价格
    highest_peak_price: float      # 被突破的最高峰值
    initial_atr: float             # 突破时的ATR
    quality_score: float           # 突破质量评分

    phase_machine: PhaseStateMachine  # 状态机实例
    phase_history: PhaseHistory       # 阶段转换历史

    # 价格追踪
    post_breakout_high: float      # 突破后最高价
    post_breakout_low: float       # 突破后最低价
    current_price: float           # 当前价格

    @property
    def current_phase(self) -> Phase:
        return self.phase_machine.current_phase

    @property
    def is_active(self) -> bool:
        return self.current_phase not in [Phase.SIGNAL, Phase.FAILED, Phase.EXPIRED]
```

### AnalysisEvidence (分析证据)

```python
@dataclass
class AnalysisEvidence:
    as_of_date: date

    # 价格模式 (from PricePatternAnalyzer)
    pullback_depth_atr: float         # 回调深度 (ATR单位)
    support_strength: float           # 支撑强度 (0-1)
    support_tests_count: int          # 支撑测试次数
    price_above_consolidation_top: bool  # 价格是否突破区间上沿
    consolidation_valid: bool         # 企稳区间是否有效

    # 波动率 (from VolatilityAnalyzer)
    convergence_score: float          # 收敛分数 (0-1)
    volatility_state: str             # "contracting" / "stable" / "expanding"
    atr_ratio: float                  # 当前ATR / 初始ATR

    # 成交量 (from VolumeAnalyzer)
    volume_expansion_ratio: float     # 当前量 / 基准量
    surge_detected: bool              # 是否放量
    volume_trend: str                 # "increasing" / "decreasing" / "neutral"
```

### PhaseStateMachine (状态机)

```python
class PhaseStateMachine:
    def __init__(self, config: PhaseConfig, entry_date: date):
        self.current_phase = Phase.INITIAL
        self.phase_start_date = entry_date
        self.history: List[PhaseTransition] = []

    def process(self, evidence: AnalysisEvidence) -> PhaseTransitionResult:
        """核心方法：根据证据判断阶段转换"""
        # 0. 过期检查
        # 1. 全局失败检查 (回调过深)
        # 2. 阶段特定检查
        if self.current_phase == Phase.INITIAL:
            return self._eval_initial(evidence)
        elif self.current_phase == Phase.PULLBACK:
            return self._eval_pullback(evidence)
        # ...

    def can_emit_signal(self) -> bool:
        return self.current_phase == Phase.SIGNAL
```

---

## 配置文件

**位置**: `configs/daily_pool/default.yaml`

**策略预设**:
```python
DailyPoolConfig.default()       # 默认配置
DailyPoolConfig.conservative()  # 保守 (更严格的企稳要求)
DailyPoolConfig.aggressive()    # 激进 (更宽松的触发条件)
```

**关键参数**:
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `max_observation_days` | 30 | 最长观察期 |
| `pullback_trigger_atr` | 0.3 | 触发回调的阈值 |
| `min_convergence_score` | 0.5 | 进入企稳的收敛要求 |
| `min_volume_expansion` | 1.5 | 再启动的放量要求 |
| `max_drop_from_breakout_atr` | 1.5 | 最大允许回调 |

---

## 使用示例

### 基本使用

```python
from BreakoutStrategy.daily_pool import DailyPoolManager, DailyPoolConfig
from datetime import date

# 创建管理器
config = DailyPoolConfig.default()
manager = DailyPoolManager(config)

# 添加条目
entry = manager.add_entry(
    symbol='AAPL',
    breakout_date=date(2024, 1, 15),
    breakout_price=185.0,
    highest_peak_price=190.0,
    initial_atr=3.5,
    quality_score=75.0
)

# 每日更新 (收盘后调用)
signals = manager.update_all(as_of_date, price_data)
for signal in signals:
    print(signal.get_explanation())
```

### 回测

```bash
python scripts/backtest/daily_pool_backtest.py
```

```python
# 或在代码中
from BreakoutStrategy.daily_pool import DailyBacktestEngine, load_config

engine = DailyBacktestEngine(load_config('configs/daily_pool/default.yaml'))
result = engine.run(breakouts, price_data, start_date, end_date)
print(result.summary())
```

---

## 调试技巧

### 查看阶段转换历史

```python
entry = manager.get_entry("AAPL_2024-01-15")
for t in entry.phase_history.transitions:
    print(f"{t.transition_date}: {t.from_phase.name} -> {t.to_phase.name}")
    print(f"  Reason: {t.reason}")
```

### 查看当前证据

```python
# 在 DailyPoolEvaluator.evaluate() 中设置断点
# 或添加日志
evidence = self._build_evidence(price_result, volatility_result, volume_result, as_of_date)
print(evidence.get_summary())
```

### 理解为什么没有信号

常见原因：
1. `INITIAL->EXPIRED` (37次) - 没有明显回调或收敛，直接过期
2. `PULLBACK->FAILED` - 回调过深超过1.5 ATR
3. `CONSOLIDATION->EXPIRED` - 企稳太久没有再启动
4. `REIGNITION->CONSOLIDATION` - 假突破回退

---

## 与 Realtime 池的区别

| 维度 | Realtime 池 | Daily 池 |
|------|-------------|----------|
| 时间粒度 | 5分钟 | 日K |
| 评估模型 | 加权评分 (0-100) | 阶段状态机 |
| 核心问题 | "此刻是否买入?" | "经历了什么变化?" |
| 代码位置 | `observation/` | `daily_pool/` |
