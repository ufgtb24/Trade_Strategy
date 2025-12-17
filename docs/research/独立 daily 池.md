# Daily 池独立架构设计 (方案B)

> 版本: 1.0 | 日期: 2026-01-04
> 设计目标: 从零开始设计，不受现有 Realtime 池约束，构建纯 Daily 池的理想架构

---

## 1. 架构总览

### 1.1 设计理念

| 维度 | Realtime 池 (现有) | Daily 池 (本设计) |
|------|-------------------|------------------|
| 评估模型 | 加权评分 (0-100) | **阶段状态机** |
| 关注对象 | 当前状态快照 | **变化过程** |
| 输入数据 | 单条 K 线 | **历史序列** |
| 核心问题 | "此刻是否买入?" | **"经历了什么变化?"** |

### 1.2 分层架构

```
┌─────────────────────────────────────────────────────────────────┐
│ Layer 4: Application     │ DailyBacktestEngine, UIAdapter       │
├─────────────────────────────────────────────────────────────────┤
│ Layer 3: Management      │ DailyPoolManager (生命周期/信号收集)  │
├─────────────────────────────────────────────────────────────────┤
│ Layer 2: Evaluation      │ DailyPoolEvaluator + 3个Analyzer     │
│                          │ (PricePattern/Volatility/Volume)     │
├─────────────────────────────────────────────────────────────────┤
│ Layer 1: State Machine   │ PhaseStateMachine (阶段转换核心)      │
├─────────────────────────────────────────────────────────────────┤
│ Layer 0: Data Models     │ DailyPoolEntry, PhaseHistory, Signal │
└─────────────────────────────────────────────────────────────────┘
```

### 1.3 核心数据流

```
价格历史 DataFrame
       │
       ▼
┌──────┴──────┐──────────────┐──────────────┐
│ PricePattern│ Volatility   │ Volume       │
│ Analyzer    │ Analyzer     │ Analyzer     │
└──────┬──────┘──────┬───────┘──────┬───────┘
       │             │              │
       └─────────────┼──────────────┘
                     ▼
            AnalysisEvidence (聚合证据)
                     │
                     ▼
            PhaseStateMachine.process()
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
      HOLD       ADVANCE        SIGNAL
    (保持)      (阶段转换)    (生成信号)
```

---

## 2. 核心模块设计

### 2.1 数据模型

```python
# ===== Phase 枚举 =====
from enum import Enum, auto

class Phase(Enum):
    INITIAL = auto()        # 刚入池
    PULLBACK = auto()       # 回调中
    CONSOLIDATION = auto()  # 企稳整理
    REIGNITION = auto()     # 再启动
    SIGNAL = auto()         # 信号已生成
    FAILED = auto()         # 失败
    EXPIRED = auto()        # 过期


# ===== DailyPoolEntry =====
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, Any, List

@dataclass
class DailyPoolEntry:
    """Daily 池条目 - 核心数据结构"""

    # 标识
    symbol: str
    entry_id: str

    # 突破信息 (不可变)
    breakout_date: date
    breakout_price: float
    highest_peak_price: float
    initial_atr: float
    quality_score: float

    # 阶段状态机
    phase_machine: 'PhaseStateMachine' = field(default=None)
    phase_history: 'PhaseHistory' = field(default_factory=lambda: PhaseHistory())

    # 价格追踪
    post_breakout_high: float = 0.0
    post_breakout_low: float = float('inf')
    current_price: float = 0.0

    # 分析缓存 (避免重复计算)
    analysis_cache: Dict[str, Any] = field(default_factory=dict)

    @property
    def current_phase(self) -> Phase:
        return self.phase_machine.current_phase

    @property
    def is_active(self) -> bool:
        return self.current_phase not in {Phase.SIGNAL, Phase.FAILED, Phase.EXPIRED}

    @property
    def days_in_pool(self) -> int:
        """入池天数"""
        return (date.today() - self.breakout_date).days

    def update_price_tracking(self, high: float, low: float, close: float):
        """更新价格追踪"""
        self.post_breakout_high = max(self.post_breakout_high, high)
        self.post_breakout_low = min(self.post_breakout_low, low)
        self.current_price = close


# ===== PhaseHistory =====
@dataclass
class PhaseTransition:
    """阶段转换记录"""
    from_phase: Phase
    to_phase: Phase
    transition_date: date
    reason: str
    evidence_snapshot: Dict[str, Any]

@dataclass
class PhaseHistory:
    """阶段历史记录"""
    transitions: List[PhaseTransition] = field(default_factory=list)

    def add_transition(self, transition: PhaseTransition):
        self.transitions.append(transition)

    def get_days_in_phase(self, phase: Phase, current_date: date) -> int:
        """获取在某阶段停留的天数"""
        for t in reversed(self.transitions):
            if t.to_phase == phase:
                return (current_date - t.transition_date).days
        return 0


# ===== DailySignal =====
from enum import Enum

class SignalType(Enum):
    REIGNITION_BUY = "reignition_buy"  # 再启动买入

class SignalStrength(Enum):
    STRONG = "strong"
    NORMAL = "normal"
    WEAK = "weak"

@dataclass
class DailySignal:
    """Daily 池买入信号"""
    symbol: str
    signal_date: date
    signal_type: SignalType
    strength: SignalStrength

    # 交易参数
    entry_price: float
    stop_loss_price: float
    position_size_pct: float

    # 可解释性 (为什么生成这个信号)
    phase_when_signaled: Phase
    days_to_signal: int
    evidence_summary: Dict[str, Any]
    confidence: float  # 0-1

    def get_explanation(self) -> str:
        """生成信号的可读解释"""
        return (
            f"{self.symbol} 触发 {self.signal_type.value} 信号:\n"
            f"  - 入池到信号: {self.days_to_signal} 天\n"
            f"  - 信号强度: {self.strength.value}\n"
            f"  - 置信度: {self.confidence:.1%}\n"
            f"  - 建议入场价: ${self.entry_price:.2f}\n"
            f"  - 建议止损价: ${self.stop_loss_price:.2f}\n"
            f"  - 建议仓位: {self.position_size_pct:.1%}"
        )
```

### 2.2 分析器组件

```python
# ===== 分析结果数据类 =====
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class SupportZone:
    """支撑区域"""
    price_low: float
    price_high: float
    test_count: int
    strength: float  # 0-1
    first_test_date: date
    last_test_date: date

@dataclass
class ConsolidationRange:
    """企稳区间"""
    upper_bound: float
    lower_bound: float
    center: float
    width_atr: float
    is_valid: bool

@dataclass
class PricePatternResult:
    """价格模式分析结果"""
    pullback_depth_atr: float           # 回调深度 (ATR单位)
    support_zones: List[SupportZone]    # 支撑区间列表
    consolidation_range: Optional[ConsolidationRange]  # 企稳区间
    price_position: str                 # "above_range" | "in_range" | "below_range"
    strongest_support: Optional[SupportZone]

@dataclass
class VolatilityResult:
    """波动率分析结果"""
    current_atr: float
    atr_ratio: float           # 当前ATR / 初始ATR
    convergence_score: float   # 收敛分数 (0-1)
    volatility_state: str      # "contracting" | "stable" | "expanding"

@dataclass
class VolumeResult:
    """成交量分析结果"""
    baseline_volume: float
    current_volume: float
    volume_expansion_ratio: float  # 当前量 / 基准量
    surge_detected: bool           # 是否放量 (ratio >= threshold)
    volume_trend: str              # "increasing" | "neutral" | "decreasing"


# ===== 价格模式分析器 =====
import pandas as pd
import numpy as np

class PricePatternAnalyzer:
    """
    价格模式分析器

    职责:
    - 检测回调深度
    - 识别支撑位
    - 计算企稳区间
    """

    def __init__(self, config: 'PricePatternConfig'):
        self.config = config

    def analyze(self, df: pd.DataFrame, entry: DailyPoolEntry,
                as_of_date: date) -> PricePatternResult:
        """
        分析价格模式

        Args:
            df: 包含 OHLCV 的 DataFrame, 已截止到 as_of_date
            entry: 池条目
            as_of_date: 分析日期

        Returns:
            PricePatternResult
        """
        # 回调深度
        pullback_depth = self._calculate_pullback_depth(df, entry)

        # 支撑位检测
        support_zones = self._detect_support_zones(df, entry.initial_atr)

        # 企稳区间
        consolidation_range = self._calculate_consolidation_range(
            df, entry.initial_atr
        )

        # 价格位置
        price_position = self._determine_price_position(
            df['close'].iloc[-1], consolidation_range
        )

        return PricePatternResult(
            pullback_depth_atr=pullback_depth,
            support_zones=support_zones,
            consolidation_range=consolidation_range,
            price_position=price_position,
            strongest_support=support_zones[0] if support_zones else None
        )

    def _calculate_pullback_depth(self, df: pd.DataFrame,
                                   entry: DailyPoolEntry) -> float:
        """计算从突破后高点的回调深度 (ATR单位)"""
        current_price = df['close'].iloc[-1]
        drop = entry.post_breakout_high - current_price
        return drop / entry.initial_atr if entry.initial_atr > 0 else 0.0

    def _detect_support_zones(self, df: pd.DataFrame,
                               atr: float) -> List[SupportZone]:
        """
        检测支撑区域

        算法:
        1. 找局部最低点 (low[i] < low[i-w:i+w])
        2. 按价格聚类 (容差 = 0.1 ATR)
        3. 过滤: 测试次数 >= min_touches
        4. 计算强度
        """
        lows = df['low'].values
        dates = df.index
        tolerance = self.config.touch_tolerance_atr * atr
        window = self.config.local_min_window

        # Step 1: 找局部最低点
        local_mins = []
        for i in range(window, len(lows) - window):
            window_slice = lows[max(0, i-window) : i+window+1]
            if lows[i] == min(window_slice):
                local_mins.append((dates[i], lows[i]))

        if not local_mins:
            return []

        # Step 2: 按价格聚类
        clusters = self._cluster_by_price(local_mins, tolerance)

        # Step 3 & 4: 过滤并构建 SupportZone
        zones = []
        for cluster in clusters:
            if len(cluster) >= self.config.min_touches:
                prices = [p for _, p in cluster]
                dates_in_cluster = [d for d, _ in cluster]

                strength = self._calculate_support_strength(cluster)

                zones.append(SupportZone(
                    price_low=min(prices),
                    price_high=max(prices),
                    test_count=len(cluster),
                    strength=strength,
                    first_test_date=min(dates_in_cluster),
                    last_test_date=max(dates_in_cluster)
                ))

        return sorted(zones, key=lambda z: z.strength, reverse=True)

    def _cluster_by_price(self, points: List, tolerance: float) -> List[List]:
        """按价格聚类"""
        if not points:
            return []

        sorted_points = sorted(points, key=lambda x: x[1])
        clusters = [[sorted_points[0]]]

        for point in sorted_points[1:]:
            if point[1] - clusters[-1][-1][1] <= tolerance:
                clusters[-1].append(point)
            else:
                clusters.append([point])

        return clusters

    def _calculate_support_strength(self, cluster: List) -> float:
        """
        计算支撑强度

        公式: strength = 0.4 * (测试次数/5) + 0.3 * (时间跨度/15天) + 0.3 * 反弹质量
        """
        count_score = min(len(cluster) / 5, 1.0) * 0.4

        dates = [d for d, _ in cluster]
        if len(dates) > 1:
            span_days = (max(dates) - min(dates)).days
            span_score = min(span_days / 15, 1.0) * 0.3
        else:
            span_score = 0.0

        bounce_score = 0.3  # 简化: 假设反弹质量良好

        return count_score + span_score + bounce_score

    def _calculate_consolidation_range(self, df: pd.DataFrame,
                                        atr: float) -> Optional[ConsolidationRange]:
        """
        计算企稳区间

        区间 = mean ± 1.5 * std
        有效性: 宽度 <= max_width_atr
        """
        if len(df) < self.config.consolidation_window:
            return None

        closes = df.tail(self.config.consolidation_window)['close'].values

        mean_price = np.mean(closes)
        std_price = np.std(closes)

        upper = mean_price + 1.5 * std_price
        lower = mean_price - 1.5 * std_price

        width_atr = (upper - lower) / atr if atr > 0 else float('inf')
        is_valid = width_atr <= self.config.max_width_atr

        return ConsolidationRange(
            upper_bound=upper,
            lower_bound=lower,
            center=mean_price,
            width_atr=width_atr,
            is_valid=is_valid
        )

    def _determine_price_position(self, current_price: float,
                                   consolidation: Optional[ConsolidationRange]) -> str:
        """判断当前价格相对于企稳区间的位置"""
        if consolidation is None:
            return "unknown"

        if current_price > consolidation.upper_bound:
            return "above_range"
        elif current_price < consolidation.lower_bound:
            return "below_range"
        else:
            return "in_range"


# ===== 波动率分析器 =====
class VolatilityAnalyzer:
    """
    波动率分析器

    职责:
    - 计算 ATR 序列
    - 检测波动率收敛
    - 评估收敛分数
    """

    def __init__(self, config: 'VolatilityConfig'):
        self.config = config

    def analyze(self, df: pd.DataFrame, initial_atr: float,
                as_of_date: date) -> VolatilityResult:
        """
        分析波动率状态

        Args:
            df: OHLCV DataFrame
            initial_atr: 突破时的 ATR
            as_of_date: 分析日期

        Returns:
            VolatilityResult
        """
        # 计算 ATR 序列
        atr_series = self._calculate_atr_series(df, self.config.atr_period)
        current_atr = atr_series.iloc[-1] if len(atr_series) > 0 else initial_atr

        # ATR 比率
        atr_ratio = current_atr / initial_atr if initial_atr > 0 else 1.0

        # 收敛分数
        convergence_score = self._calculate_convergence_score(
            atr_series.tolist(), initial_atr
        )

        # 波动状态
        volatility_state = self._determine_volatility_state(atr_ratio, convergence_score)

        return VolatilityResult(
            current_atr=current_atr,
            atr_ratio=atr_ratio,
            convergence_score=convergence_score,
            volatility_state=volatility_state
        )

    def _calculate_atr_series(self, df: pd.DataFrame, period: int) -> pd.Series:
        """计算 ATR 序列"""
        high = df['high']
        low = df['low']
        close = df['close']

        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()

        return atr.dropna()

    def _calculate_convergence_score(self, atr_series: List[float],
                                      initial_atr: float) -> float:
        """
        计算收敛分数

        公式: score = 斜率分数(0.5) + ATR比率分数(0.3) + 稳定性分数(0.2)
        """
        if len(atr_series) < 5:
            return 0.0

        recent = atr_series[-self.config.lookback_days:]
        current_atr = recent[-1]

        # 1. 斜率分数: 线性回归斜率, 负值得分
        slope = self._linear_regression_slope(recent)
        normalized_slope = slope / np.mean(recent) if np.mean(recent) > 0 else 0

        if slope < 0:
            slope_score = min(abs(normalized_slope) / 0.05, 1.0) * 0.5
        else:
            slope_score = 0

        # 2. ATR 比率分数: 当前/初始 越小越好
        atr_ratio = current_atr / initial_atr if initial_atr > 0 else 1.0

        if atr_ratio <= self.config.contraction_threshold:
            ratio_score = 0.3
        elif atr_ratio <= 1.0:
            ratio_score = 0.3 * (1.0 - atr_ratio) / (1.0 - self.config.contraction_threshold)
        else:
            ratio_score = 0

        # 3. 稳定性分数: 变异系数 (CV) 越小越好
        last_5 = recent[-5:]
        mean_val = np.mean(last_5)
        cv = np.std(last_5) / mean_val if mean_val > 0 else 1.0
        stability_score = max(0, 0.2 * (1 - cv / 0.3))

        return slope_score + ratio_score + stability_score

    def _linear_regression_slope(self, values: List[float]) -> float:
        """计算线性回归斜率"""
        n = len(values)
        x = np.arange(n)
        y = np.array(values)

        x_mean = np.mean(x)
        y_mean = np.mean(y)

        numerator = np.sum((x - x_mean) * (y - y_mean))
        denominator = np.sum((x - x_mean) ** 2)

        return numerator / denominator if denominator > 0 else 0.0

    def _determine_volatility_state(self, atr_ratio: float,
                                     convergence_score: float) -> str:
        """判断波动率状态"""
        if convergence_score >= 0.5 and atr_ratio < 1.0:
            return "contracting"
        elif convergence_score < 0.3 or atr_ratio > 1.2:
            return "expanding"
        else:
            return "stable"


# ===== 成交量分析器 =====
class VolumeAnalyzer:
    """
    成交量分析器

    职责:
    - 计算基准成交量
    - 检测放量
    - 判断成交量趋势
    """

    def __init__(self, config: 'VolumeConfig'):
        self.config = config

    def analyze(self, df: pd.DataFrame, as_of_date: date) -> VolumeResult:
        """
        分析成交量

        Args:
            df: OHLCV DataFrame
            as_of_date: 分析日期

        Returns:
            VolumeResult
        """
        volume = df['volume']

        # 基准量: MA(baseline_period)
        baseline = volume.tail(self.config.baseline_period).mean()
        current = volume.iloc[-1]

        # 放量比率
        ratio = current / baseline if baseline > 0 else 1.0

        # 放量检测
        surge_detected = ratio >= self.config.expansion_threshold

        # 趋势判断
        volume_trend = self._determine_volume_trend(volume)

        return VolumeResult(
            baseline_volume=baseline,
            current_volume=current,
            volume_expansion_ratio=ratio,
            surge_detected=surge_detected,
            volume_trend=volume_trend
        )

    def _determine_volume_trend(self, volume: pd.Series) -> str:
        """
        判断成交量趋势

        比较短期MA和长期MA
        """
        if len(volume) < 20:
            return "neutral"

        short_ma = volume.tail(5).mean()
        long_ma = volume.tail(20).mean()

        if short_ma > long_ma * 1.1:
            return "increasing"
        elif short_ma < long_ma * 0.9:
            return "decreasing"
        else:
            return "neutral"
```

### 2.3 阶段状态机

```python
# ===== AnalysisEvidence =====
@dataclass
class AnalysisEvidence:
    """
    分析证据聚合

    由 DailyPoolEvaluator 从三个 Analyzer 的结果中构建
    作为 PhaseStateMachine.process() 的输入
    """
    as_of_date: date

    # 价格模式证据
    pullback_depth_atr: float
    support_strength: float
    support_tests_count: int
    price_above_consolidation_top: bool
    consolidation_valid: bool

    # 波动率证据
    convergence_score: float
    volatility_state: str
    atr_ratio: float

    # 成交量证据
    volume_expansion_ratio: float
    surge_detected: bool
    volume_trend: str


# ===== PhaseStateMachine =====
@dataclass
class PhaseTransitionResult:
    """阶段转换结果"""
    action: str  # "hold" | "advance" | "fail" | "expire"
    from_phase: Phase
    to_phase: Phase
    reason: str
    evidence: AnalysisEvidence

class PhaseStateMachine:
    """
    阶段状态机

    核心职责:
    - 管理阶段状态
    - 根据证据判断阶段转换
    - 记录转换历史
    """

    def __init__(self, config: 'PhaseConfig', entry_date: date):
        self.current_phase = Phase.INITIAL
        self.config = config
        self.phase_start_date = entry_date
        self.entry_date = entry_date
        self.history: List[PhaseTransition] = []

    def process(self, evidence: AnalysisEvidence) -> PhaseTransitionResult:
        """
        核心方法: 根据证据判断阶段转换

        Args:
            evidence: 聚合的分析证据

        Returns:
            PhaseTransitionResult 描述转换动作
        """
        # 0. 过期检查 (全局)
        total_days = (evidence.as_of_date - self.entry_date).days
        if total_days >= self.config.max_observation_days:
            return self._transition_to(Phase.EXPIRED, "Observation period expired", evidence)

        # 1. 全局失败检查
        if evidence.pullback_depth_atr > self.config.max_drop_from_breakout_atr:
            return self._transition_to(Phase.FAILED,
                f"Pullback too deep: {evidence.pullback_depth_atr:.2f} ATR", evidence)

        # 2. 阶段特定检查
        if self.current_phase == Phase.INITIAL:
            return self._eval_initial(evidence)
        elif self.current_phase == Phase.PULLBACK:
            return self._eval_pullback(evidence)
        elif self.current_phase == Phase.CONSOLIDATION:
            return self._eval_consolidation(evidence)
        elif self.current_phase == Phase.REIGNITION:
            return self._eval_reignition(evidence)

        # 终态不再转换
        return self._hold(evidence)

    def _eval_initial(self, evidence: AnalysisEvidence) -> PhaseTransitionResult:
        """INITIAL 阶段评估"""
        # 直接进入企稳 (无明显回调但波动收敛)
        if (evidence.pullback_depth_atr < self.config.pullback_trigger_atr and
            evidence.convergence_score >= self.config.min_convergence_score):
            return self._transition_to(Phase.CONSOLIDATION,
                "Direct to consolidation: no pullback, volatility converging", evidence)

        # 进入回调
        if evidence.pullback_depth_atr >= self.config.pullback_trigger_atr:
            return self._transition_to(Phase.PULLBACK,
                f"Entering pullback: depth={evidence.pullback_depth_atr:.2f} ATR", evidence)

        return self._hold(evidence)

    def _eval_pullback(self, evidence: AnalysisEvidence) -> PhaseTransitionResult:
        """PULLBACK 阶段评估"""
        days_in_phase = self._days_in_current_phase(evidence.as_of_date)

        # 超时失败
        if days_in_phase > self.config.max_pullback_days:
            return self._transition_to(Phase.FAILED,
                f"Pullback timeout: {days_in_phase} days", evidence)

        # 进入企稳: 波动收敛 + 支撑形成
        if (evidence.convergence_score >= self.config.min_convergence_score and
            evidence.support_tests_count >= self.config.min_support_tests):
            return self._transition_to(Phase.CONSOLIDATION,
                f"Entering consolidation: convergence={evidence.convergence_score:.2f}, "
                f"support_tests={evidence.support_tests_count}", evidence)

        return self._hold(evidence)

    def _eval_consolidation(self, evidence: AnalysisEvidence) -> PhaseTransitionResult:
        """CONSOLIDATION 阶段评估"""
        days_in_phase = self._days_in_current_phase(evidence.as_of_date)

        # 超时失败
        if days_in_phase > self.config.max_consolidation_days:
            return self._transition_to(Phase.FAILED,
                f"Consolidation timeout: {days_in_phase} days", evidence)

        # 再启动: 放量 + 突破区间上沿
        if (evidence.volume_expansion_ratio >= self.config.min_volume_expansion and
            evidence.price_above_consolidation_top):
            return self._transition_to(Phase.REIGNITION,
                f"Reignition triggered: volume={evidence.volume_expansion_ratio:.1f}x", evidence)

        return self._hold(evidence)

    def _eval_reignition(self, evidence: AnalysisEvidence) -> PhaseTransitionResult:
        """REIGNITION 阶段评估"""
        days_in_phase = self._days_in_current_phase(evidence.as_of_date)

        # 假突破回退
        if not evidence.price_above_consolidation_top:
            return self._transition_to(Phase.CONSOLIDATION,
                "False breakout: price fell back into range", evidence)

        # 确认信号
        if days_in_phase >= self.config.breakout_confirm_days:
            return self._transition_to(Phase.SIGNAL,
                f"Signal confirmed after {days_in_phase} days", evidence)

        return self._hold(evidence)

    def _transition_to(self, to_phase: Phase, reason: str,
                        evidence: AnalysisEvidence) -> PhaseTransitionResult:
        """执行阶段转换"""
        from_phase = self.current_phase

        # 记录历史
        transition = PhaseTransition(
            from_phase=from_phase,
            to_phase=to_phase,
            transition_date=evidence.as_of_date,
            reason=reason,
            evidence_snapshot={
                'pullback_depth_atr': evidence.pullback_depth_atr,
                'convergence_score': evidence.convergence_score,
                'volume_ratio': evidence.volume_expansion_ratio,
            }
        )
        self.history.append(transition)

        # 更新状态
        self.current_phase = to_phase
        self.phase_start_date = evidence.as_of_date

        action = "fail" if to_phase == Phase.FAILED else \
                 "expire" if to_phase == Phase.EXPIRED else "advance"

        return PhaseTransitionResult(
            action=action,
            from_phase=from_phase,
            to_phase=to_phase,
            reason=reason,
            evidence=evidence
        )

    def _hold(self, evidence: AnalysisEvidence) -> PhaseTransitionResult:
        """保持当前阶段"""
        return PhaseTransitionResult(
            action="hold",
            from_phase=self.current_phase,
            to_phase=self.current_phase,
            reason="Conditions not met for transition",
            evidence=evidence
        )

    def _days_in_current_phase(self, as_of_date: date) -> int:
        """计算在当前阶段的天数"""
        return (as_of_date - self.phase_start_date).days

    def can_emit_signal(self) -> bool:
        """是否可以发出信号"""
        return self.current_phase == Phase.SIGNAL
```

---

## 3. 阶段转换详解

### 3.1 完整状态转换图

```
                              ┌─────────────┐
                              │   INITIAL   │
                              └──────┬──────┘
                                     │
              ┌──────────────────────┼──────────────────────┐
              │                      │                      │
              ▼                      │                      ▼
   回调 > 0.3 ATR                    │           收敛 > 0.5 且无明显回调
              │                      │                      │
     ┌────────┴────────┐             │             ┌────────┴────────┐
     │    PULLBACK     │             │             │                 │
     │  (最长15天)     │─────────────┼─────────────│  CONSOLIDATION  │
     └────────┬────────┘             │             │   (最长20天)    │
              │                      │             └────────┬────────┘
              │ 收敛 + 支撑形成      │                      │
              └──────────────────────┴──────────────────────┤
                                                            │
                                                            │ 放量 >= 1.5x
                                                            │ + 突破区间上沿
                                                            ▼
                                                   ┌────────────────┐
                                                   │  REIGNITION    │
                                            ┌──────┤  (确认中)      │
                                            │      └────────┬───────┘
                                            │               │
                                假突破回退   │               │ 维持 >= 1天
                                            │               ▼
                                            │      ┌────────────────┐
                                            │      │    SIGNAL      │
                                            │      │  (生成信号)    │
                                            │      └────────────────┘
                                            │
                                            └────► 回到 CONSOLIDATION

    任意阶段 ──────────────────────────────────────────► FAILED
              (回调 > 1.5 ATR 或 跌破支撑 或 阶段超时)

    任意阶段 ──────────────────────────────────────────► EXPIRED
              (观察期满 30 天)
```

### 3.2 转换条件详表

| 当前阶段 | 目标阶段 | 转换条件 | 业务含义 |
|---------|---------|---------|---------|
| INITIAL | PULLBACK | `pullback_depth_atr >= 0.3` | 突破后开始回调 |
| INITIAL | CONSOLIDATION | `convergence_score >= 0.5 AND pullback_depth_atr < 0.3` | 直接进入横盘整理 |
| PULLBACK | CONSOLIDATION | `convergence_score >= 0.5 AND support_tests >= 2` | 回调企稳，支撑形成 |
| PULLBACK | FAILED | `days_in_phase > 15 OR pullback_depth_atr > 1.5` | 回调过深或过久 |
| CONSOLIDATION | REIGNITION | `volume_ratio >= 1.5 AND price_above_top` | 放量突破整理区间 |
| CONSOLIDATION | FAILED | `days_in_phase > 20 OR broke_support` | 整理过久或破位 |
| REIGNITION | SIGNAL | `days_in_phase >= 1 AND still_above_top` | 突破确认 |
| REIGNITION | CONSOLIDATION | `NOT price_above_top` | 假突破回退 |
| ANY | FAILED | `pullback_depth_atr > 1.5` | 全局止损 |
| ANY | EXPIRED | `total_days >= 30` | 观察期满 |

### 3.3 各阶段业务语义

| 阶段 | 业务含义 | 持续时间预期 | 关键观察指标 |
|------|---------|-------------|-------------|
| **INITIAL** | 刚入池，等待行情发展 | 1-3天 | 价格走向 |
| **PULLBACK** | 健康回调，寻找支撑 | 3-15天 | 回调深度、支撑测试 |
| **CONSOLIDATION** | 企稳整理，蓄势待发 | 5-20天 | 波动收敛、区间宽度 |
| **REIGNITION** | 放量启动，等待确认 | 1-3天 | 量能、价格维持 |
| **SIGNAL** | 信号生成，可以交易 | 终态 | - |
| **FAILED** | 观察失败，移出池 | 终态 | - |
| **EXPIRED** | 观察期满，移出池 | 终态 | - |

---

## 4. 评估器与管理器

### 4.1 DailyPoolEvaluator

```python
@dataclass
class PhaseEvaluation:
    """评估结果"""
    transition: PhaseTransitionResult
    signal: Optional[DailySignal]
    entry_updated: bool

class DailyPoolEvaluator:
    """
    Daily 池评估器

    核心职责:
    - 协调三个分析器
    - 聚合分析证据
    - 驱动状态机
    - 生成买入信号
    """

    def __init__(self, config: 'DailyPoolConfig'):
        self.config = config
        self.price_analyzer = PricePatternAnalyzer(config.price_pattern)
        self.volatility_analyzer = VolatilityAnalyzer(config.volatility)
        self.volume_analyzer = VolumeAnalyzer(config.volume)

    def evaluate(self, entry: DailyPoolEntry, df: pd.DataFrame,
                 as_of_date: date) -> PhaseEvaluation:
        """
        评估单个条目

        Args:
            entry: 池条目
            df: 截止到 as_of_date 的 OHLCV DataFrame
            as_of_date: 评估日期

        Returns:
            PhaseEvaluation
        """
        # 更新价格追踪
        latest = df.iloc[-1]
        entry.update_price_tracking(
            high=latest['high'],
            low=latest['low'],
            close=latest['close']
        )

        # 1. 三维度分析
        price_result = self.price_analyzer.analyze(df, entry, as_of_date)
        volatility_result = self.volatility_analyzer.analyze(
            df, entry.initial_atr, as_of_date
        )
        volume_result = self.volume_analyzer.analyze(df, as_of_date)

        # 2. 聚合证据
        evidence = self._build_evidence(
            price_result, volatility_result, volume_result, as_of_date
        )

        # 3. 驱动状态机
        transition = entry.phase_machine.process(evidence)

        # 4. 更新历史
        if transition.action != "hold":
            entry.phase_history.add_transition(PhaseTransition(
                from_phase=transition.from_phase,
                to_phase=transition.to_phase,
                transition_date=as_of_date,
                reason=transition.reason,
                evidence_snapshot=self._evidence_to_dict(evidence)
            ))

        # 5. 生成信号 (如果到达 SIGNAL 阶段)
        signal = None
        if entry.phase_machine.can_emit_signal():
            signal = self._generate_signal(entry, evidence, df)

        return PhaseEvaluation(
            transition=transition,
            signal=signal,
            entry_updated=True
        )

    def _build_evidence(self, price: PricePatternResult,
                        volatility: VolatilityResult,
                        volume: VolumeResult,
                        as_of_date: date) -> AnalysisEvidence:
        """从三个分析结果构建证据"""
        return AnalysisEvidence(
            as_of_date=as_of_date,
            # 价格模式
            pullback_depth_atr=price.pullback_depth_atr,
            support_strength=price.strongest_support.strength if price.strongest_support else 0,
            support_tests_count=price.strongest_support.test_count if price.strongest_support else 0,
            price_above_consolidation_top=(price.price_position == "above_range"),
            consolidation_valid=price.consolidation_range.is_valid if price.consolidation_range else False,
            # 波动率
            convergence_score=volatility.convergence_score,
            volatility_state=volatility.volatility_state,
            atr_ratio=volatility.atr_ratio,
            # 成交量
            volume_expansion_ratio=volume.volume_expansion_ratio,
            surge_detected=volume.surge_detected,
            volume_trend=volume.volume_trend
        )

    def _generate_signal(self, entry: DailyPoolEntry,
                          evidence: AnalysisEvidence,
                          df: pd.DataFrame) -> DailySignal:
        """生成买入信号"""
        # 计算置信度
        confidence = self._calculate_confidence(evidence, entry)

        # 确定信号强度
        strength = self._determine_strength(confidence)

        # 计算交易参数
        current_price = entry.current_price
        stop_loss = self._calculate_stop_loss(entry, df)
        position_pct = self.config.signal.position_sizing[strength.value]

        return DailySignal(
            symbol=entry.symbol,
            signal_date=evidence.as_of_date,
            signal_type=SignalType.REIGNITION_BUY,
            strength=strength,
            entry_price=current_price,
            stop_loss_price=stop_loss,
            position_size_pct=position_pct,
            phase_when_signaled=entry.current_phase,
            days_to_signal=entry.days_in_pool,
            evidence_summary=self._evidence_to_dict(evidence),
            confidence=confidence
        )

    def _calculate_confidence(self, evidence: AnalysisEvidence,
                               entry: DailyPoolEntry) -> float:
        """
        计算置信度

        公式: confidence = w1*收敛分数 + w2*支撑强度 + w3*放量程度 + w4*突破质量
        """
        weights = self.config.signal.confidence_weights

        convergence_score = evidence.convergence_score * weights['convergence']
        support_score = evidence.support_strength * weights['support']
        volume_score = min(evidence.volume_expansion_ratio / 2.0, 1.0) * weights['volume']
        quality_score = min(entry.quality_score / 100, 1.0) * weights['quality']

        return convergence_score + support_score + volume_score + quality_score

    def _determine_strength(self, confidence: float) -> SignalStrength:
        """根据置信度确定信号强度"""
        if confidence >= 0.7:
            return SignalStrength.STRONG
        elif confidence >= 0.5:
            return SignalStrength.NORMAL
        else:
            return SignalStrength.WEAK

    def _calculate_stop_loss(self, entry: DailyPoolEntry,
                              df: pd.DataFrame) -> float:
        """
        计算止损价

        策略: 取最近支撑位下方 0.5 ATR
        """
        # 简化: 使用最近低点 - 0.5 ATR
        recent_low = df.tail(10)['low'].min()
        stop_loss = recent_low - 0.5 * entry.initial_atr
        return stop_loss

    def _evidence_to_dict(self, evidence: AnalysisEvidence) -> Dict[str, Any]:
        """将证据转为字典 (用于记录/调试)"""
        return {
            'pullback_depth_atr': round(evidence.pullback_depth_atr, 3),
            'convergence_score': round(evidence.convergence_score, 3),
            'support_tests': evidence.support_tests_count,
            'volume_ratio': round(evidence.volume_expansion_ratio, 2),
            'volatility_state': evidence.volatility_state,
            'price_position': 'above' if evidence.price_above_consolidation_top else 'in/below'
        }
```

### 4.2 DailyPoolManager

```python
from typing import Dict, List, Iterator
from datetime import date

class DailyPoolManager:
    """
    Daily 池管理器

    核心职责:
    - 管理条目生命周期 (添加、更新、移除)
    - 协调每日评估
    - 收集和分发信号
    - 提供统计信息
    """

    def __init__(self, config: 'DailyPoolConfig'):
        self.config = config
        self.evaluator = DailyPoolEvaluator(config)
        self._entries: Dict[str, DailyPoolEntry] = {}  # entry_id -> entry
        self._signals: List[DailySignal] = []

    def add_entry(self, breakout: 'Breakout', as_of_date: date) -> DailyPoolEntry:
        """
        添加新条目到池中

        Args:
            breakout: 突破信息
            as_of_date: 入池日期

        Returns:
            新创建的 DailyPoolEntry
        """
        entry_id = f"{breakout.symbol}_{as_of_date.isoformat()}"

        entry = DailyPoolEntry(
            symbol=breakout.symbol,
            entry_id=entry_id,
            breakout_date=as_of_date,
            breakout_price=breakout.breakout_price,
            highest_peak_price=breakout.highest_peak_price,
            initial_atr=breakout.atr,
            quality_score=breakout.quality_score,
            phase_machine=PhaseStateMachine(
                config=self.config.phase,
                entry_date=as_of_date
            ),
            phase_history=PhaseHistory(),
            post_breakout_high=breakout.highest_peak_price,
            post_breakout_low=breakout.breakout_price,
            current_price=breakout.breakout_price
        )

        self._entries[entry_id] = entry
        return entry

    def update_all(self, as_of_date: date,
                   price_data: Dict[str, pd.DataFrame]) -> List[DailySignal]:
        """
        更新所有活跃条目 (每日收盘后调用)

        Args:
            as_of_date: 当前日期
            price_data: symbol -> DataFrame 的映射

        Returns:
            新生成的信号列表
        """
        new_signals = []

        for entry in self.get_active_entries():
            if entry.symbol not in price_data:
                continue

            df = price_data[entry.symbol]
            # 截止到 as_of_date
            df_until = df[df.index <= pd.Timestamp(as_of_date)]

            if len(df_until) == 0:
                continue

            # 评估
            evaluation = self.evaluator.evaluate(entry, df_until, as_of_date)

            # 收集信号
            if evaluation.signal:
                new_signals.append(evaluation.signal)
                self._signals.append(evaluation.signal)

        # 清理终态条目
        self._cleanup_finished_entries()

        return new_signals

    def get_active_entries(self) -> List[DailyPoolEntry]:
        """获取所有活跃条目"""
        return [e for e in self._entries.values() if e.is_active]

    def get_entry(self, entry_id: str) -> Optional[DailyPoolEntry]:
        """根据 ID 获取条目"""
        return self._entries.get(entry_id)

    def get_entries_by_symbol(self, symbol: str) -> List[DailyPoolEntry]:
        """获取某股票的所有条目"""
        return [e for e in self._entries.values() if e.symbol == symbol]

    def get_all_signals(self) -> List[DailySignal]:
        """获取所有历史信号"""
        return self._signals.copy()

    def get_statistics(self) -> Dict[str, Any]:
        """获取池统计信息"""
        active = self.get_active_entries()

        phase_counts = {}
        for entry in active:
            phase = entry.current_phase.name
            phase_counts[phase] = phase_counts.get(phase, 0) + 1

        return {
            'total_entries': len(self._entries),
            'active_entries': len(active),
            'phase_distribution': phase_counts,
            'total_signals': len(self._signals),
            'signal_rate': len(self._signals) / len(self._entries) if self._entries else 0
        }

    def _cleanup_finished_entries(self):
        """清理终态条目 (可选: 移到历史存储)"""
        # 保留所有条目用于分析，不实际删除
        pass

    def iter_entries_by_phase(self, phase: Phase) -> Iterator[DailyPoolEntry]:
        """按阶段迭代条目"""
        for entry in self._entries.values():
            if entry.current_phase == phase:
                yield entry
```

---

## 5. 配置参数体系

### 5.1 配置类定义

```python
from dataclasses import dataclass, field
from typing import Dict

@dataclass
class PhaseConfig:
    """阶段转换配置"""
    # INITIAL -> PULLBACK
    pullback_trigger_atr: float = 0.3

    # PULLBACK -> CONSOLIDATION
    min_convergence_score: float = 0.5
    min_support_tests: int = 2

    # CONSOLIDATION -> REIGNITION
    min_volume_expansion: float = 1.5
    breakout_confirm_days: int = 1

    # 失败条件
    max_drop_from_breakout_atr: float = 1.5
    support_break_buffer_atr: float = 0.5
    max_pullback_days: int = 15
    max_consolidation_days: int = 20
    max_observation_days: int = 30

@dataclass
class PricePatternConfig:
    """价格模式分析配置"""
    # 支撑位检测
    min_touches: int = 2
    touch_tolerance_atr: float = 0.1
    local_min_window: int = 2

    # 企稳区间
    consolidation_window: int = 10
    max_width_atr: float = 2.0

@dataclass
class VolatilityConfig:
    """波动率分析配置"""
    atr_period: int = 14
    lookback_days: int = 20
    contraction_threshold: float = 0.8

@dataclass
class VolumeConfig:
    """成交量分析配置"""
    baseline_period: int = 20
    expansion_threshold: float = 1.5

@dataclass
class SignalConfig:
    """信号生成配置"""
    confidence_weights: Dict[str, float] = field(default_factory=lambda: {
        'convergence': 0.30,
        'support': 0.25,
        'volume': 0.25,
        'quality': 0.20
    })
    position_sizing: Dict[str, float] = field(default_factory=lambda: {
        'strong': 0.15,
        'normal': 0.10,
        'weak': 0.05
    })

@dataclass
class DailyPoolConfig:
    """Daily 池总配置"""
    phase: PhaseConfig = field(default_factory=PhaseConfig)
    price_pattern: PricePatternConfig = field(default_factory=PricePatternConfig)
    volatility: VolatilityConfig = field(default_factory=VolatilityConfig)
    volume: VolumeConfig = field(default_factory=VolumeConfig)
    signal: SignalConfig = field(default_factory=SignalConfig)
```

### 5.2 YAML 配置文件

```yaml
# configs/daily_pool/default.yaml

global:
  max_observation_days: 30
  keep_history: true

phase:
  # INITIAL -> PULLBACK
  pullback_trigger_atr: 0.3

  # PULLBACK -> CONSOLIDATION
  min_convergence_score: 0.5
  min_support_tests: 2

  # CONSOLIDATION -> REIGNITION
  min_volume_expansion: 1.5
  breakout_confirm_days: 1

  # 失败条件
  max_drop_from_breakout_atr: 1.5
  support_break_buffer_atr: 0.5
  max_pullback_days: 15
  max_consolidation_days: 20

price_pattern:
  support_detection:
    min_touches: 2
    touch_tolerance_atr: 0.1
    local_min_window: 2
  consolidation:
    window: 10
    max_width_atr: 2.0

volatility:
  atr_period: 14
  lookback_days: 20
  contraction_threshold: 0.8

volume:
  baseline_period: 20
  expansion_threshold: 1.5

signal:
  confidence_weights:
    convergence: 0.30
    support: 0.25
    volume: 0.25
    quality: 0.20
  position_sizing:
    strong: 0.15
    normal: 0.10
    weak: 0.05
```

### 5.3 策略配置模板

```yaml
# configs/daily_pool/conservative.yaml (保守策略)

phase:
  min_convergence_score: 0.6      # 更严格的企稳要求
  min_volume_expansion: 1.8       # 更强的放量要求
  max_drop_from_breakout_atr: 1.2 # 更严格的止损
  breakout_confirm_days: 2        # 更长的确认期

signal:
  position_sizing:
    strong: 0.12
    normal: 0.08
    weak: 0.04


# configs/daily_pool/aggressive.yaml (激进策略)

phase:
  min_convergence_score: 0.4      # 更宽松的企稳要求
  min_volume_expansion: 1.3       # 较小放量也触发
  max_drop_from_breakout_atr: 2.0 # 更宽容的止损
  breakout_confirm_days: 1        # 快速确认

signal:
  position_sizing:
    strong: 0.20
    normal: 0.15
    weak: 0.08
```

### 5.4 参数调优指南

| 参数 | 默认值 | 调高效果 | 调低效果 |
|------|--------|---------|---------|
| `pullback_trigger_atr` | 0.3 | 需更深回调才识别 | 浅回调也识别 |
| `min_convergence_score` | 0.5 | 企稳判定更严格 | 更快进入CONSOLIDATION |
| `min_support_tests` | 2 | 需更强支撑确认 | 单次触及也算支撑 |
| `min_volume_expansion` | 1.5 | 需更强放量 | 较小放量也触发 |
| `max_drop_from_breakout_atr` | 1.5 | 更宽容失败 | 更严格止损 |
| `max_observation_days` | 30 | 给更长观察期 | 更快过期 |
| `contraction_threshold` | 0.8 | 需更强收敛 | 较弱收敛也算 |

---

## 6. 回测引擎

```python
from datetime import date, timedelta
from typing import List, Dict, Callable, Optional
import pandas as pd

@dataclass
class BacktestResult:
    """回测结果"""
    signals: List[DailySignal]
    statistics: Dict[str, Any]
    phase_transitions: List[Dict]
    daily_snapshots: List[Dict]

class DailyBacktestEngine:
    """
    Daily 池回测引擎

    核心职责:
    - 驱动历史数据回放
    - 管理回测时间线
    - 收集回测指标
    """

    def __init__(self, config: DailyPoolConfig):
        self.config = config
        self.manager = DailyPoolManager(config)

    def run(self,
            breakouts: List['Breakout'],
            price_data: Dict[str, pd.DataFrame],
            start_date: date,
            end_date: date,
            on_signal: Optional[Callable[[DailySignal], None]] = None
    ) -> BacktestResult:
        """
        运行回测

        Args:
            breakouts: 突破列表 (带 date 字段)
            price_data: symbol -> DataFrame 的映射
            start_date: 回测开始日期
            end_date: 回测结束日期
            on_signal: 信号回调 (可选)

        Returns:
            BacktestResult
        """
        all_signals = []
        phase_transitions = []
        daily_snapshots = []

        # 按日期排序突破
        sorted_breakouts = sorted(breakouts, key=lambda b: b.date)
        breakout_idx = 0

        # 按日期迭代
        current_date = start_date
        while current_date <= end_date:
            # 1. 添加当日的新突破
            while (breakout_idx < len(sorted_breakouts) and
                   sorted_breakouts[breakout_idx].date <= current_date):
                bo = sorted_breakouts[breakout_idx]
                self.manager.add_entry(bo, bo.date)
                breakout_idx += 1

            # 2. 更新所有条目
            new_signals = self.manager.update_all(current_date, price_data)

            # 3. 处理信号
            for signal in new_signals:
                all_signals.append(signal)
                if on_signal:
                    on_signal(signal)

            # 4. 记录快照
            daily_snapshots.append({
                'date': current_date,
                'active_entries': len(self.manager.get_active_entries()),
                'new_signals': len(new_signals),
                'phase_dist': self.manager.get_statistics()['phase_distribution']
            })

            # 下一天
            current_date += timedelta(days=1)

        # 收集阶段转换历史
        for entry in self.manager._entries.values():
            for t in entry.phase_history.transitions:
                phase_transitions.append({
                    'symbol': entry.symbol,
                    'date': t.transition_date,
                    'from': t.from_phase.name,
                    'to': t.to_phase.name,
                    'reason': t.reason
                })

        # 计算统计
        statistics = self._calculate_statistics(all_signals, phase_transitions)

        return BacktestResult(
            signals=all_signals,
            statistics=statistics,
            phase_transitions=phase_transitions,
            daily_snapshots=daily_snapshots
        )

    def _calculate_statistics(self, signals: List[DailySignal],
                               transitions: List[Dict]) -> Dict[str, Any]:
        """计算回测统计"""
        total_entries = len(self.manager._entries)

        return {
            'total_entries': total_entries,
            'total_signals': len(signals),
            'signal_rate': len(signals) / total_entries if total_entries > 0 else 0,
            'avg_days_to_signal': (
                sum(s.days_to_signal for s in signals) / len(signals)
                if signals else 0
            ),
            'strength_distribution': {
                'strong': sum(1 for s in signals if s.strength == SignalStrength.STRONG),
                'normal': sum(1 for s in signals if s.strength == SignalStrength.NORMAL),
                'weak': sum(1 for s in signals if s.strength == SignalStrength.WEAK),
            },
            'transition_counts': self._count_transitions(transitions),
        }

    def _count_transitions(self, transitions: List[Dict]) -> Dict[str, int]:
        """统计转换次数"""
        counts = {}
        for t in transitions:
            key = f"{t['from']}->{t['to']}"
            counts[key] = counts.get(key, 0) + 1
        return counts
```

---

## 7. 代码结构

### 7.1 推荐目录结构

```
BreakoutStrategy/
└── daily_pool/                     # Daily 池独立模块
    ├── __init__.py                 # 模块入口, 导出公共 API
    │
    ├── models/                     # 数据模型层
    │   ├── __init__.py
    │   ├── phase.py               # Phase 枚举
    │   ├── entry.py               # DailyPoolEntry
    │   ├── signal.py              # DailySignal, SignalType, SignalStrength
    │   └── history.py             # PhaseHistory, PhaseTransition
    │
    ├── state_machine/             # 状态机层
    │   ├── __init__.py
    │   ├── evidence.py            # AnalysisEvidence
    │   ├── machine.py             # PhaseStateMachine
    │   └── transitions.py         # PhaseTransitionResult
    │
    ├── analyzers/                 # 分析器层
    │   ├── __init__.py
    │   ├── base.py                # 分析器基类
    │   ├── price_pattern.py       # PricePatternAnalyzer
    │   ├── volatility.py          # VolatilityAnalyzer
    │   ├── volume.py              # VolumeAnalyzer
    │   └── results.py             # 分析结果数据类
    │
    ├── evaluator/                 # 评估器层
    │   ├── __init__.py
    │   └── daily_evaluator.py     # DailyPoolEvaluator
    │
    ├── manager/                   # 管理器层
    │   ├── __init__.py
    │   └── pool_manager.py        # DailyPoolManager
    │
    ├── backtest/                  # 回测层
    │   ├── __init__.py
    │   ├── engine.py              # DailyBacktestEngine
    │   └── result.py              # BacktestResult
    │
    └── config/                    # 配置层
        ├── __init__.py
        ├── config.py              # 配置数据类
        └── loader.py              # YAML 配置加载器
```

### 7.2 模块依赖关系

```
                    ┌──────────────┐
                    │   backtest   │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │   manager    │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │  evaluator   │
                    └──────┬───────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
  ┌──────▼──────┐  ┌───────▼───────┐  ┌──────▼──────┐
  │  analyzers  │  │ state_machine │  │   config    │
  └──────┬──────┘  └───────┬───────┘  └─────────────┘
         │                 │
         └────────┬────────┘
                  │
           ┌──────▼──────┐
           │   models    │
           └─────────────┘
```

---

## 8. 开发路线图

### 8.1 分阶段实施计划

| 阶段 | 工时 | 交付物 | 依赖 |
|------|------|--------|------|
| **Phase 1**: 数据模型 + 配置 | 1天 | `models/`, `config/` | 无 |
| **Phase 2**: 状态机 | 1天 | `state_machine/` | Phase 1 |
| **Phase 3**: 三个分析器 | 1.5天 | `analyzers/` | Phase 1 |
| **Phase 4**: 评估器 | 0.5天 | `evaluator/` | Phase 2, 3 |
| **Phase 5**: 池管理器 | 0.5天 | `manager/` | Phase 4 |
| **Phase 6**: 回测引擎 | 1天 | `backtest/` | Phase 5 |
| **Phase 7**: 集成测试 + 调参 | 0.5天 | 测试用例 | Phase 6 |
| **总计** | **6天** | 完整 Daily 池系统 | |

### 8.2 里程碑定义

| 里程碑 | 完成标准 |
|--------|---------|
| M1: 核心框架 | 数据模型和状态机可独立运行 |
| M2: 分析能力 | 三个分析器可处理真实数据 |
| M3: 评估闭环 | 从数据到信号的完整流程 |
| M4: 回测验证 | 通过历史数据回测验证 |

---

## 9. 与现有架构的对比

### 9.1 关键设计决策

| 决策 | 现有 Realtime 架构 | 本设计 (独立 Daily) | 理由 |
|------|-------------------|---------------------|------|
| 评估模型 | 加权评分 | 阶段状态机 | 过程导向 vs 状态导向 |
| 数据输入 | 单条 K 线 | 历史序列 DataFrame | Daily 需要看趋势 |
| 核心维度 | TimeWindow, Price, Volume, Risk | 价格模式, 波动收敛, 放量启动 | 业务语义不同 |
| 输出类型 | 分数 (0-100) | 阶段 + 信号 | 可解释性 |
| 状态管理 | 简单三态 | 完整阶段机 + 历史 | 过程追溯 |

### 9.2 不复用的理由

| 现有组件 | 不复用原因 |
|---------|-----------|
| `CompositeBuyEvaluator` | 加权模型不适合过程评估 |
| `TimeWindowEvaluator` | Daily 无时间窗口概念 |
| `VolumeVerifyEvaluator` | 5分钟粒度不适用 |
| `PriceConfirmEvaluator` | 点比较 vs 模式识别 |
| `PoolManager.evaluate_entries()` | 驱动逻辑完全不同 |

### 9.3 潜在复用项 (如果未来需要集成)

| 现有组件 | 复用可能性 | 说明 |
|---------|-----------|------|
| `ITimeProvider` | 高 | 时间抽象通用 |
| `IPoolStorage` | 中 | 存储接口可适配 |
| `EvaluationResult` | 低 | 输出结构不同 |
| `BuySignal` | 中 | 可扩展支持 DailySignal |
| `BacktestEngine` | 低 | 驱动逻辑完全不同 |

---

## 10. 结论

### 10.1 核心设计理念

本架构的核心理念是 **"过程优于状态"**：

1. **阶段状态机** 替代 加权评分，准确建模 "回调-企稳-再启动" 过程
2. **证据聚合模式**：三个分析器独立分析，状态机综合判断
3. **完整历史追踪**：每次转换都有记录，信号可解释
4. **ATR 标准化**：所有阈值以 ATR 为单位，自动适应不同股票

### 10.2 与方案 C 的对比

| 维度 | 方案 B (本设计) | 方案 C (重构评估器) |
|------|----------------|-------------------|
| 开发周期 | 6 天 | 4 天 |
| 代码复用 | 0% | ~60% |
| 架构纯净度 | 100% | 90% |
| 维护复杂度 | 较高 (两套架构) | 较低 (共享基础) |
| 适用场景 | 完全独立开发 | 增量演进 |

### 10.3 建议

如果目标是 **探索理想架构**，本设计提供了完整蓝图。

如果目标是 **快速实现盈利**，建议采用方案 C，复用已验证的基础设施，同时获得本设计的核心创新（阶段状态机）。

---

*文档完成于 2026-01-04*
