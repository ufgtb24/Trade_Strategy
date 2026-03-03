"""
联合信号强度计算与序列标签生成

纯函数模块，无状态、无配置依赖。
用信号内在属性（pk_num, tr_num）计算加权强度，
生成可读的信号序列标签。
"""

from datetime import date
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .models import AbsoluteSignal, SignalType


def calculate_signal_strength(signal: AbsoluteSignal) -> float:
    """
    用信号已有的内在属性计算强度。

    B → pk_num（穿越几层阻力就是几）
    D → tr_num（几次底部确认就是几）
    V → 1.0
    Y → 1.0

    Args:
        signal: 绝对信号

    Returns:
        信号强度值
    """
    if signal.signal_type == SignalType.BREAKOUT:
        return float(signal.details.get("pk_num", 1))
    elif signal.signal_type == SignalType.DOUBLE_TROUGH:
        return float(signal.details.get("tr_num", 1))
    else:
        return 1.0


def generate_sequence_label(signals: List[AbsoluteSignal]) -> str:
    """
    按时间升序生成可读的信号序列标签。
    例: "D(2) → B(3) → V → Y"

    规则:
    - B: pk_num > 1 时显示 B(N)，否则显示 B
    - D: tr_num > 1 时显示 D(N)，否则显示 D
    - V, Y: 直接显示字母
    - 按日期升序排列，用 " → " 连接

    Args:
        signals: 信号列表

    Returns:
        信号序列标签字符串
    """
    sorted_signals = sorted(signals, key=lambda s: s.date)

    parts = []
    for s in sorted_signals:
        label = s.signal_type.value
        if s.signal_type == SignalType.BREAKOUT:
            pk_num = s.details.get("pk_num", 1)
            if pk_num > 1:
                label = f"B({pk_num})"
        elif s.signal_type == SignalType.DOUBLE_TROUGH:
            tr_num = s.details.get("tr_num", 1)
            if tr_num > 1:
                label = f"D({tr_num})"
        parts.append(label)

    return " → ".join(parts)


# ========== 异常走势检测 ==========

# lookback 窗口内价格振幅阈值，超过此值标记为 turbulent
AMPLITUDE_THRESHOLD = 0.8


def calculate_amplitude(df_slice: pd.DataFrame, lookback_days: int) -> float:
    """
    计算 lookback 窗口内的最大方向性上涨幅度（max_runup）。

    从窗口内任意累计最低点到其后续高点的最大涨幅。
    仅捕获方向性上冲，不计入来回震荡产生的范围。

    算法:
        cum_min = cumulative minimum of lows
        runup_i = (high_i - cum_min_i) / cum_min_i
        max_runup = max(runup_i)

    函数名保持 calculate_amplitude 以兼容现有调用方。

    Args:
        df_slice: 价格数据（需包含 High/Low 列）
        lookback_days: 回看交易日数

    Returns:
        最大方向性涨幅（0.0 表示无上涨或数据无效，1.0 表示 100%）
    """
    window = df_slice.iloc[-lookback_days:] if len(df_slice) > lookback_days else df_slice

    # 兼容大小写列名
    high_col = "High" if "High" in window.columns else "high"
    low_col = "Low" if "Low" in window.columns else "low"

    highs = window[high_col].values.astype(float)
    lows = window[low_col].values.astype(float)

    # NaN 安全：用 inf/-inf 替换缺失值，避免 np.minimum.accumulate 传播 NaN
    lows_clean = np.where(np.isnan(lows), np.inf, lows)
    highs_clean = np.where(np.isnan(highs), -np.inf, highs)

    cum_min = np.minimum.accumulate(lows_clean)

    # 避免除零：将 <= 0 或 inf 的累计最低值替换为 nan
    cum_min_safe = np.where((cum_min <= 0) | np.isinf(cum_min), np.nan, cum_min)
    runups = (highs_clean - cum_min_safe) / cum_min_safe

    if len(runups) == 0 or np.all(np.isnan(runups)):
        return 0.0

    return float(np.nanmax(runups))


def is_turbulent(amplitude: float, threshold: float = AMPLITUDE_THRESHOLD) -> bool:
    """
    判断股票是否处于异常走势。

    Args:
        amplitude: 价格振幅
        threshold: 判定阈值（默认 0.8 即 80%）

    Returns:
        True 表示异常走势
    """
    return amplitude >= threshold


def _get_freshness(signal: AbsoluteSignal) -> float:
    """
    从信号中提取 freshness 值，兼容 dict 和旧 float 格式。

    Args:
        signal: 绝对信号

    Returns:
        freshness 值，默认 1.0
    """
    f = signal.details.get("freshness", 1.0)
    if isinstance(f, dict):
        return f.get("value", 1.0)
    return f


def calc_effective_weighted_sum(
    signals: List[AbsoluteSignal],
    turbulent: bool,
) -> float:
    """
    计算有效加权强度总和。

    turbulent 时仅计入 D（双底）信号的强度，
    其余信号（B/V/Y）不计入排序权重。

    每个信号的 strength 会乘以 freshness（如果存在），
    默认 freshness=1.0 以保持向后兼容。
    支持 freshness 为 float 或 dict（取 "value" 键）。

    Args:
        signals: 信号列表（strength 已计算）
        turbulent: 是否为异常走势股票

    Returns:
        有效加权强度总和
    """
    if not turbulent:
        return sum(
            s.strength * _get_freshness(s) for s in signals
        )

    # turbulent：仅 D 信号计入
    return sum(
        s.strength * _get_freshness(s) for s in signals
        if s.signal_type == SignalType.DOUBLE_TROUGH
    )


# ========== 信号鲜度计算 ==========

# PRTR 衰减曲线指数
FRESHNESS_ALPHA = 1.5
# 时间衰减半衰期（交易日）
FRESHNESS_HALF_LIFE = 30
# 最小有效涨幅比例（低于此值视为噪音）
MIN_RISE_PCT = 0.05


def calculate_signal_freshness(
    signal: AbsoluteSignal,
    df_slice: pd.DataFrame,
    current_price: float,
    scan_date: date,  # 保留用于 API 一致性，实际时间衰减通过 df_slice 索引计算
    alpha: float = FRESHNESS_ALPHA,
    half_life: int = FRESHNESS_HALF_LIFE,
) -> dict:
    """
    计算信号鲜度因子 [0.0, 1.0]，返回分解值。

    鲜度 = price_decay × time_decay
    - price_decay: 信号"能量"被后续价格运动消耗的程度
      - B/V/Y（动量信号）：使用 Price Round-Trip Ratio (PRTR)
      - D（支撑信号）：基于价格与支撑位的距离
    - time_decay: 基于信号到扫描日的交易日数的指数衰减

    Args:
        signal: 绝对信号
        df_slice: 信号所在的价格数据切片
        current_price: 当前价格（扫描日收盘价）
        scan_date: 扫描截止日期
        alpha: PRTR 衰减曲线指数（默认 1.5）
        half_life: 时间衰减半衰期，交易日数（默认 30）

    Returns:
        dict with keys: value (float), price_decay (float), time_decay (float)
    """
    # 价格衰减
    if signal.signal_type == SignalType.DOUBLE_TROUGH:
        price_decay = _calc_price_decay_support(signal, current_price)
    else:
        price_decay = _calc_price_decay_momentum(
            signal, df_slice, current_price, alpha
        )

    # 时间衰减：用交易日索引差计算
    signal_idx = df_slice.index.get_indexer(
        pd.DatetimeIndex([pd.Timestamp(signal.date)]), method="nearest"
    )[0]
    scan_idx = len(df_slice) - 1  # 最后一根 bar 即扫描日
    days_elapsed = max(scan_idx - signal_idx, 0)
    time_decay = 0.5 ** (days_elapsed / half_life)

    return {
        "value": round(price_decay * time_decay, 3),
        "price_decay": round(price_decay, 3),
        "time_decay": round(time_decay, 3),
    }


def _calc_price_decay_momentum(
    signal: AbsoluteSignal,
    df_slice: pd.DataFrame,
    current_price: float,
    alpha: float = FRESHNESS_ALPHA,
) -> float:
    """
    动量信号（B/V/Y）的价格衰减因子。

    使用 Price Round-Trip Ratio (PRTR):
        rise = peak_after - signal_price
        giveback = peak_after - current_price
        prtr = giveback / rise  (clamp to [0, 1])
        decay = 1 - prtr^alpha

    关键行为:
        30% 回撤 → 衰减仅 16%
        50% 回撤 → 衰减 35%
        80% 回撤 → 衰减 72%
        100% 回撤 → 完全衰减

    若信号后涨幅过小（< MIN_RISE_PCT），使用简单跌幅比率回退。

    Args:
        signal: 动量信号（B/V/Y）
        df_slice: 价格数据切片
        current_price: 当前价格
        alpha: PRTR 衰减曲线指数

    Returns:
        价格衰减因子 [0.0, 1.0]
    """
    signal_date = signal.date
    # 获取信号日期及之后的数据
    after_mask = df_slice.index.date >= signal_date
    after_slice = df_slice.loc[after_mask]

    if after_slice.empty:
        return 1.0

    high_col = "High" if "High" in after_slice.columns else "high"
    peak_after = after_slice[high_col].max()

    rise = peak_after - signal.price
    if rise <= signal.price * MIN_RISE_PCT:
        # 涨幅过小，不具备 PRTR 计算意义
        if current_price < signal.price:
            drop_ratio = (signal.price - current_price) / signal.price
            return max(0.0, 1.0 - drop_ratio)
        return 1.0  # 接近信号价，保持新鲜

    giveback = peak_after - current_price
    prtr = min(max(giveback / rise, 0.0), 1.0)
    return 1.0 - prtr ** alpha


def _calc_price_decay_support(
    signal: AbsoluteSignal,
    current_price: float,
) -> float:
    """
    支撑信号（D）的价格衰减因子。

    基于当前价格与支撑价的比率：
        0.9 <= ratio <= 1.2 → 在支撑区间内，完全新鲜
        ratio < 0.9 → 支撑失效，快速衰减
        ratio > 1.2 → 远离支撑，缓慢衰减

    Args:
        signal: 支撑信号（D）
        current_price: 当前价格

    Returns:
        价格衰减因子 [0.0, 1.0]（signal.price <= 0 时返回 0.0）
    """
    if signal.price <= 0:
        return 0.0

    price_ratio = current_price / signal.price

    if 0.9 <= price_ratio <= 1.2:
        return 1.0  # 在支撑区间内
    elif price_ratio < 0.9:
        # 支撑失效
        return max(0.1, 1.0 - (0.9 - price_ratio) / 0.2)
    else:
        # 远离支撑
        return max(0.3, 1.0 - (price_ratio - 1.2) / 0.5)
