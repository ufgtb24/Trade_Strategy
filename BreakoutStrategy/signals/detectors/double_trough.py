"""
双底检测器 (Double Trough)

与 V_REVERSAL 的核心区别：
- V_REVERSAL: TR1 仅是 126 日最低点（纯价格定义），持续下跌中频繁出现
- DOUBLE_TROUGH: TR1 必须是 126 日最低点 + 在 [TR1, TR2] 区间内有足够的反弹

双底形态：
        高点(bounce >= first_bounce_atr * ATR)
       ↗    ↘
TR1  ↗        ↘  TR2
(底)            (次底)

双底定义：
1. TR1: 126 日内的绝对最低点
2. TR2: TR1 之后的第一个形状确认 trough，且价格 > TR1
3. 反弹约束：[TR1, TR2] 区间内的最高点相对 TR1 涨幅 >= first_bounce_atr * ATR
4. 结构紧邻约束：TR2 必须是 TR1 之后的第一个 trough，中间不跳过
5. 信号日期 = TR2 确认日期

参数使用 ATR 倍数进行标准化，以适应不同价格水平和波动率的股票。
"""

from typing import List, Tuple

import numpy as np
import pandas as pd

from ..models import AbsoluteSignal, SignalType
from .base import SignalDetector
from .trough import TroughDetector


class DoubleTroughDetector(SignalDetector):
    """
    双底检测器

    参数：
        min_of: 回看窗口，用于确定 TR1（窗口内绝对最低点）
        first_bounce_atr: TR1 之后的最小反弹高度，以 ATR 倍数衡量（核心参数）
        min_tr2_depth_atr: TR2 相对区间高点的最小下跌深度，以 ATR 倍数衡量
        max_gap_days: TR1 和 TR2 之间最大间隔天数
        min_recovery_atr: TR2 需比 TR1 高至少 X 倍 ATR（可选，默认 0.1）
        atr_period: ATR 计算周期
        trough_window: TR2 形状检测窗口
        trough_min_side_bars: TR2 形状检测的单侧最小 K 线数
        tr1_measure: TR1 价格衡量方式 ("low", "close", "body_bottom")
        tr2_measure: TR2 价格衡量方式 ("low", "close", "body_bottom")
    """

    def __init__(
        self,
        min_of: int = 126,
        first_bounce_atr: float = 1.5,
        min_tr2_depth_atr: float = 0.8,
        max_gap_days: int = 60,
        min_recovery_atr: float = 0.1,
        atr_period: int = 14,
        trough_window: int = 6,
        trough_min_side_bars: int = 2,
        tr1_measure: str = "low",
        tr2_measure: str = "low",
        bounce_high_measure: str = "close",
        support_trough_window: int = None,
        support_trough_min_side_bars: int = 1,
    ):
        self.min_of = min_of
        self.first_bounce_atr = first_bounce_atr
        self.min_tr2_depth_atr = min_tr2_depth_atr
        self.max_gap_days = max_gap_days
        self.min_recovery_atr = min_recovery_atr
        self.atr_period = atr_period
        self.tr1_measure = tr1_measure
        self.tr2_measure = tr2_measure
        self.bounce_high_measure = bounce_high_measure

        # 创建 trough 检测器（用于 TR2 形状检测）
        self.trough_detector = TroughDetector(
            window=trough_window,
            min_side_bars=trough_min_side_bars,
            measure=tr2_measure,
        )

        # 支撑测试 trough 检测参数（使用 close 衡量市场共识）
        self.support_trough_window = support_trough_window or trough_window
        self.support_trough_min_side_bars = support_trough_min_side_bars

        # 记录因数据异常被跳过的股票
        self.skipped_symbols: List[str] = []

    def reset_skipped(self):
        """重置跳过列表（每次批量扫描前调用）"""
        self.skipped_symbols = []

    def _get_price_by_measure(self, df: pd.DataFrame, measure: str) -> pd.Series:
        """
        根据 measure 获取价格序列

        Args:
            df: OHLCV 数据
            measure: 价格衡量方式 ("low", "close", "body_bottom")

        Returns:
            价格序列
        """
        if measure == "low":
            return df["low"]
        elif measure == "close":
            return df["close"]
        elif measure == "body_bottom":
            return pd.Series(
                np.minimum(df["open"].values, df["close"].values), index=df.index
            )
        else:
            return df["low"]

    def _get_tr2_price(self, df: pd.DataFrame, index: int) -> float:
        """
        根据 tr2_measure 获取 TR2 的比较价格

        Args:
            df: OHLCV 数据
            index: TR2 的索引

        Returns:
            TR2 的比较价格
        """
        return self._get_price_by_measure(df, self.tr2_measure).iloc[index]

    def _find_126d_low(self, df: pd.DataFrame, end_index: int) -> Tuple[int, float, pd.Timestamp]:
        """
        找到 end_index 之前的 126 日最低点（不含 end_index 当天）

        Args:
            df: OHLCV 数据
            end_index: 计算截止索引（不含，即 TR2 的索引）

        Returns:
            (最低点索引, 最低价格, 最低点日期)
        """
        lookback_start = max(0, end_index - self.min_of)
        price_series = self._get_price_by_measure(df, self.tr1_measure)
        window_prices = price_series.iloc[lookback_start:end_index]
        min_idx = window_prices.idxmin()
        # 转换为整数位置索引
        min_pos = df.index.get_loc(min_idx)
        return min_pos, price_series.iloc[min_pos], min_idx

    def _validate_tr1_bounce(
        self, bounce_high: float, tr1_price: float, atr_value: float
    ) -> Tuple[bool, float, float]:
        """
        验证 TR1 反弹幅度是否足够（基于 ATR 倍数）

        Args:
            bounce_high: [TR1, TR2] 区间内的最高收盘价
            tr1_price: TR1 的价格
            atr_value: TR1 位置的 ATR 值

        Returns:
            (是否满足反弹要求, 反弹百分比, 反弹 ATR 倍数)
        """
        if tr1_price <= 0 or bounce_high <= 0 or atr_value <= 0:
            return False, 0.0, 0.0

        bounce_amount = bounce_high - tr1_price
        bounce_pct = bounce_amount / tr1_price * 100  # 保留百分比用于 details
        bounce_atr_ratio = bounce_amount / atr_value
        return bounce_atr_ratio >= self.first_bounce_atr, bounce_pct, bounce_atr_ratio

    def _validate_tr2_depth(
        self, bounce_high: float, tr2_price: float, atr_value: float
    ) -> Tuple[bool, float, float]:
        """
        验证 TR2 相对于区间高点的下跌深度（基于 ATR 倍数）

        与 _validate_tr1_bounce 对称：
        - _validate_tr1_bounce: (bounce_high - tr1) / atr >= first_bounce_atr
        - _validate_tr2_depth:  (bounce_high - tr2) / atr >= min_tr2_depth_atr

        Args:
            bounce_high: [TR1, TR2] 区间内的最高价
            tr2_price: TR2 的价格
            atr_value: TR1 位置的 ATR 值

        Returns:
            (是否满足深度要求, 跌幅百分比, 深度 ATR 倍数)
        """
        if bounce_high <= 0 or atr_value <= 0:
            return False, 0.0, 0.0

        depth_amount = bounce_high - tr2_price
        depth_pct = depth_amount / bounce_high * 100
        depth_atr_ratio = depth_amount / atr_value

        # 如果 min_tr2_depth_atr <= 0，跳过检查
        if self.min_tr2_depth_atr <= 0:
            return True, depth_pct, depth_atr_ratio

        return depth_atr_ratio >= self.min_tr2_depth_atr, depth_pct, depth_atr_ratio

    def detect(
        self, df: pd.DataFrame, symbol: str, end_index: int = None
    ) -> List[AbsoluteSignal]:
        """
        检测双底信号

        状态机逻辑：
        1. 检测所有形状确认的 trough
        2. 遍历每个 trough 作为潜在 TR2
        3. 找到该时刻的 126 日最低点作为 TR1
        4. 验证 TR1 满足 first_bounce_atr 约束（ATR 倍数）
        5. 检查 TR2 > TR1 等其他约束
        6. 生成 DOUBLE_TROUGH 信号

        Args:
            df: OHLCV 数据
            symbol: 股票代码
            end_index: 检测结束索引（不含），默认检测到 df 末尾

        Returns:
            检测到的 DOUBLE_TROUGH 信号列表
        """
        signals = []

        if len(df) < self.min_of:
            return signals

        # 截取 df 到 end_index，确保 TroughDetector 只检测指定范围
        if end_index is not None:
            df = df.iloc[:end_index]

        # 计算 ATR 序列（局部导入，避免循环依赖风险）
        from BreakoutStrategy.analysis.indicators import TechnicalIndicators

        atr_series = TechnicalIndicators.calculate_atr(
            df["high"], df["low"], df["close"], period=self.atr_period
        )

        # 检测所有形状确认的 trough（用 Low 进行 TR2 形态识别）
        troughs_low = self.trough_detector.detect_troughs(df)

        # 额外用 Close 检测一次（供 SupportAnalyzer 使用，避免重复计算）
        trough_detector_close = TroughDetector(
            window=self.support_trough_window,
            min_side_bars=self.support_trough_min_side_bars,
            measure="close"
        )
        troughs_close = trough_detector_close.detect_troughs(df)

        if not troughs_low:
            return signals

        # 按索引排序确保时间顺序
        troughs = sorted(troughs_low, key=lambda t: t.index)

        # 已生成信号的 TR1 索引，避免重复
        processed_tr1_indices = set()

        # 遍历每个 trough 作为潜在的 TR2
        for trough in troughs:
            # 计算该 trough 时刻的 126 日最低点
            tr1_idx, tr1_price, tr1_date = self._find_126d_low(df, trough.index)

            # 如果已经为这个 TR1 生成过信号，跳过
            if tr1_idx in processed_tr1_indices:
                continue

            # 检查 TR1 是否在 TR2 的检测窗口外
            if tr1_idx >= trough.window_start:
                continue  # TR1 在窗口内，不是有效双底

            # 检查 max_gap_days 约束
            gap_days = trough.index - tr1_idx
            if gap_days > self.max_gap_days:
                processed_tr1_indices.add(tr1_idx)
                continue

            # 获取 TR1 位置的 ATR（作为波动率基准）
            atr_at_tr1 = atr_series.iloc[tr1_idx]
            if pd.isna(atr_at_tr1) or atr_at_tr1 <= 0:
                processed_tr1_indices.add(tr1_idx)
                continue

            # 情况 3：当前 trough 价格 <= TR1 -> TR2 必须高于 TR1
            # 使用 tr2_modes 获取 TR2 的比较价格
            tr2_price = self._get_tr2_price(df, trough.index)
            if tr2_price <= tr1_price:
                processed_tr1_indices.add(tr1_idx)
                continue

            # 计算区间最高价（供两个验证方法共用）
            price_col = self.bounce_high_measure  # "close" 或 "high"
            bounce_high = df[price_col].iloc[tr1_idx : trough.index + 1].max()

            # 验证 TR1 反弹幅度（基于 ATR 倍数）
            is_valid_bounce, bounce_pct, bounce_atr_ratio = self._validate_tr1_bounce(
                bounce_high, tr1_price, atr_at_tr1
            )
            if not is_valid_bounce:
                processed_tr1_indices.add(tr1_idx)
                continue

            # 验证 TR2 深度（基于 ATR 倍数）
            is_valid_depth, depth_pct, depth_atr_ratio = self._validate_tr2_depth(
                bounce_high, tr2_price, atr_at_tr1
            )
            if not is_valid_depth:
                continue

            # 检查 min_recovery_atr 约束（可选）
            if self.min_recovery_atr > 0:
                if tr1_price <= 0:
                    print(f"[Warning] {symbol}: tr1_price={tr1_price} <= 0, skipping")
                    self.skipped_symbols.append(symbol)
                    return signals
                recovery_amount = tr2_price - tr1_price
                recovery_atr_ratio = recovery_amount / atr_at_tr1
                if recovery_atr_ratio < self.min_recovery_atr:
                    continue

            # 所有约束通过，生成信号
            processed_tr1_indices.add(tr1_idx)

            # 计算恢复百分比和恢复 ATR 倍数
            if tr1_price <= 0:
                print(f"[Warning] {symbol}: tr1_price={tr1_price} <= 0, skipping")
                self.skipped_symbols.append(symbol)
                return signals

            recovery_pct = round((tr2_price - tr1_price) / tr1_price * 100, 2)
            recovery_atr_ratio = (tr2_price - tr1_price) / atr_at_tr1

            signal_price = float(df["close"].iloc[trough.index])

            signal = AbsoluteSignal(
                symbol=symbol,
                date=trough.date,
                signal_type=SignalType.DOUBLE_TROUGH,
                price=signal_price,
                details={
                    "trough1_date": str(tr1_date),
                    "trough1_price": round(float(tr1_price), 2),
                    "trough1_index": tr1_idx,
                    "trough2_date": str(trough.date),
                    "trough2_price": round(float(tr2_price), 2),
                    "trough2_index": trough.index,
                    "trough2_window_end": trough.window_end,  # TR2 确认日期索引
                    "trough2_window_end_date": str(df.index[trough.window_end].date()) if trough.window_end is not None else None,
                    "recovery_pct": float(recovery_pct),
                    "bounce_pct": round(float(bounce_pct), 2),
                    "depth_pct": round(float(depth_pct), 2),
                    "gap_days": gap_days,
                    "atr_at_tr1": round(float(atr_at_tr1), 4),
                    "bounce_atr": round(float(bounce_atr_ratio), 2),
                    "depth_atr": round(float(depth_atr_ratio), 2),
                    "recovery_atr": round(float(recovery_atr_ratio), 2),
                    # tr_num = 1 表示 TR2 是第一次支撑确认
                    # 后续支撑由 SupportAnalyzer 累加
                    "tr_num": 1,
                    # 支撑状态（由 SupportAnalyzer 填充）
                    "support_status": None,
                    # 缓存已检测的 trough 列表，供 SupportAnalyzer 复用
                    # troughs_low: 用于 TR2 形态识别（保持向后兼容）
                    "troughs": [
                        {"index": t.index, "price": t.price, "date": str(t.date)}
                        for t in troughs_low
                    ],
                    # troughs_close: 用于支撑测试（市场共识确认）
                    "troughs_close": [
                        {"index": t.index, "price": t.price, "date": str(t.date)}
                        for t in troughs_close
                    ],
                },
            )
            signals.append(signal)

        return signals
