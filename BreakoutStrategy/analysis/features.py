"""
特征计算模块

从BreakoutInfo（增量检测结果）计算完整的Breakout对象（包含丰富特征）
"""

import math
import os
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .breakout_detector import BreakoutInfo, Breakout
from .indicators import TechnicalIndicators

# 设置环境变量 DEBUG_MOMENTUM=1 启用调试输出
DEBUG_MOMENTUM = os.environ.get("DEBUG_MOMENTUM", "0") == "1"
# 设置环境变量 DEBUG_VOLUME=1 启用成交量计算调试输出
DEBUG_VOLUME = os.environ.get("DEBUG_VOLUME", "0") == "1"


class FeatureCalculator:
    """特征计算器"""

    def __init__(self, config: Optional[dict] = None):
        """
        初始化特征计算器

        Args:
            config: 配置参数字典
        """
        if config is None:
            config = {}

        self.stability_lookforward = config.get("stability_lookforward", 10)
        self.continuity_lookback = config.get("continuity_lookback", 5)

        # ATR 配置（可选功能）
        self.atr_period = config.get("atr_period", 14)
        self.use_atr_normalization = config.get("use_atr_normalization", False)

        # gain_window: 涨幅计算窗口（用于 gain_5d 等）
        self.gain_window = config.get("gain_window", 5)

        # pk_momentum 时间窗口（用于近期 peak 检测）
        self.pk_lookback = config.get("pk_lookback", 30)

        # 回测标签配置
        # 格式: [{"min_days": 5, "max_days": 20}, {"min_days": 3, "max_days": 10}]
        self.label_configs: List[Dict] = config.get("label_configs", [])

    def enrich_breakout(
        self,
        df: pd.DataFrame,
        breakout_info: BreakoutInfo,
        symbol: str,
        detector=None,
        atr_series: pd.Series = None,
    ) -> Breakout:
        """
        从BreakoutInfo计算完整特征

        Args:
            df: OHLCV数据
            breakout_info: 增量检测返回的突破信息
            symbol: 股票代码
            detector: BreakoutDetector实例（可选，用于获取连续突破信息）
            atr_series: 预计算的 ATR 序列（调用方应一次性计算后复用）

        Returns:
            包含所有特征的Breakout对象
        """
        idx = breakout_info.current_index
        row = df.iloc[idx]

        # 计算突破类型
        breakout_type = self._classify_type(row)

        # 计算日内涨幅（收盘 vs 开盘）
        if row["open"] > 0:
            intraday_change_pct = (row["close"] - row["open"]) / row["open"]
        else:
            intraday_change_pct = 0.0

        # 获取前一日收盘价（用于跳空和日间涨幅计算）
        prev_close = df["close"].iloc[idx - 1] if idx > 0 else 0.0

        # 计算跳空
        if idx > 0 and prev_close > 0:
            gap_up = row["open"] > prev_close
            gap_up_pct = (
                (row["open"] - prev_close) / prev_close
                if gap_up
                else 0.0
            )
        else:
            gap_up = False
            gap_up_pct = 0.0

        # 获取前一日 ATR（用于 daily_return_atr_ratio）
        atr_value = 0.0
        if atr_series is not None and idx > 0:
            atr_prev = atr_series.iloc[idx - 1]
            if pd.notna(atr_prev) and atr_prev > 0:
                atr_value = float(atr_prev)

        # 计算日间涨幅的 ATR 标准化版本（单日强势K线指标）
        # daily_return_atr_ratio = (close[i] - close[i-1]) / atr[i-1]
        daily_return_atr_ratio = 0.0
        if atr_value > 0 and idx > 0:
            daily_return_atr_ratio = (row["close"] - prev_close) / atr_value

        # 计算跳空的 ATR 标准化版本
        # gap_atr_ratio = (open[i] - close[i-1]) / atr[i-1]
        gap_atr_ratio = 0.0
        if gap_up and atr_value > 0:
            gap_atr_ratio = (row["open"] - prev_close) / atr_value

        # 计算波动率相关字段（用于评分的波动率标准化）
        gain_5d = self._calculate_gain_5d(df, idx)
        annual_volatility = self._calculate_annual_volatility(df, idx)

        # 计算突破幅度的 ATR 标准化（可选功能）
        atr_normalized_height = 0.0
        if self.use_atr_normalization and atr_value > 0:
            highest_peak = breakout_info.highest_peak_broken
            breakout_amplitude = row["close"] - highest_peak.price
            atr_normalized_height = breakout_amplitude / atr_value

        # 计算放量倍数
        volume_surge_ratio = self._calculate_volume_ratio(df, idx)

        # 计算突破前涨势强度 (PBM)
        momentum = self._calculate_momentum(df, idx)

        # 计算稳定性
        highest_peak = breakout_info.highest_peak_broken
        stability_score = self._calculate_stability(df, idx, highest_peak.price)

        # 计算回测标签
        labels = self._calculate_labels(df, idx)

        # 计算连续突破次数（PLAN A: Momentum）
        recent_breakout_count = 1
        if detector is not None:
            recent_breakout_count = detector.get_recent_breakout_count(idx, debug=DEBUG_MOMENTUM)

        # 计算 pk_momentum（使用距离 breakout 最近的 peak）
        nearest_peak = max(breakout_info.broken_peaks, key=lambda p: p.index)
        pk_momentum = self._calculate_pk_momentum(
            df=df,
            peak_idx=nearest_peak.index,
            peak_price=nearest_peak.price,
            breakout_idx=idx,
            atr_value=atr_value,
        )

        return Breakout(
            symbol=symbol,
            date=breakout_info.current_date,
            price=breakout_info.current_price,
            index=idx,
            broken_peaks=breakout_info.broken_peaks,
            superseded_peaks=breakout_info.superseded_peaks,
            breakout_type=breakout_type,
            intraday_change_pct=intraday_change_pct,
            gap_up=gap_up,
            gap_up_pct=gap_up_pct,
            gap_atr_ratio=gap_atr_ratio,
            volume_surge_ratio=volume_surge_ratio,
            momentum=momentum,
            stability_score=stability_score,
            labels=labels,
            recent_breakout_count=recent_breakout_count,
            daily_return_atr_ratio=daily_return_atr_ratio,
            pk_momentum=pk_momentum,
            gain_5d=gain_5d,
            annual_volatility=annual_volatility,
            atr_value=atr_value,
            atr_normalized_height=atr_normalized_height,
        )

    def _classify_type(self, row: pd.Series) -> str:
        """
        分类突破类型

        - 阳线突破：收盘价 > 开盘价
        - 阴线突破：收盘价 < 开盘价
        - 上影线突破：收盘价 ≈ 开盘价（差异<1%）

        Args:
            row: 突破日的行情数据

        Returns:
            突破类型：'yang', 'yin', 'shadow'
        """
        open_price = row["open"]
        close_price = row["close"]

        if open_price == 0:
            return "shadow"

        change_ratio = abs((close_price - open_price) / open_price)

        if change_ratio < 0.01:  # 收盘价与开盘价差异<1%
            return "shadow"
        elif close_price > open_price:
            return "yang"
        else:
            return "yin"

    def _calculate_volume_ratio(self, df: pd.DataFrame, index: int) -> float:
        """
        计算放量倍数

        Args:
            df: 行情数据
            index: 突破点索引

        Returns:
            放量倍数
        """
        VOLUME_LOOKBACK = 63
        window_start = max(0, index - VOLUME_LOOKBACK)
        actual_window_size = index - window_start
        avg_volume = df["volume"].iloc[window_start:index].mean()

        current_volume = df["volume"].iloc[index]
        if avg_volume > 0:
            ratio = current_volume / avg_volume
        else:
            ratio = 1.0

        # 调试输出：成交量计算详情
        if DEBUG_VOLUME:
            df_start_date = df.index[0].strftime("%Y-%m-%d") if hasattr(df.index[0], 'strftime') else str(df.index[0])
            breakout_date = df.index[index].strftime("%Y-%m-%d") if hasattr(df.index[index], 'strftime') else str(df.index[index])
            window_incomplete = actual_window_size < VOLUME_LOOKBACK
            print(f"[DEBUG_VOLUME] breakout_date={breakout_date}, index={index}, "
                  f"window_start={window_start}, actual_window={actual_window_size}, "
                  f"df_start={df_start_date}, len(df)={len(df)}, "
                  f"avg_vol={avg_volume:.0f}, cur_vol={current_volume:.0f}, "
                  f"ratio={ratio:.2f}x"
                  f"{' ⚠️ INCOMPLETE_WINDOW' if window_incomplete else ''}")

        return ratio

    def _calculate_momentum(self, df: pd.DataFrame, index: int) -> float:
        """
        计算突破前涨势强度 (Pre-Breakout Momentum, PBM)

        公式: PBM = (位移/起点价格) × (位移/路径长度) / K线数量
             = ΔP² / (P₀ × L × N)

        涵义:
        - 位移(ΔP): 价格从起点到终点的净变化
        - 路径长度(L): 所有日间波动的绝对值之和
        - 位移/路径 = 路径效率，衡量涨势的"直接程度"
        - 除以 N 进行时间标准化

        Args:
            df: 行情数据
            index: 突破点索引（不包含在计算中）

        Returns:
            涨势强度值，正值表示涨势，负值表示跌势
            参考值: > 0.001 存在涨势, > 0.003 强劲涨势
        """
        lookback = self.continuity_lookback
        start_idx = max(0, index - lookback)

        if start_idx >= index:
            return 0.0

        # 获取收盘价序列（不包含突破日）
        closes = df["close"].iloc[start_idx:index].tolist()
        if len(closes) < 2:
            return 0.0

        # 位移
        displacement = closes[-1] - closes[0]

        # 路径长度
        path_length = sum(abs(closes[i] - closes[i - 1]) for i in range(1, len(closes)))

        if path_length == 0 or closes[0] == 0:
            return 0.0

        # PBM = 标准化位移 × 效率 / 时间
        # 效率 = |位移| / 路径长度（始终为正，0~1）
        # 方向由标准化位移决定
        n_bars = len(closes)
        efficiency = abs(displacement) / path_length
        pbm = (displacement / closes[0]) * efficiency / n_bars

        return pbm

    def _calculate_stability(
        self, df: pd.DataFrame, index: int, peak_price: float
    ) -> float:
        """
        计算稳定性分数

        稳定性定义：突破后N天内，价格不跌破最高峰值价格的比例

        Args:
            df: 行情数据
            index: 突破点索引
            peak_price: 最高峰值价格

        Returns:
            稳定性分数（0-100）
        """
        # 向后查看stability_lookforward天
        lookforward_end = min(len(df), index + self.stability_lookforward + 1)
        future_data = df.iloc[index + 1 : lookforward_end]

        if len(future_data) == 0:
            # 无未来数据，无法评估稳定性
            return 50.0  # 返回中性分数

        # 统计价格不跌破峰值的天数
        stable_days = (future_data["low"] >= peak_price).sum()
        total_days = len(future_data)

        stability_score = (stable_days / total_days) * 100 if total_days > 0 else 50.0

        return stability_score

    def _calculate_labels(
        self, df: pd.DataFrame, index: int
    ) -> Dict[str, Optional[float]]:
        """
        计算回测标签

        标签定义：(最低点之后到N天内的最高价 - M天内最低价) / M天内最低价
        - M天内最低价：使用 close 价格
        - 最高价范围：从最低点出现日之后到N天内，使用 high 价格
        - M < N，均不包括突破当日

        Args:
            df: OHLCV数据
            index: 突破点索引

        Returns:
            标签字典，格式：{"label_5_20": 0.15, "label_3_10": None}
            数据不足时对应值为 None
        """
        labels = {}

        for config in self.label_configs:
            min_days = config.get("min_days", 5)  # M: 最低价窗口
            max_days = config.get("max_days", 20)  # N: 最高价窗口

            label_key = f"label_{min_days}_{max_days}"

            # 计算数据范围（不包括突破当日）
            min_end = min(len(df), index + min_days + 1)
            max_end = min(len(df), index + max_days + 1)

            future_min_data = df.iloc[index + 1 : min_end]  # M天内数据

            # 检查数据是否充足
            if len(future_min_data) < min_days or (max_end - index - 1) < max_days:
                labels[label_key] = None
                continue

            # 1. 在M天内找最低 close 及其位置
            min_close = future_min_data["close"].min()
            # argmin() 返回相对位置索引，加上起始位置得到在 df 中的绝对位置
            min_close_pos = index + 1 + future_min_data["close"].argmin()

            # 2. 从最低点之后到N天内找最高 high
            future_max_data = df.iloc[min_close_pos + 1 : max_end]

            if len(future_max_data) == 0:
                # 最低点在窗口末尾，没有后续数据计算最高价
                labels[label_key] = None
                continue

            max_high = future_max_data["high"].max()

            # 计算标签
            if min_close > 0:
                label_value = (max_high - min_close) / min_close
            else:
                label_value = None

            labels[label_key] = label_value

        return labels

    def _calculate_pk_momentum(
        self,
        df: pd.DataFrame,
        peak_idx: int,
        peak_price: float,
        breakout_idx: int,
        atr_value: float,
    ) -> float:
        """
        计算 pk_momentum（近期 peak 凹陷深度）

        逻辑：
        - 时间窗口内才计算（近期 peak 才有意义，远期已被 height_bonus 覆盖）
        - 凹陷深度决定值大小

        公式：pk_momentum = 1 + log(1 + D_atr)
        其中 D_atr = (peak_price - trough_price) / ATR

        Args:
            df: OHLCV 数据
            peak_idx: peak 的索引
            peak_price: peak 的价格
            breakout_idx: breakout 的索引
            atr_value: ATR 值

        Returns:
            pk_momentum：0 表示无近期 peak，>1 表示有近期 peak
        """
        delta_t = breakout_idx - peak_idx

        # 超出时间窗口，不计算
        if delta_t > self.pk_lookback or delta_t <= 0:
            return 0.0

        if atr_value <= 0:
            return 0.0

        # 找到 peak 和 breakout 之间的最低价（trough）
        segment = df["low"].iloc[peak_idx : breakout_idx + 1]
        trough_price = segment.min()

        # 计算凹陷深度（ATR 标准化）
        dip_depth = peak_price - trough_price
        if dip_depth <= 0:
            return 1.0  # 无凹陷，返回基础值

        d_atr = dip_depth / atr_value

        # pk_momentum = 1 + log(1 + D_atr)
        return 1.0 + math.log(1 + d_atr)

    def _calculate_gain_5d(self, df: pd.DataFrame, idx: int) -> float:
        """
        计算 5 日涨幅（绝对值）

        用于波动率动态阈值判断：不同波动率的股票有不同的"超涨"绝对阈值

        Args:
            df: OHLCV 数据
            idx: 当前 bar 索引

        Returns:
            5 日涨幅（小数形式，如 0.15 表示 15%）
        """
        if idx < self.gain_window:
            return 0.0

        close = df["close"].values

        if close[idx - self.gain_window] <= 0:
            return 0.0

        return (close[idx] - close[idx - self.gain_window]) / close[idx - self.gain_window]

    def _calculate_annual_volatility(self, df: pd.DataFrame, idx: int) -> float:
        """
        计算年化波动率（基于过去 252 天日收益率标准差）

        用于波动率动态阈值：
        - 低波动股票（如公用事业）的超涨阈值应该更低
        - 高波动股票（如成长股）的超涨阈值应该更高

        公式：annual_vol = std(daily_returns) * sqrt(252)

        Args:
            df: OHLCV 数据
            idx: 当前 bar 索引

        Returns:
            年化波动率（小数形式，如 0.30 表示 30%）
        """
        # 使用最多 252 天数据，至少需要 20 天
        lookback = min(252, idx)
        if lookback < 20:
            return 0.0

        close = df["close"].values

        # 计算日收益率
        returns = []
        for i in range(idx - lookback + 1, idx + 1):
            if i >= 1 and close[i - 1] > 0:
                ret = (close[i] - close[i - 1]) / close[i - 1]
                returns.append(ret)

        if len(returns) < 20:
            return 0.0

        # 年化波动率 = 日收益率标准差 * sqrt(252)
        return np.std(returns) * np.sqrt(252)
