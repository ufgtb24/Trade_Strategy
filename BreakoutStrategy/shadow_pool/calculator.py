"""
Shadow Pool 计算器

纯函数实现，从 Breakout 和价格数据直接计算 MFE/MAE 指标。
无状态管理，支持并行计算。
"""

from datetime import date
from typing import Optional

import numpy as np
import pandas as pd

from BreakoutStrategy.analysis import Breakout
from .models import ShadowResult


def compute_shadow_result(bo: Breakout,
                          df: pd.DataFrame,
                          tracking_days: int = 30) -> Optional[ShadowResult]:
    """
    纯函数：从突破点计算后续表现指标

    Args:
        bo: 突破对象
        df: 该股票的完整价格 DataFrame（需包含 high, low, close 列）
        tracking_days: 跟踪天数

    Returns:
        ShadowResult，如果数据不足则返回 None
    """
    # 截取突破日之后的数据（T+1 开始跟踪）
    future_mask = df.index > pd.Timestamp(bo.date)
    future_df = df[future_mask].head(tracking_days)

    if len(future_df) == 0:
        return None

    # 提取价格序列
    highs = future_df['high'].values
    lows = future_df['low'].values
    closes = future_df['close'].values

    entry_price = bo.price
    actual_days = len(future_df)
    complete = actual_days >= tracking_days

    # MFE: 最大涨幅
    max_high = float(np.max(highs))
    mfe = (max_high - entry_price) / entry_price * 100

    # MFE day: 第一次达到最高价的天数
    mfe_day = int(np.argmax(highs)) + 1

    # MAE: 最大回撤（相对入场价）
    min_low = float(np.min(lows))
    mae = max(0.0, (entry_price - min_low) / entry_price * 100)

    # MAE before MFE: MFE 前的最大回撤
    if mfe_day > 0:
        lows_before_mfe = lows[:mfe_day]
        min_low_before = float(np.min(lows_before_mfe))
        mae_before_mfe = max(0.0, (entry_price - min_low_before) / entry_price * 100)
    else:
        mae_before_mfe = 0.0

    # Max drawdown: 从任意高点到后续低点的最大回撤
    max_drawdown = 0.0
    running_max = entry_price
    for h, l in zip(highs, lows):
        running_max = max(running_max, h)
        drawdown = (running_max - l) / running_max * 100
        max_drawdown = max(max_drawdown, drawdown)

    # Final return
    final_price = float(closes[-1])
    final_return = (final_price - entry_price) / entry_price * 100

    # 成功标签
    success_10 = mfe >= 10.0
    success_20 = mfe >= 20.0
    success_50 = mfe >= 50.0

    # 提取突破特征
    breakout_type = _get_breakout_type(bo)
    volume_surge = getattr(bo, 'volume_surge_ratio', 1.0)
    momentum = getattr(bo, 'momentum', 0.0)
    gap_up = getattr(bo, 'gap_up_pct', 0.0)
    num_peaks = len(bo.broken_peaks) if bo.broken_peaks else 1

    # 最高峰值价格
    highest_peak_price = bo.price
    if bo.broken_peaks:
        highest_peak_price = max(p.price for p in bo.broken_peaks)

    return ShadowResult(
        symbol=bo.symbol,
        breakout_date=bo.date,
        breakout_price=round(entry_price, 4),
        highest_peak_price=round(highest_peak_price, 4),
        atr_value=round(bo.atr_value, 4),
        quality_score=round(getattr(bo, 'quality_score', 0.0), 2),
        breakout_type=breakout_type,
        volume_surge_ratio=round(volume_surge, 2),
        momentum=round(momentum, 4),
        gap_up_pct=round(gap_up, 4),
        num_peaks_broken=num_peaks,
        mfe=round(mfe, 2),
        mae=round(mae, 2),
        mfe_day=mfe_day,
        mae_before_mfe=round(mae_before_mfe, 2),
        final_return=round(final_return, 2),
        final_price=round(final_price, 4),
        max_drawdown=round(max_drawdown, 2),
        tracking_days=actual_days,
        complete=complete,
        success_10=success_10,
        success_20=success_20,
        success_50=success_50,
    )


def _get_breakout_type(bo: Breakout) -> str:
    """提取突破类型"""
    if hasattr(bo, 'breakout_type'):
        return bo.breakout_type
    if hasattr(bo, 'close') and hasattr(bo, 'open'):
        if bo.close > bo.open:
            return 'yang'
        else:
            return 'yin'
    return 'unknown'
