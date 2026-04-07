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
from BreakoutStrategy.factor_registry import INACTIVE_FACTORS

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

        # pre_vol 回看窗口（突破前放量检测）
        self.pre_vol_window = config.get("pre_vol_window", 10)

        # ma_pos 均线周期
        self.ma_pos_period = config.get("ma_pos_period", 20)

        # dd_recov 配置
        self.dd_recov_lookback = config.get("dd_recov_lookback", 252)
        best_recov = config.get("dd_recov_best_recovery", 0.25)
        self.dd_recov_decay_power = 1.0 / best_recov  # b = 1/r*, 峰值在 r* = 1/b

        # ma_curve 配置
        self.ma_curve_period = config.get("ma_curve_period", 50)
        self.ma_curve_stride = config.get("ma_curve_stride", 5)

        # 阻力簇聚类阈值（与 scorer 保持一致，默认引用 peak_supersede_threshold）
        self.cluster_density_threshold = config.get(
            "cluster_density_threshold",
            config.get("peak_supersede_threshold", 0.03),
        )

        # 回测标签配置
        # 格式: [{"max_days": 40}]
        self.label_configs: List[Dict] = config.get("label_configs", [])

    def enrich_breakout(
        self,
        df: pd.DataFrame,
        breakout_info: BreakoutInfo,
        symbol: str,
        detector=None,
        atr_series: pd.Series = None,
        vol_ratio_series: pd.Series = None,
    ) -> Breakout:
        """
        从BreakoutInfo计算完整特征

        Args:
            df: OHLCV数据
            breakout_info: 增量检测返回的突破信息
            symbol: 股票代码
            detector: BreakoutDetector实例（可选，用于获取连续突破信息）
            atr_series: 预计算的 ATR 序列（调用方应一次性计算后复用）
            vol_ratio_series: 预计算的每日放量倍数序列（用于 pre_vol 因子）

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

        # 获取前一日 ATR（用于 ATR 标准化、pk_mom 等）
        atr_value = 0.0
        if atr_series is not None and idx > 0:
            atr_prev = atr_series.iloc[idx - 1]
            if pd.notna(atr_prev) and atr_prev > 0:
                atr_value = float(atr_prev)

        # 计算波动率相关字段（Breakout 基础字段 + 多因子共享中间变量，始终计算）
        inactive = INACTIVE_FACTORS
        annual_volatility = self._calculate_annual_volatility(df, idx)
        gain_5d = self._calculate_gain_5d(df, idx) if 'overshoot' not in inactive else 0.0

        # 注册因子计算（受总开关控制）
        day_str = self._calculate_day_str(intraday_change_pct, gap_up_pct, annual_volatility) if 'day_str' not in inactive else 0.0
        overshoot = self._calculate_overshoot(gain_5d, annual_volatility) if 'overshoot' not in inactive else 0.0

        # 计算突破幅度的 ATR 标准化（可选功能）
        atr_normalized_height = 0.0
        if self.use_atr_normalization and atr_value > 0:
            highest_peak = breakout_info.highest_peak_broken
            breakout_amplitude = row["close"] - highest_peak.price
            atr_normalized_height = breakout_amplitude / atr_value

        volume = self._calculate_volume_ratio(df, idx) if 'volume' not in inactive else 0.0
        pbm = self._calculate_pbm(df, idx, annual_volatility) if 'pbm' not in inactive else 0.0

        # 计算稳定性
        highest_peak = breakout_info.highest_peak_broken
        stability_score = self._calculate_stability(df, idx, highest_peak.price)

        # 计算回测标签
        labels = self._calculate_labels(df, idx)

        streak = self._calculate_streak(detector, idx) if 'streak' not in inactive else 1
        drought = self._calculate_drought(detector, idx) if 'drought' not in inactive else None

        broken_peaks = breakout_info.broken_peaks
        age = self._calculate_age(idx, broken_peaks) if 'age' not in inactive else 0
        height = self._calculate_height(broken_peaks) if 'height' not in inactive else 0.0
        peak_vol = self._calculate_peak_vol(broken_peaks) if 'peak_vol' not in inactive else 0.0
        test = self._calculate_test(broken_peaks) if 'test' not in inactive else 0

        # pk_mom（使用距离 breakout 最近的 peak）
        if 'pk_mom' not in inactive:
            nearest_peak = max(breakout_info.broken_peaks, key=lambda p: p.index)
            pk_mom = self._calculate_pk_momentum(
                df=df,
                peak_idx=nearest_peak.index,
                peak_price=nearest_peak.price,
                breakout_idx=idx,
                atr_value=atr_value,
                atr_series=atr_series,
            )
        else:
            pk_mom = 0.0

        # pre_vol
        pre_vol = 0.0
        if 'pre_vol' not in inactive and vol_ratio_series is not None:
            pre_vol = self._calculate_pre_breakout_volume(vol_ratio_series, idx, self.pre_vol_window)

        ma_pos = self._calculate_ma_pos(df, idx) if 'ma_pos' not in inactive else 0.0
        dd_recov = self._calculate_dd_recov(df, idx) if 'dd_recov' not in inactive else 0.0
        ma_curve = self._calculate_ma_curve(df, idx) if 'ma_curve' not in inactive else 0.0

        return Breakout(
            symbol=symbol,
            date=breakout_info.current_date,
            price=breakout_info.current_price,
            index=idx,
            broken_peaks=breakout_info.broken_peaks,
            superseded_peaks=breakout_info.superseded_peaks,
            breakout_type=breakout_type,
            intraday_change_pct=intraday_change_pct,
            gap_up_pct=gap_up_pct,
            volume=volume,
            pbm=pbm,
            stability_score=stability_score,
            labels=labels,
            streak=streak,
            drought=drought,
            pk_mom=pk_mom,
            annual_volatility=annual_volatility,
            atr_value=atr_value,
            atr_normalized_height=atr_normalized_height,
            day_str=day_str,
            overshoot=overshoot,
            age=age,
            test=test,
            peak_vol=peak_vol,
            height=height,
            pre_vol=pre_vol,
            ma_pos=ma_pos,
            dd_recov=dd_recov,
            ma_curve=ma_curve,
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

    def _calculate_momentum(self, df: pd.DataFrame, index: int) -> tuple[float, int]:
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
            (pbm, n_bars) 涨势强度值和实际使用的K线数量
        """
        lookback = self.continuity_lookback
        start_idx = max(0, index - lookback)

        if start_idx >= index:
            return 0.0, 0

        # 获取收盘价序列（不包含突破日）
        closes = df["close"].iloc[start_idx:index].tolist()
        if len(closes) < 2:
            return 0.0, 0

        # 位移
        displacement = closes[-1] - closes[0]

        # 路径长度
        path_length = sum(abs(closes[i] - closes[i - 1]) for i in range(1, len(closes)))

        if path_length == 0 or closes[0] == 0:
            return 0.0, len(closes)

        # PBM = 标准化位移 × 效率 / 时间
        # 效率 = |位移| / 路径长度（始终为正，0~1）
        # 方向由标准化位移决定
        n_bars = len(closes)
        efficiency = abs(displacement) / path_length
        pbm = (displacement / closes[0]) * efficiency / n_bars

        return pbm, n_bars

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

        标签定义：(N天内最高价 - 突破日收盘价) / 突破日收盘价
        - 基准价：突破日收盘价（不编码任何交易策略假设）
        - 最高价范围：突破后1到N天内，使用 high 价格
        - 不包括突破当日

        Args:
            df: OHLCV数据
            index: 突破点索引

        Returns:
            标签字典，格式：{"label_40": 0.15, "label_20": None}
            数据不足时对应值为 None
        """
        labels = {}
        breakout_price = df.iloc[index]["close"]

        for config in self.label_configs:
            max_days = config.get("max_days", 20)
            label_key = f"label_{max_days}"

            max_end = min(len(df), index + max_days + 1)
            future_data = df.iloc[index + 1 : max_end]

            if len(future_data) < max_days:
                labels[label_key] = None
                continue

            max_high = future_data["close"].max()

            if breakout_price > 0:
                label_value = (max_high - breakout_price) / breakout_price
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
        atr_series: pd.Series = None,
    ) -> float:
        """
        计算 pk_momentum（近期 peak 凹陷深度）

        逻辑：
        - 时间窗口内才计算（近期 peak 才有意义，远期已被 height_factor 覆盖）
        - 凹陷深度决定值大小

        公式：pk_momentum = 1 + log(1 + D_atr)
        其中 D_atr = (peak_price - trough_price) / ATR

        D_atr 的分母使用 peak 时刻（peak_idx - 1）的 ATR，而非 breakout 前一日的 ATR。
        原因：V 型反弹中，反弹段会膨胀 breakout 前一日的 ATR，导致 D_atr 分母增大、
        pk_momentum 反而降低，与"奖励深蹲起跳"的设计意图矛盾。使用 peak 时刻的 ATR
        反映回调开始前的波动率环境，消除反弹段对分母的污染。

        Args:
            df: OHLCV 数据
            peak_idx: peak 的索引
            peak_price: peak 的价格
            breakout_idx: breakout 的索引
            atr_value: breakout 前一日 ATR（回退值）
            atr_series: 完整 ATR 序列，用于取 peak 时刻 ATR

        Returns:
            pk_momentum：0 表示无近期 peak，>1 表示有近期 peak
        """
        delta_t = breakout_idx - peak_idx

        # 超出时间窗口，不计算
        if delta_t > self.pk_lookback or delta_t <= 0:
            return 0.0

        if atr_value <= 0:
            return 0.0

        # D_atr 分母：优先用 peak 时刻 ATR，不可用时回退到 breakout 前一日 ATR
        denominator = atr_value
        if atr_series is not None and peak_idx - 1 >= 0:
            peak_atr = atr_series.iloc[peak_idx - 1]
            if peak_atr > 0:
                denominator = peak_atr

        # 找到 peak 和 breakout 之间的最低价（trough）
        segment = df["low"].iloc[peak_idx : breakout_idx + 1]
        trough_price = segment.min()

        # 计算凹陷深度（ATR 标准化）
        dip_depth = peak_price - trough_price
        if dip_depth <= 0:
            return 1.0  # 无凹陷，返回基础值

        d_atr = dip_depth / denominator

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

    # ---- 以下为注册因子的 _calculate_xxx 方法 ----

    def _calculate_day_str(
        self,
        intraday_change_pct: float,
        gap_up_pct: float,
        annual_volatility: float,
    ) -> float:
        """
        计算突破日强度比率（DayStr），σ 单位

        取日内涨幅与跳空幅度相对于日波动率的比率中的较大者。

        Args:
            intraday_change_pct: 日内涨幅（收盘 vs 开盘）
            gap_up_pct: 跳空幅度
            annual_volatility: 年化波动率

        Returns:
            突破日强度比率（σ 单位），波动率无效时返回 0.0
        """
        if annual_volatility <= 0:
            return 0.0
        daily_vol = annual_volatility / math.sqrt(252)
        idr_ratio = intraday_change_pct / daily_vol if intraday_change_pct > 0 else 0.0
        gap_ratio = gap_up_pct / daily_vol if gap_up_pct > 0 else 0.0
        return max(idr_ratio, gap_ratio)

    def _calculate_overshoot(
        self,
        gain_5d: float,
        annual_volatility: float,
    ) -> float:
        """
        计算超涨比率（Overshoot），σ 单位

        公式：gain_5d / (annual_volatility / sqrt(50.4))

        Args:
            gain_5d: 5 日涨幅（小数形式）
            annual_volatility: 年化波动率

        Returns:
            超涨比率（σ 单位），波动率无效时返回 0.0
        """
        if annual_volatility <= 0:
            return 0.0
        five_day_vol = annual_volatility / math.sqrt(50.4)
        return gain_5d / five_day_vol

    def _calculate_pbm(
        self,
        df: pd.DataFrame,
        idx: int,
        annual_volatility: float,
    ) -> float:
        """
        计算突破前涨势强度（PBM），标准化为 σ_N 单位

        内部调用 _calculate_momentum() 获取 raw_momentum 和 n_bars，
        然后执行波动率标准化：pbm = raw_momentum * sqrt(n_bars) / daily_vol

        Args:
            df: OHLCV 数据
            idx: 突破点索引
            annual_volatility: 年化波动率

        Returns:
            标准化后的 PBM 值
        """
        raw_momentum, n_bars = self._calculate_momentum(df, idx)
        if annual_volatility > 0 and n_bars > 0:
            daily_vol = annual_volatility / math.sqrt(252)
            return raw_momentum * math.sqrt(n_bars) / daily_vol
        return 0.0

    @staticmethod
    def _calculate_streak(detector, idx: int) -> int:
        """
        计算连续突破次数

        Args:
            detector: BreakoutDetector 实例（可为 None）
            idx: 突破点索引

        Returns:
            近期突破次数（无 detector 时返回 1）
        """
        if detector is not None:
            return detector.get_recent_breakout_count(idx, debug=DEBUG_MOMENTUM)
        return 1

    @staticmethod
    def _calculate_drought(detector, idx: int) -> Optional[int]:
        """
        计算距上次突破的交易日间隔

        Args:
            detector: BreakoutDetector 实例（可为 None）
            idx: 突破点索引

        Returns:
            交易日间隔，None 表示首次突破或无 detector
        """
        if detector is not None:
            return detector.get_days_since_last_breakout(idx)
        return None

    @staticmethod
    def _calculate_age(idx: int, broken_peaks) -> int:
        """
        计算最老被突破峰值的年龄（交易日数）

        Args:
            idx: 突破点索引
            broken_peaks: 被突破的峰值列表

        Returns:
            最大峰值年龄
        """
        return max(idx - p.index for p in broken_peaks)

    @staticmethod
    def _calculate_height(broken_peaks) -> float:
        """
        计算峰值最大相对高度

        Args:
            broken_peaks: 被突破的峰值列表

        Returns:
            最大 relative_height
        """
        return max(p.relative_height for p in broken_peaks)

    @staticmethod
    def _calculate_peak_vol(broken_peaks) -> float:
        """
        计算峰值最大放量倍数

        Args:
            broken_peaks: 被突破的峰值列表

        Returns:
            最大 volume_peak
        """
        return max(p.volume_peak for p in broken_peaks)

    def _calculate_test(self, broken_peaks) -> int:
        """
        计算最大阻力簇峰值数（贪心聚类算法）

        对 broken_peaks 按价格排序，相邻价格差 <= cluster_density_threshold
        的归为同一簇，返回最大簇的大小。

        Args:
            broken_peaks: 被突破的峰值列表

        Returns:
            最大阻力簇大小
        """
        sorted_prices = sorted(p.price for p in broken_peaks)
        best_cluster = 1
        current_cluster = 1
        for i in range(1, len(sorted_prices)):
            if (sorted_prices[i] - sorted_prices[i - 1]) / sorted_prices[i - 1] <= self.cluster_density_threshold:
                current_cluster += 1
            else:
                best_cluster = max(best_cluster, current_cluster)
                current_cluster = 1
        return max(best_cluster, current_cluster)

    def _calculate_ma_pos(self, df: pd.DataFrame, idx: int) -> float:
        """
        计算均线位置（MA Position）：突破日收盘价相对 N 日均线的溢价率

        衡量中期动量积累强度。值越大说明突破前买方力量越强。

        Args:
            df: OHLCV 数据（可能含 ma_20/ma_50 预计算列）
            idx: 突破点索引

        Returns:
            close / MA_N - 1.0，MA 无效时返回 0.0
        """
        period = self.ma_pos_period
        ma_col = f"ma_{period}"

        # 优先使用 df 中已预计算的均线列
        if ma_col in df.columns:
            ma_val = df[ma_col].iloc[idx]
        else:
            # 动态计算（当 period 非 20/50 时）
            if idx < period - 1:
                return 0.0
            ma_val = df["close"].iloc[idx - period + 1: idx + 1].mean()

        if pd.notna(ma_val) and ma_val > 0:
            return df["close"].iloc[idx] / ma_val - 1.0
        return 0.0

    def _calculate_dd_recov(self, df: pd.DataFrame, idx: int) -> float:
        """
        回撤恢复度（幂次衰减版）

        在 lookback 窗口内找到最高点，计算 drawdown 和 recovery_ratio，
        用 decay_power 控制右侧衰减，使"底部早期恢复"获得最高分。

        dd_recov = drawdown * recovery * (1 - recovery)^(decay_power - 1)

        峰值位置 r* = 1/decay_power：
        - decay_power=2: r*=0.50（对称，原始版本）
        - decay_power=4: r*=0.25（推荐，惩罚追高）

        Args:
            df: OHLCV 数据
            idx: 突破点索引

        Returns:
            回撤恢复度，无回撤时返回 0.0
        """
        lookback = self.dd_recov_lookback
        decay_power = self.dd_recov_decay_power
        start = max(0, idx - lookback)

        highs = df["high"].values[start:idx + 1]
        peak_local_idx = np.argmax(highs)
        peak_price = highs[peak_local_idx]
        peak_abs_idx = start + peak_local_idx

        current_price = df["close"].values[idx]

        # 无回撤（当前就是最高点）-> 非底部
        if peak_price <= 0 or current_price >= peak_price:
            return 0.0

        drawdown = (peak_price - current_price) / peak_price

        # 从 peak 之后的最低点
        trough_price = df["low"].values[peak_abs_idx:idx + 1].min()
        range_total = peak_price - trough_price
        if range_total <= 0:
            return 0.0

        recovery_ratio = (current_price - trough_price) / range_total

        return drawdown * recovery_ratio * (1 - recovery_ratio) ** (decay_power - 1)

    def _calculate_ma_curve(self, df: pd.DataFrame, idx: int) -> float:
        """
        MA 曲率因子：宽间隔二阶差分的归一化值

        使用 stride=k 的 3 点采样计算 MA 的二阶导数：
          d2 = (MA[t] - 2*MA[t-k] + MA[t-2k]) / k²

        等价于比较最近 k 天的 MA 斜率与前一个 k 天的 MA 斜率。
        正值 = MA 下跌减速或上涨加速 → 底部反转信号
        负值 = MA 上涨减速或下跌加速

        归一化：d2 / MA[t] * period²，使不同价格水平和周期可比。

        Args:
            df: OHLCV 数据（可能含 ma_50 预计算列）
            idx: 突破点索引

        Returns:
            归一化曲率值
        """
        period = self.ma_curve_period   # 默认 50
        k = self.ma_curve_stride        # 宽间隔步幅，默认 5

        if idx < period + 2 * k:
            return 0.0

        # 只需 3 个 MA 采样点：t, t-k, t-2k
        ma_col = f"ma_{period}"
        if ma_col in df.columns:
            ma_t = df[ma_col].iat[idx]
            ma_tk = df[ma_col].iat[idx - k]
            ma_t2k = df[ma_col].iat[idx - 2 * k]
        else:
            close = df["close"].values
            ma_t = close[idx - period + 1: idx + 1].mean()
            ma_tk = close[idx - k - period + 1: idx - k + 1].mean()
            ma_t2k = close[idx - 2 * k - period + 1: idx - 2 * k + 1].mean()

        if np.isnan(ma_t) or np.isnan(ma_tk) or np.isnan(ma_t2k) or ma_t <= 0:
            return 0.0

        d2 = (ma_t - 2 * ma_tk + ma_t2k) / (k ** 2)
        return (d2 / ma_t) * (period ** 2)

    @staticmethod
    def precompute_vol_ratio_series(df: pd.DataFrame, lookback: int = 63) -> pd.Series:
        """
        预计算每日放量倍数序列

        vol_ratio[d] = volume[d] / mean(volume[max(0, d-lookback) : d])
        使用 rolling + shift 实现，语义与逐日手动计算完全一致。

        Args:
            df: 含 volume 列的 OHLCV DataFrame
            lookback: 均量回看天数（默认 63，即 3 个月）

        Returns:
            放量倍数 Series（与 df 同索引）
        """
        avg_vol = df["volume"].rolling(lookback, min_periods=1).mean().shift(1)
        return (df["volume"] / avg_vol).replace([np.inf, -np.inf], 0.0).fillna(0.0)

    @staticmethod
    def _calculate_pre_breakout_volume(
        vol_ratio_series: pd.Series, idx: int, window: int = 10
    ) -> float:
        """
        突破前 window 天内每日放量倍数的最大值

        Args:
            vol_ratio_series: precompute_vol_ratio_series() 的输出
            idx: 突破点索引
            window: 回看窗口天数

        Returns:
            窗口内最大放量倍数
        """
        pre_start = max(0, idx - window)
        segment = vol_ratio_series.iloc[pre_start:idx]
        if len(segment) == 0:
            return 0.0
        result = segment.max()
        return 0.0 if pd.isna(result) else float(result)
