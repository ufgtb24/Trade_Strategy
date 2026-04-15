"""
统一因子注册表

每个因子只有三个显式名称：
- key: 缩写/程序标识（如 "age", "pk_mom"）
- name: 英文全称（如 "Age", "Peak Momentum"）
- cn_name: 中文名（如 "突破位龄", "峰值动量"）

其他名称由 key 自动派生：
- level_col = f"{key}_level"（DataFrame 等级列）
- yaml_key = f"{key}_factor"（YAML 配置键）
- display_label = f"{key}({name}:{cn_name})"（Parameter Editor 显示）
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SubParamDef:
    """因子的计算参数定义（影响 FeatureCalculator 或 Detector 的参数）"""
    yaml_name: str
    internal_name: str
    param_type: type
    default: int | float
    range: tuple = (1, 9999)
    description: str = ''
    consumer: str = 'feature_calculator'  # 'feature_calculator' | 'detector'


@dataclass(frozen=True)
class FactorInfo:
    """单个因子的完整元数据"""
    key: str
    name: str
    cn_name: str
    default_thresholds: tuple
    default_values: tuple
    is_discrete: bool = False
    has_nan_group: bool = False
    mining_mode: str | None = None  # None=Spearman自动推断, 'gte'/'lte'=强制覆盖
    category: str = 'breakout'     # 'resistance' | 'breakout' | 'context'

    # --- Scorer 动态化所需 ---
    unit: str = 'x'
    display_transform: str = 'identity'  # 'identity' | 'pct100' | 'round1' | 'round2'
    zero_guard: bool = False
    nullable: bool = False

    # --- 计算参数（sub_params）---
    sub_params: tuple = ()  # tuple[SubParamDef, ...]

    # --- BO 级 buffer（trading days）---
    # 该因子在 idx 处计算所需的最少历史 bar 数。BreakoutDetector 用
    # max(active 因子的 buffer) 作为 BO 产生的硬下限：BO 的 idx < max_buffer
    # 时直接 skip，保证下游所有 _calculate_xxx 永远在 lookback 充足时调用。
    #
    # 取值规则：
    # - 无历史 lookback 概念的因子（peak 属性 / detector 状态）：保持 0
    # - 单一窗口因子：填该窗口长度（如 volume=63）
    # - 组合窗口因子：填各部分之和（如 pk_mom = pk_lookback(30) + atr_period(14) = 44）
    # - 间接依赖型因子（如 day_str/overshoot/pbm 依赖 annual_volatility）：
    #   填被依赖量的 buffer（这里都是 252）
    #
    # 注意：buffer 假设 sub_params 取默认值；如果 sub_params 改大，需同步调高 buffer，
    # 否则上游 gate 不充分，下游 _calculate_xxx 会触发"严格 lookback"的 raise。
    buffer: int = 0

    @property
    def level_col(self) -> str:
        return f"{self.key}_level"

    @property
    def yaml_key(self) -> str:
        return f"{self.key}_factor"

    @property
    def display_label(self) -> str:
        return f"{self.key}({self.name}:{self.cn_name})"


FACTOR_REGISTRY: list[FactorInfo] = [
    # === 阻力属性 Factor ===
    FactorInfo('age', 'Age', '突破位龄',
               (42, 63, 252), (1.02, 1.03, 1.05),
               is_discrete=True, category='resistance',
               unit='d', display_transform='identity'),
    FactorInfo('test', 'Test Count', '测试次数',
               (2, 3, 4), (1.1, 1.25, 1.4),
               is_discrete=True, category='resistance',
               unit='x', display_transform='identity'),
    FactorInfo('height', 'Height', '峰值高度',
               (0.2, 0.4, 0.7), (1.3, 1.6, 2.0),
               category='resistance',
               unit='%', display_transform='pct100'),
    FactorInfo('peak_vol', 'Peak Volume', '峰值量能',
               (3.0, 5.0), (1.1, 1.2),
               mining_mode='gte', category='resistance',
               unit='x', display_transform='identity'),

    # === 突破行为 Factor ===
    FactorInfo('volume', 'Volume Surge', '突破量能',
               (5.0, 10.0), (1.5, 2.0),
               category='breakout',
               unit='x', display_transform='identity',
               buffer=63),  # VOLUME_LOOKBACK in features._calculate_volume_ratio
    FactorInfo('overshoot', 'Overshoot', '超涨比',
               (4.0, 5.0), (0.80, 0.60),
               mining_mode='lte', category='breakout',
               unit='σ', display_transform='round1', zero_guard=True,
               sub_params=(
                   SubParamDef('gain_window', 'gain_window', int, 5,
                               (1, 30), 'Gain measurement window'),
               ),
               buffer=252),  # 依赖 annual_volatility (252 day window)
    FactorInfo('day_str', 'Breakout Day Strength', '突破日强度',
               (1.5, 2.5), (1.2, 1.35),
               category='breakout',
               unit='σ', display_transform='round1', zero_guard=True,
               buffer=252),  # 依赖 annual_volatility (252 day window)
    FactorInfo('pbm', 'Pre-Breakout Momentum', '突破前动量',
               (0.7, 1.45), (1.15, 1.3),
               category='breakout',
               unit='σN', display_transform='round2',
               sub_params=(
                   SubParamDef('lookback', 'continuity_lookback', int, 5,
                               (1, 9999), 'Lookback period for momentum calculation'),
               ),
               buffer=252),  # 依赖 annual_volatility (252 day window)
    FactorInfo('streak', 'Streak', '连续突破',
               (2, 4), (0.9, 0.75),
               is_discrete=True, mining_mode='lte', category='breakout',
               unit='bo', display_transform='identity',
               sub_params=(
                   SubParamDef('window', 'streak_window', int, 20,
                               (1, 9999), 'Window for streak counting',
                               consumer='detector'),
               )),
    FactorInfo('drought', 'Drought', '突破干旱期',
               (60, 80, 120), (1.25, 1.1, 1.05),
               has_nan_group=True, category='breakout',
               unit='d', display_transform='identity', nullable=True),
    FactorInfo('pk_mom', 'Peak Momentum', '峰值动量',
               (1.2, 1.5), (1.2, 1.5),
               has_nan_group=True, category='breakout', mining_mode='gte',
               unit='', display_transform='round2',
               sub_params=(
                   SubParamDef('lookback', 'pk_lookback', int, 30,
                               (1, 9999), 'Time window for recent peak detection'),
               ),
               buffer=44),  # pk_lookback(30) + atr_period(14)
    FactorInfo('pre_vol', 'Pre-Breakout Volume', '突破前放量',
               (3.0, 5.0), (1.15, 1.25),
               category='context', mining_mode='gte',
               unit='x', display_transform='round2',
               sub_params=(
                   SubParamDef('window', 'pre_vol_window', int, 10,
                               (1, 60), 'Pre-breakout volume lookback window'),
               ),
               buffer=73),  # vol_ratio rolling(63) + pre_vol_window(10)
    FactorInfo('ma_pos', 'MA Position', '均线位置',
               (0.05, 0.10, 0.20), (1.1, 1.2, 1.35),
               category='context',
               unit='%', display_transform='pct100', zero_guard=True,
               sub_params=(
                   SubParamDef('period', 'ma_pos_period', int, 20,
                               (10, 50), 'MA period for position calculation'),
               ),
               buffer=20),  # ma_pos_period
    FactorInfo('dd_recov', 'Drawdown Recovery', '回撤恢复度',
               (0.02, 0.04, 0.06), (1.15, 1.25, 1.40),
               category='context',
               unit='', display_transform='round2', zero_guard=True,
               mining_mode='gte',
               sub_params=(
                   SubParamDef('lookback', 'dd_recov_lookback', int, 252,
                               (60, 504), 'Lookback window for peak detection'),
                   SubParamDef('best_recovery', 'dd_recov_best_recovery', float, 0.25,
                               (0.10, 0.50), 'Recovery ratio at which factor peaks (lower=more conservative)'),
               ),
               buffer=252),  # dd_recov_lookback default; INACTIVE 当前
    FactorInfo('ma_curve', 'MA Curvature', 'MA曲率',
               (0.05, 0.15, 0.30), (1.15, 1.25, 1.40),
               category='context',
               unit='', display_transform='round2', zero_guard=True,
               mining_mode='gte',
               sub_params=(
                   SubParamDef('period', 'ma_curve_period', int, 50,
                               (20, 100), 'MA period for curvature calculation'),
                   SubParamDef('stride', 'ma_curve_stride', int, 5,
                               (2, 10), 'Stride for wide-interval curvature calculation (days)'),
               ),
               buffer=50),  # ma_curve_period default; INACTIVE 当前
]

# --- 总开关：在此集合中的因子 key 将在所有模块中不可见 ---
# 与 YAML 中的 enabled（评分开关）不同，这里控制因子是否参与系统的所有环节
# 使用场景：触发率100%的无效因子、数据质量不足待优化的因子
# INACTIVE_FACTORS: set[str] = {}
INACTIVE_FACTORS: set[str] = {'ma_curve', 'dd_recov'}
# 使用方式：将无效因子的 key 加入集合，如 {'age', 'streak'}
# 示例：
# INACTIVE_FACTORS = {'age'}  # 触发率100%，无区分力

LABEL_COL = 'label'

# --- 索引（保留全量，服务于精确查询） ---
_BY_KEY: dict[str, FactorInfo] = {f.key: f for f in FACTOR_REGISTRY}
_BY_LEVEL_COL: dict[str, FactorInfo] = {f.level_col: f for f in FACTOR_REGISTRY}

# --- 活跃因子缓存（模块加载时计算一次） ---
_ACTIVE_FACTORS: list[FactorInfo] = [
    f for f in FACTOR_REGISTRY if f.key not in INACTIVE_FACTORS
]


def get_factor(key: str) -> FactorInfo:
    """按 key 获取因子信息（全量，不受总开关影响）"""
    return _BY_KEY[key]


def get_factor_by_level_col(level_col: str) -> FactorInfo:
    """按 level_col 获取因子信息（全量，不受总开关影响）"""
    return _BY_LEVEL_COL[level_col]


def get_active_factors() -> list[FactorInfo]:
    """返回所有活跃因子列表（已排除 INACTIVE_FACTORS）"""
    return list(_ACTIVE_FACTORS)


def get_level_cols() -> list[str]:
    """所有活跃因子的 level_col 列表"""
    return [f.level_col for f in _ACTIVE_FACTORS]


def get_factor_display() -> dict[str, str]:
    """{level_col: key}（仅活跃因子）"""
    return {f.level_col: f.key for f in _ACTIVE_FACTORS}


def get_max_buffer() -> int:
    """所有活跃因子的最大 buffer 长度（trading days）。

    每个因子的 buffer 在 FactorInfo.buffer 字段里声明（单一来源，加新因子时
    在 FACTOR_REGISTRY 那行就需要填）。BreakoutDetector 用此值作为 BO 产生
    的硬下限：BO 的 idx 必须 >= 此值，否则直接不产生该 BO。这样下游 features
    计算永远不会落在 lookback 不足的位置，得以采用严格契约（不需要自适应降级）。

    若所有需要 lookback 的因子都被加入 INACTIVE_FACTORS，返回 0（无 gate）。

    设计参考：docs/research/bo-level-buffer-redesign.md
    """
    return max((f.buffer for f in _ACTIVE_FACTORS), default=0)
