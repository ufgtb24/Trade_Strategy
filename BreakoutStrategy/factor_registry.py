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

    # --- UI 文档 ---
    description: str = ''  # 多段中文：算法 + 意义；空 → UI 不弹 tooltip

    # --- 计算参数（sub_params）---
    sub_params: tuple = ()  # tuple[SubParamDef, ...]

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
               unit='d', display_transform='identity',
               description=(
                   '算法：max(idx - p.index for p in broken_peaks)。\n\n'
                   'source: BreakoutStrategy/analysis/features.py:710\n\n'
                   '意义：取本次突破吃掉的所有峰值中最老那一个距今的交易日数。'
                   '位龄越长，阻力被压制时间越久，含金量越高。'
               )),
    FactorInfo('test', 'Test Count', '测试次数',
               (2, 3, 4), (1.1, 1.25, 1.4),
               is_discrete=True, category='resistance',
               unit='x', display_transform='identity',
               description=(
                   '算法：对 broken_peaks 按价格排序，相邻差 ≤ cluster_density_threshold '
                   '归同一簇，取最大簇大小。\n\n'
                   'source: BreakoutStrategy/analysis/features.py:749\n\n'
                   '意义：同价区被测试次数越多，阻力越经充分验证，突破后获买方共识越强。'
               )),
    FactorInfo('height', 'Height', '峰值高度',
               (0.2, 0.4, 0.7), (1.3, 1.6, 2.0),
               category='resistance',
               unit='%', display_transform='pct100',
               description=(
                   '算法：max(p.relative_height for p in broken_peaks)。\n\n'
                   'source: BreakoutStrategy/analysis/features.py:724\n\n'
                   '意义：峰值相对高度越大，被突破的阻力幅度越显著，'
                   '说明该价位曾吸引大量抛压，突破后空间更充分。'
               )),
    FactorInfo('peak_vol', 'Peak Volume', '峰值量能',
               (3.0, 5.0), (1.1, 1.2),
               mining_mode='gte', category='resistance',
               unit='x', display_transform='identity',
               description=(
                   '算法：max(p.volume_peak for p in broken_peaks)。\n\n'
                   'source: BreakoutStrategy/analysis/features.py:737\n\n'
                   '意义：峰值形成时的最大放量倍数越高，该阻力位成交越密集，'
                   '突破此阻力代表消化了更大的套牢盘，信号更可靠。'
               )),

    # === 突破行为 Factor ===
    FactorInfo('volume', 'Volume Surge', '突破量能',
               (5.0, 10.0), (1.5, 2.0),
               category='breakout',
               unit='x', display_transform='identity',
               nullable=True,
               description=(
                   '算法：突破日成交量 / 过去 63 日均量。\n\n'
                   'source: BreakoutStrategy/analysis/features.py:332\n\n'
                   '意义：放量倍数越高，突破时买方资金越充裕，有效突破的概率越大；'
                   '缩量突破往往为假突破。'
               )),
    FactorInfo('overshoot', 'Overshoot', '超涨比',
               (4.0, 5.0), (0.80, 0.60),
               mining_mode='lte', category='breakout',
               unit='σ', display_transform='round1', zero_guard=True,
               sub_params=(
                   SubParamDef('gain_window', 'gain_window', int, 5,
                               (1, 30), 'Gain measurement window'),
               ),
               nullable=True,
               description=(
                   '算法：突破后 gain_window 日涨幅 / (年化波动率 / sqrt(50.4))，σ 单位。\n\n'
                   'source: BreakoutStrategy/analysis/features.py:623\n\n'
                   '意义：值越大说明突破后短期涨幅相对自身波动率越极端，'
                   '过高往往意味着透支行情、回调风险增加，故本因子取 lte（越低越好）。'
               )),
    FactorInfo('day_str', 'Breakout Day Strength', '突破日强度',
               (1.5, 2.5), (1.2, 1.35),
               category='breakout',
               unit='σ', display_transform='round1', zero_guard=True,
               nullable=True,
               description=(
                   '算法：max(日内涨幅, 跳空幅度) / 日波动率（年化波动率 / sqrt(252)），σ 单位。\n\n'
                   'source: BreakoutStrategy/analysis/features.py:594\n\n'
                   '意义：突破日相对自身波动率越强烈，买方动能越集中，'
                   '形成强力突破信号；值小则可能是温吞突破。'
               )),
    FactorInfo('pbm', 'Pre-Breakout Momentum', '突破前动量',
               (0.7, 1.45), (1.15, 1.3),
               category='breakout',
               unit='σN', display_transform='round2',
               sub_params=(
                   SubParamDef('lookback', 'continuity_lookback', int, 5,
                               (1, 9999), 'Lookback period for momentum calculation'),
               ),
               nullable=True,
               description=(
                   '算法：(ΔP/P₀) × |ΔP|/L / N，再 × sqrt(n_bars)/日波动率，'
                   '波动率标准化为 σN 单位。\n\n'
                   'source: BreakoutStrategy/analysis/features.py:648\n\n'
                   '意义：突破前价格走势越连贯高效（净位移大、路径短），'
                   '说明买方积累充分，突破更具惯性。'
               )),
    FactorInfo('streak', 'Streak', '连续突破',
               (2, 4), (0.9, 0.75),
               is_discrete=True, mining_mode='lte', category='breakout',
               unit='bo', display_transform='identity',
               sub_params=(
                   SubParamDef('window', 'streak_window', int, 20,
                               (1, 9999), 'Window for streak counting',
                               consumer='detector'),
               ),
               description=(
                   '算法：统计 streak_window 内（含当次）历史突破次数。\n\n'
                   'source: BreakoutStrategy/analysis/breakout_detector.py:616\n\n'
                   '意义：短期内频繁突破（高 streak）往往意味着连续追高，'
                   '胜率下降；首次或低频突破（低 streak）信号更纯粹，故取 lte。'
               )),
    FactorInfo('drought', 'Drought', '突破干旱期',
               (60, 80, 120), (1.25, 1.1, 1.05),
               has_nan_group=True, category='breakout',
               unit='d', display_transform='identity', nullable=True,
               description=(
                   '算法：当前突破索引 - 上一次突破索引，首次突破返回 None。\n\n'
                   'source: BreakoutStrategy/analysis/features.py:694\n\n'
                   '意义：距上次突破间隔越长，积累的买方能量越充足，'
                   '突破后持续性更强；None 组（首次突破）单独建模。'
               )),
    FactorInfo('pk_mom', 'Peak Momentum', '峰值动量',
               (1.2, 1.5), (1.2, 1.5),
               has_nan_group=True, category='breakout', mining_mode='gte',
               unit='', display_transform='round2',
               sub_params=(
                   SubParamDef('lookback', 'pk_lookback', int, 30,
                               (1, 9999), 'Time window for recent peak detection'),
               ),
               nullable=True,
               description=(
                   '算法：1 + log(1 + D_atr)，D_atr = (peak_price - trough_price) / ATR_peak；'
                   '无近期 peak 时返回 0。\n\n'
                   'source: BreakoutStrategy/analysis/features.py:471\n\n'
                   '意义：突破前 peak 至今的回调幅度（ATR 标准化）越深，'
                   '"深蹲起跳"形态越强，突破动能越充沛。'
               )),
    FactorInfo('pre_vol', 'Pre-Breakout Volume', '突破前放量',
               (3.0, 5.0), (1.15, 1.25),
               category='context', mining_mode='gte',
               unit='x', display_transform='round2',
               sub_params=(
                   SubParamDef('window', 'pre_vol_window', int, 10,
                               (1, 60), 'Pre-breakout volume lookback window'),
               ),
               nullable=True,
               description=(
                   '算法：突破前 pre_vol_window 天内逐日放量倍数（vs 63 日基线）的最大值。\n\n'
                   'source: BreakoutStrategy/analysis/features.py:912\n\n'
                   '意义：突破前窗口内出现过显著放量，说明有资金提前布局，'
                   '突破后持续上涨概率更高。'
               )),
    FactorInfo('ma_pos', 'MA Position', '均线位置',
               (0.05, 0.10, 0.20), (1.1, 1.2, 1.35),
               category='context',
               unit='%', display_transform='pct100', zero_guard=True,
               sub_params=(
                   SubParamDef('period', 'ma_pos_period', int, 20,
                               (10, 50), 'MA period for position calculation'),
               ),
               nullable=True,
               description=(
                   '算法：close / MA_N - 1.0，MA_N 为 N 日均线，优先用预计算列。\n\n'
                   'source: BreakoutStrategy/analysis/features.py:773\n\n'
                   '意义：突破时股价在均线上方越多，说明中期趋势越强健，'
                   '动量积累充分，突破后上行空间更大。'
               )),
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
               nullable=True,
               description=(
                   '算法：drawdown × recovery × (1 - recovery)^(decay_power-1)，'
                   'recovery = (close - trough) / (peak - trough)，峰值在 r* = 1/decay_power 处。\n\n'
                   'source: BreakoutStrategy/analysis/features.py:802\n\n'
                   '意义：在回撤幅度大、且早期恢复（未追高）时得分最高，'
                   '筛选底部反弹而非顶部强势的突破形态。'
               )),  # INACTIVE 当前
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
               nullable=True,
               description=(
                   '算法：d2 = (MA[t] - 2×MA[t-k] + MA[t-2k]) / k²，'
                   '归一化为 d2 / MA[t] × period²；正值表示均线加速上行或减速下行。\n\n'
                   'source: BreakoutStrategy/analysis/features.py:849\n\n'
                   '意义：MA 曲率正值越大，趋势加速越明显，'
                   '均线由跌转涨的拐点是底部反转的领先信号。'
               )),  # INACTIVE 当前
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
_BY_YAML_KEY: dict[str, FactorInfo] = {f.yaml_key: f for f in FACTOR_REGISTRY}

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


def find_factor(key: str | None) -> FactorInfo | None:
    """按 key 查找因子（不抛异常）。

    与 get_factor() 不同：未注册的 key 返回 None，None 输入也返回 None。
    供 UI 等"key 可能不属于因子"的场景使用。
    """
    if key is None:
        return None
    return _BY_KEY.get(key)


def find_factor_by_yaml_key(yaml_key: str | None) -> FactorInfo | None:
    """按 yaml_key（形如 'peak_vol_factor'）查找因子。

    未注册或 None 输入返回 None；不抛异常。供 UI 等需要按
    yaml 键查询的场景使用，避免在调用侧重新拼接 _factor 后缀。
    """
    if yaml_key is None:
        return None
    return _BY_YAML_KEY.get(yaml_key)


