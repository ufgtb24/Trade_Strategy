"""
突破检测模块（增量式架构）

基于增量式算法重构，核心特性：
1. 增量添加价格数据，维护活跃峰值列表
2. 支持价格相近的峰值共存（形成阻力区）
3. 一次突破可能突破多个峰值
4. 支持持久化缓存（可选）
"""

import pandas as pd
import numpy as np
import pickle
import json
from pathlib import Path
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Tuple


@dataclass
class Peak:
    """
    峰值数据结构
    """
    index: int                      # 在价格序列中的索引
    price: float                    # 峰值价格
    date: date                      # 峰值日期

    # Peak 唯一标识符
    id: Optional[int] = None        # 峰值唯一ID（用于追踪）

    # 峰值特征
    volume_peak: float = 0.0             # 峰值放量倍数
    candle_change_pct: float = 0.0       # K线涨跌幅
    left_suppression_days: int = 0       # 左侧压制天数
    right_suppression_days: int = 0      # 右侧压制天数（突破时更新）
    relative_height: float = 0.0         # 相对高度
    original_price: Optional[float] = None  # 被 elevate 前的原始峰值价格

    # 该 peak 作为 killer 时令哪些旧 peak 退场（peak→peak supersede）
    superseded_peak_ids: List[int] = field(default_factory=list)


@dataclass
class BreakoutInfo:
    """
    突破信息（简化版，由增量检测直接返回）

    一次突破可能突破多个峰值
    """
    current_index: int              # 突破点索引
    current_price: float            # 突破价格
    current_date: date              # 突破日期

    # 被突破的峰值列表（关键：支持多个）
    broken_peaks: List[Peak]        # 被突破的所有峰值
    superseded_peaks: List[Peak] = field(default_factory=list)  # 被真正移除的峰值（突破幅度 > supersede_threshold）

    @property
    def num_peaks_broken(self) -> int:
        """突破的峰值数量"""
        return len(self.broken_peaks)

    @property
    def broken_peak_ids(self) -> List[int]:
        """被突破的峰值ID列表"""
        return [p.id for p in self.broken_peaks if p.id is not None]

    @property
    def superseded_peak_ids(self) -> List[int]:
        """被真正移除的峰值ID列表"""
        return [p.id for p in self.superseded_peaks if p.id is not None]

    @property
    def highest_peak_broken(self) -> Peak:
        """被突破的最高峰值"""
        return max(self.broken_peaks, key=lambda p: p.price)

    @property
    def lowest_peak_broken(self) -> Peak:
        """被突破的最低峰值"""
        return min(self.broken_peaks, key=lambda p: p.price)

    @property
    def peak_price_range(self) -> float:
        """被突破峰值的价格范围"""
        if len(self.broken_peaks) == 0:
            return 0.0
        prices = [p.price for p in self.broken_peaks]
        return max(prices) - min(prices)

    @property
    def avg_peak_price(self) -> float:
        """被突破峰值的平均价格"""
        if len(self.broken_peaks) == 0:
            return 0.0
        return sum(p.price for p in self.broken_peaks) / len(self.broken_peaks)


@dataclass
class BreakoutRecord:
    """
    突破历史记录（轻量级，仅用于连续突破判断）

    用于追踪近期突破，计算 Momentum 评分
    """
    index: int          # 突破点索引
    date: date          # 突破日期
    price: float        # 突破价格
    num_peaks: int      # 突破的峰值数量


@dataclass
class Breakout:
    """
    完整的突破对象（包含丰富特征）

    由FeatureCalculator从BreakoutInfo计算得到
    """
    symbol: str
    date: date
    price: float
    index: int

    # 被突破的峰值列表
    broken_peaks: List[Peak]

    # 突破特征
    breakout_type: str          # 'yang', 'yin', 'shadow'
    intraday_change_pct: float      # 日内涨幅（收盘 vs 开盘）
    gap_up_pct: float               # 跳空幅度（百分比）
    stability_score: float          # 稳定性分数
    volume: Optional[float] = None  # 放量倍数
    pbm: Optional[float] = None     # 突破前涨势强度 (PBM)

    # 近期 peak 凹陷深度（0 表示无近期 peak）
    # pk_mom = 1 + log(1 + D_atr)，其中 D_atr = (peak - trough) / ATR
    pk_mom: Optional[float] = None

    # 年化波动率（基于 252 天日收益率标准差）
    annual_volatility: Optional[float] = None

    # ATR 相关字段（可选功能）
    atr_value: float = 0.0               # ATR 值
    atr_normalized_height: float = 0.0   # 突破幅度 / ATR

    # 质量评分（由QualityScorer计算）
    quality_score: Optional[float] = None

    # 回测标签（由FeatureCalculator计算）
    # 格式：{"label_5_20": 0.15, "label_3_10": None}
    labels: Dict[str, Optional[float]] = field(default_factory=dict)

    # 连续突破信息（由 FeatureCalculator 填充）
    streak: int = 1                             # 近期突破次数（至少包括自己）
    drought: Optional[int] = None               # 距上次突破的交易日间隔，None=首次突破

    # 突破日强度比率：max(intraday/daily_vol, gap/daily_vol)，σ 单位
    day_str: Optional[float] = None

    # 超涨比率：gain_5d / five_day_vol，σ 单位
    overshoot: Optional[float] = None

    # 阻力属性因子（从 broken_peaks 聚合，由 FeatureCalculator 计算）
    age: int = 0                        # 最老被突破峰值的年龄（天数）
    test: int = 0                       # 最大阻力簇峰值数（贪心聚类 3%）
    peak_vol: float = 0.0              # 峰值最大放量倍数
    height: float = 0.0                # 峰值最大相对高度

    # 突破前环境因子
    pre_vol: Optional[float] = None    # 突破前 window 天内最大放量倍数（逐日 63 天基线）
    ma_pos: Optional[float] = None     # 突破日收盘价相对 N 日均线的溢价率（中期动量积累）
    dd_recov: float = 0.0              # 回撤恢复度（drawdown * recovery * (1-recovery)^(b-1)，底部启动信号）
    ma_curve: float = 0.0              # MA曲率（均线二阶导数归一化值，趋势拐点信号）

    # 被真正移除的峰值（突破幅度 > supersede_threshold）
    superseded_peaks: List[Peak] = field(default_factory=list)

    @property
    def num_peaks_broken(self) -> int:
        return len(self.broken_peaks)

    @property
    def broken_peak_ids(self) -> List[int]:
        """被突破的峰值ID列表"""
        return [p.id for p in self.broken_peaks if p.id is not None]

    @property
    def superseded_peak_ids(self) -> List[int]:
        """被真正移除的峰值ID列表"""
        return [p.id for p in self.superseded_peaks if p.id is not None]

    @property
    def highest_peak_broken(self) -> Peak:
        return max(self.broken_peaks, key=lambda p: p.price)

    @property
    def peak_price_range(self) -> float:
        if len(self.broken_peaks) == 0:
            return 0.0
        prices = [p.price for p in self.broken_peaks]
        return max(prices) - min(prices)


class BreakoutDetector:
    """
    突破检测器（增量式架构）

    核心特性：
    - 增量添加价格数据
    - 维护活跃峰值列表
    - 支持峰值共存（阻力区）
    - 可选持久化缓存
    """

    def __init__(self,
                 symbol: str,
                 total_window: int = 10,
                 min_side_bars: int = 2,
                 min_relative_height: float = 0.05,
                 exceed_threshold: float = 0.005,
                 peak_supersede_threshold: float = 0.03,
                 peak_measure: str = 'body_top',
                 breakout_mode: str = 'body_top',
                 streak_window: int = 20,
                 use_cache: bool = False,
                 cache_dir: str = "./cache"):
        """
        初始化突破检测器

        Args:
            symbol: 股票代码
            total_window: 总窗口大小（左右两侧合计需超过的K线数）
            min_side_bars: 单侧最少K线数（左右各至少超过此数量）
            min_relative_height: 最小相对高度（峰值相对窗口内最低 low 的幅度下限）
            exceed_threshold: 突破确认阈值（默认0.5%）
            peak_supersede_threshold: 峰值覆盖阈值（默认3%）
                - 新峰值超过旧峰值 < 3% → 两者共存（形成阻力区）
                - 新峰值超过旧峰值 > 3% → 删除旧峰值（已被明显超越）
            peak_measure: 峰值价格定义方式（'high', 'close', 'body_top'）
                - 'high': 使用最高价（原始方式）
                - 'close': 使用收盘价
                - 'body_top': 使用 max(open, close)，实体上界（推荐）
            breakout_mode: 突破确认模式
                - 'body_top': 实体上界 max(open, close) 突破时确认（默认）
                - 'close': 收盘价突破时确认
                - 'high': 最高价突破时确认
            streak_window: 连续突破统计窗口（默认20个交易日）
            use_cache: 是否使用持久化缓存（实时监控=True，回测=False）
            cache_dir: 缓存目录
        """
        # 参数验证
        if min_side_bars * 2 > total_window:
            raise ValueError(
                f"min_side_bars ({min_side_bars}) * 2 > total_window ({total_window}), "
                "无法满足窗口条件"
            )

        self.symbol = symbol
        self.total_window = total_window
        self.min_side_bars = min_side_bars
        self.min_relative_height = min_relative_height
        self.exceed_threshold = exceed_threshold
        self.peak_supersede_threshold = peak_supersede_threshold
        self.peak_measure = peak_measure
        self.breakout_mode = breakout_mode
        self.streak_window = streak_window
        self.use_cache = use_cache
        self.cache_dir = Path(cache_dir)

        # 核心状态
        self.prices = []           # 价格历史（close）
        self.highs = []            # 最高价历史
        self.lows = []             # 最低价历史
        self.opens = []            # 开盘价历史
        self.volumes = []          # 成交量历史
        self.dates = []            # 日期历史
        self.active_peaks = []     # 活跃峰值列表: [Peak对象, ...]
        self.superseded_by_new_peak: List[Peak] = []  # 被新峰值取代的旧峰值
        # 历史上创建过的所有峰值（不过滤、不去重）。下游消费者（scanner JSON
        # 输出、dev UI 灰色 SU_PK 绘制）应以此为权威来源；active_peaks /
        # superseded_by_new_peak / breakout.broken_peaks 都是它的子集，且任一
        # 子集都可能因 BO 价格过滤而漏 peak。
        self.all_peaks: List[Peak] = []

        self.peak_id_counter = 0   # Peak ID 计数器（用于生成唯一ID）
        self.last_updated = None

        # 有效检测范围（用于排除缓冲区数据）
        self._valid_start_index = 0  # 有效范围起始索引（ATR 缓冲区结束后）

        # 突破历史（用于连续突破加成）
        self.breakout_history: List[BreakoutRecord] = []

        # 如果启用缓存，尝试加载
        if use_cache:
            self.cache_dir.mkdir(exist_ok=True)
            self._load_cache()

    def add_bar(self,
                row: pd.Series,
                auto_save: bool = True,
                enable_detection: bool = True) -> Optional[BreakoutInfo]:
        """
        添加新的K线数据

        Args:
            row: K线数据（包含open, high, low, close, volume）
            auto_save: 是否自动保存缓存
            enable_detection: 是否启用峰值/突破检测（缓冲区数据设为 False）

        Returns:
            如果有突破，返回BreakoutInfo；否则返回None
        """
        current_idx = len(self.prices)

        # 提取数据
        price = row['close']
        high = row['high']
        low = row['low']
        open_price = row['open']
        volume = row['volume']
        bar_date = row.name.date() if isinstance(row.name, pd.Timestamp) else row.name

        # 添加到历史
        self.prices.append(price)
        self.highs.append(high)
        self.lows.append(low)
        self.opens.append(open_price)
        self.volumes.append(volume)
        self.dates.append(bar_date)

        # 如果禁用检测（缓冲区数据），直接返回
        if not enable_detection:
            return None

        # 1. 先进行峰值检测（在固定窗口内）
        #    峰值不会在窗口的最后 min_side_bars 个位置，
        #    所以峰值会在突破检测之前被添加
        if current_idx >= self.total_window:
            self._detect_peak_in_window(current_idx)

        # 2. 再检查突破（使用high价格）
        breakout_info = self._check_breakouts(current_idx, bar_date)

        # 3. 保存缓存
        if self.use_cache and auto_save:
            if len(self.prices) % 10 == 0 or breakout_info:
                self._save_cache()

        return breakout_info

    def batch_add_bars(self,
                      df: pd.DataFrame,
                      return_breakouts: bool = True,
                      valid_start_index: int = 0,
                      valid_end_index: int = None) -> List[BreakoutInfo]:
        """
        批量添加K线数据

        用于初始化或历史回测

        Args:
            df: OHLCV数据
            return_breakouts: 是否返回突破列表
            valid_start_index: 有效检测范围起始索引（之前的数据仅用于 ATR 等指标计算）
            valid_end_index: 有效检测范围结束索引（之后的数据为 Label 缓冲区，不检测）

        Returns:
            所有突破信息
        """
        all_breakouts = []

        # 设置有效范围（供 _detect_peak_in_window 使用）
        self._valid_start_index = valid_start_index
        if valid_end_index is None:
            valid_end_index = len(df)

        for i in range(len(df)):
            row = df.iloc[i]
            # 只在有效范围内启用检测
            enable_detection = valid_start_index <= i < valid_end_index
            breakout_info = self.add_bar(row, auto_save=False, enable_detection=enable_detection)

            if return_breakouts and breakout_info:
                all_breakouts.append(breakout_info)

        if self.use_cache:
            self._save_cache()

        return all_breakouts

    def _get_measure_price(self, idx: int, measure: str = None) -> float:
        """
        获取指定度量的价格

        Args:
            idx: K线索引
            measure: 度量类型 ('high', 'close', 'body_top')，默认使用 self.peak_measure

        Returns:
            指定度量的价格值
        """
        if measure is None:
            measure = self.peak_measure

        if measure == 'high':
            return self.highs[idx]
        elif measure == 'close':
            return self.prices[idx]
        elif measure == 'body_top':
            return max(self.opens[idx], self.prices[idx])
        else:
            raise ValueError(f"Unknown measure: {measure}")

    def _get_window_measures(self, start: int, end: int, measure: str = None) -> list:
        """
        获取窗口内的度量价格序列

        Args:
            start: 窗口起始索引
            end: 窗口结束索引（不包含）
            measure: 度量类型，默认使用 self.peak_measure

        Returns:
            窗口内的价格列表
        """
        return [self._get_measure_price(i, measure) for i in range(start, end)]

    def _detect_peak_in_window(self, current_idx: int):
        """
        在固定窗口内检测峰值

        窗口：[current_idx - total_window, current_idx - 1]，共 total_window 个元素

        峰值判定条件（4点必须都满足）：
        1. 峰值索引 >= _valid_start_index（排除 ATR 缓冲区内的峰值）
        2. 在窗口内是最高点（使用 peak_measure 定义的价格）
        3. 该点的局部索引不在前 min_side_bars 或后 min_side_bars 个位置
        4. (peak_measure - window_min_low) / window_min_low >= min_relative_height

        支持价格相近的峰值共存，形成阻力区
        """
        window_start = current_idx - self.total_window

        if window_start < 0:
            return

        # 获取窗口内的 measure 价格序列
        window_measures = self._get_window_measures(window_start, current_idx)
        window_size = len(window_measures)

        # 条件2：找到窗口内的最高 measure 点
        max_measure = max(window_measures)
        max_local_idx = window_measures.index(max_measure)

        # 条件3：检查是否在有效范围内
        # 前 min_side_bars 个位置：局部索引 [0, min_side_bars - 1]
        # 后 min_side_bars 个位置：局部索引 [window_size - min_side_bars, window_size - 1]
        if max_local_idx < self.min_side_bars:
            return  # 在窗口前部，不是有效峰值
        if max_local_idx >= window_size - self.min_side_bars:
            return  # 在窗口后部，不是有效峰值

        # 计算全局索引
        peak_global_idx = window_start + max_local_idx

        # 条件1：检查峰值是否在有效检测范围内（排除 ATR 缓冲区）
        if peak_global_idx < self._valid_start_index:
            return  # 峰值在 ATR 缓冲区内，不检测

        # 检查是否已经添加过这个峰值（避免重复添加）
        for existing_peak in self.active_peaks:
            if existing_peak.index == peak_global_idx:
                return

        # 条件3：检查相对高度 (measure vs low)
        window_lows = self.lows[window_start:current_idx]
        window_min_low = min(window_lows)
        relative_height = (max_measure - window_min_low) / window_min_low if window_min_low > 0 else 0
        if relative_height < self.min_relative_height:
            return  # 相对高度不足

        # 所有条件满足，创建峰值
        peak = self._create_peak(peak_global_idx, max_measure, self.dates[peak_global_idx], current_idx)

        # 决定保留哪些旧峰值（支持共存）
        remaining_peaks = []
        for old_peak in self.active_peaks:
            exceed_pct = (max_measure - old_peak.price) / old_peak.price
            if exceed_pct < self.peak_supersede_threshold:
                remaining_peaks.append(old_peak)
            else:
                # 被新峰值明显超越，记录以便UI显示
                self.superseded_by_new_peak.append(old_peak)
                # killer→victim 关系：新 peak 显式记录被它干掉的 peak ids
                if old_peak.id is not None:
                    peak.superseded_peak_ids.append(old_peak.id)

        # 添加新峰值
        self.active_peaks = remaining_peaks
        self.active_peaks.append(peak)

    def _create_peak(self, idx: int, price: float, date_val: date, current_idx: int) -> Peak:
        """
        创建Peak对象并计算质量特征

        Args:
            idx: 峰值的全局索引
            price: 峰值价格
            date_val: 峰值日期
            current_idx: 当前处理到的位置（用于确定右侧边界）
        """
        # 分配唯一ID
        peak_id = self.peak_id_counter
        self.peak_id_counter += 1

        # 计算放量倍数
        window_start = max(0, idx - 63)
        avg_volume = np.mean(self.volumes[window_start:idx]) if idx > window_start else 1.0
        vol_ratio = self.volumes[idx] / avg_volume if avg_volume > 0 else 1.0

        # 计算K线涨跌幅
        candle_change_pct = (self.prices[idx] - self.opens[idx]) / self.opens[idx] if self.opens[idx] > 0 else 0.0

        # 计算左侧压制天数
        left_suppression = 0
        for i in range(idx - 1, max(0, idx - 60), -1):
            if self.highs[i] < price:
                left_suppression += 1
            else:
                break

        # 右侧压制天数暂时为0（突破时会更新）
        right_suppression = 0

        # 计算相对高度（使用对称窗口，反映局部突出程度）
        # 避免长窗口跨越其他峰值导致 relative_height 被稀释
        side_bars = self.total_window // 2  # 与检测窗口一致（默认10）
        left_start = max(0, idx - side_bars)
        right_end = min(current_idx, idx + side_bars + 1)  # 右边界不超过当前处理位置
        window_low = min(self.lows[left_start:right_end])
        relative_height = (price - window_low) / window_low if window_low > 0 else 0.0

        peak = Peak(
            index=idx,
            price=price,
            date=date_val,
            id=peak_id,
            volume_peak=vol_ratio,
            candle_change_pct=candle_change_pct,
            left_suppression_days=left_suppression,
            right_suppression_days=right_suppression,
            relative_height=relative_height
        )
        self.all_peaks.append(peak)
        return peak

    def _check_breakouts(self,
                        current_idx: int,
                        current_date: date) -> Optional[BreakoutInfo]:
        """
        检查突破

        采用双阈值设计：
        - exceed_threshold (0.5%): 用于突破检测（敏感）
        - peak_supersede_threshold (3%): 用于峰值移除（保守）

        per-factor gate 架构：突破判定是纯局部事实（仅依赖 active_peaks 与当前 bar
        的价格），与因子 lookback 解耦。因子 lookback 不足由下游 _calculate_xxx
        各自自检返回 None（见 FeatureCalculator._has_buffer / _effective_buffer）。

        Returns:
            如果有突破，返回BreakoutInfo（包含所有被突破的峰值）
            如果没有突破，返回None
        """
        # 一次性确定突破判定价格和 elevation 价格
        breakout_price = self._get_measure_price(current_idx, self.breakout_mode)
        elevation_price = self._get_measure_price(current_idx, self.peak_measure)

        broken_peaks = []
        superseded_peaks = []
        remaining_peaks = []

        for peak in self.active_peaks:
            exceed_threshold_price = peak.price * (1 + self.exceed_threshold)
            # supersede 锚定原始价：peak.price 在小幅突破后会被 elevation 抬升，
            # 若仍以其为基准会让缓步上行的累计涨幅永远进不到 supersede 分支
            supersede_base_price = peak.original_price if peak.original_price is not None else peak.price
            supersede_threshold_price = supersede_base_price * (1 + self.peak_supersede_threshold)

            if breakout_price > exceed_threshold_price:
                # 突破确认
                peak.right_suppression_days = current_idx - peak.index - 1
                broken_peaks.append(peak)

                if breakout_price <= supersede_threshold_price:
                    # 突破幅度 <= 3%：保留峰值（突破巩固）
                    # 提升峰值有效价格到当前度量价格（阻力位上移）
                    if elevation_price > peak.price:
                        if peak.original_price is None:
                            peak.original_price = peak.price
                        peak.price = elevation_price
                    remaining_peaks.append(peak)
                else:
                    # 突破幅度 > 3%：真正移除峰值
                    superseded_peaks.append(peak)
            else:
                remaining_peaks.append(peak)

        self.active_peaks = remaining_peaks

        if broken_peaks:
            self.breakout_history.append(BreakoutRecord(
                index=current_idx,
                date=current_date,
                price=breakout_price,
                num_peaks=len(broken_peaks)
            ))

            return BreakoutInfo(
                current_index=current_idx,
                current_price=breakout_price,
                current_date=current_date,
                broken_peaks=broken_peaks,
                superseded_peaks=superseded_peaks
            )

        return None

    def get_recent_breakout_count(self, current_idx: int, debug: bool = False) -> int:
        """
        获取时间窗口内的突破次数（包括当前突破）

        Args:
            current_idx: 当前K线索引
            debug: 是否输出调试信息

        Returns:
            近期突破次数
        """
        count = sum(
            1 for h in self.breakout_history
            if h.index <= current_idx and current_idx - h.index <= self.streak_window
        )
        result = max(count, 1)  # 至少返回1（包括自己）

        if debug:
            print(f"[DEBUG] get_recent_breakout_count: current_idx={current_idx}, "
                  f"streak_window={self.streak_window}, "
                  f"breakout_history_len={len(self.breakout_history)}, "
                  f"history_indices={[h.index for h in self.breakout_history]}, "
                  f"result={result}")

        return result

    def get_days_since_last_breakout(self, current_idx: int) -> Optional[int]:
        """
        距上次突破的交易日间隔，None=首次突破

        用 < current_idx 排除自身（当前突破已在 _check_breakouts 追加到 history）

        Args:
            current_idx: 当前K线索引

        Returns:
            交易日间隔，None 表示首次突破
        """
        prev = [h for h in self.breakout_history if h.index < current_idx]
        if not prev:
            return None
        return current_idx - max(prev, key=lambda h: h.index).index

    def _save_cache(self):
        """保存缓存到磁盘"""
        if not self.use_cache:
            return

        try:
            cache_data = {
                'symbol': self.symbol,
                'prices': self.prices,
                'highs': self.highs,
                'lows': self.lows,
                'opens': self.opens,
                'volumes': self.volumes,
                'dates': [d.isoformat() for d in self.dates],
                'active_peaks': [
                    {
                        'index': p.index,
                        'price': p.price,
                        'date': p.date.isoformat(),
                        'id': p.id,
                        'volume_peak': p.volume_peak,
                        'candle_change_pct': p.candle_change_pct,
                        'left_suppression_days': p.left_suppression_days,
                        'right_suppression_days': p.right_suppression_days,
                        'relative_height': p.relative_height,
                        'original_price': p.original_price
                    }
                    for p in self.active_peaks
                ],
                'peak_id_counter': self.peak_id_counter,
                'total_window': self.total_window,
                'min_side_bars': self.min_side_bars,
                'min_relative_height': self.min_relative_height,
                'exceed_threshold': self.exceed_threshold,
                'peak_supersede_threshold': self.peak_supersede_threshold,
                'peak_measure': self.peak_measure,
                'breakout_mode': self.breakout_mode,
                'streak_window': self.streak_window,
                'breakout_history': [
                    {
                        'index': h.index,
                        'date': h.date.isoformat(),
                        'price': h.price,
                        'num_peaks': h.num_peaks
                    }
                    for h in self.breakout_history
                ]
            }

            cache_path = self._get_cache_path()
            with open(cache_path, 'wb') as f:
                pickle.dump(cache_data, f)

            # 保存元数据
            metadata = {
                'symbol': self.symbol,
                'data_points': len(self.prices),
                'active_peaks_count': len(self.active_peaks),
                'last_date': self.dates[-1].isoformat() if self.dates else None
            }

            meta_path = self._get_metadata_path()
            with open(meta_path, 'w') as f:
                json.dump(metadata, f, indent=2)

        except Exception as e:
            print(f"✗ 保存缓存失败: {e}")

    def _load_cache(self):
        """从磁盘加载缓存"""
        cache_path = self._get_cache_path()

        if not cache_path.exists():
            return False

        try:
            with open(cache_path, 'rb') as f:
                cache_data = pickle.load(f)

            # 验证参数匹配
            if (cache_data.get('total_window') != self.total_window or
                cache_data.get('min_side_bars') != self.min_side_bars or
                cache_data.get('min_relative_height') != self.min_relative_height or
                cache_data.get('exceed_threshold') != self.exceed_threshold or
                cache_data.get('peak_supersede_threshold') != self.peak_supersede_threshold or
                cache_data.get('peak_measure') != self.peak_measure or
                cache_data.get('breakout_mode') != self.breakout_mode):
                print(f"⚠ 缓存参数不匹配，跳过加载")
                return False

            # 恢复状态
            self.prices = cache_data['prices']
            self.highs = cache_data['highs']
            self.lows = cache_data['lows']
            self.opens = cache_data['opens']
            self.volumes = cache_data['volumes']
            self.dates = [date.fromisoformat(d) for d in cache_data['dates']]

            # 恢复峰值
            self.active_peaks = [
                Peak(
                    index=p['index'],
                    price=p['price'],
                    date=date.fromisoformat(p['date']),
                    id=p.get('id'),  # 兼容旧缓存
                    volume_peak=p['volume_peak'],
                    candle_change_pct=p['candle_change_pct'],
                    left_suppression_days=p['left_suppression_days'],
                    right_suppression_days=p['right_suppression_days'],
                    relative_height=p['relative_height'],
                    original_price=p.get('original_price')
                )
                for p in cache_data['active_peaks']
            ]

            # 恢复 peak_id_counter（兼容旧缓存）
            self.peak_id_counter = cache_data.get('peak_id_counter', 0)

            # 恢复 breakout_history（兼容旧缓存）
            self.breakout_history = [
                BreakoutRecord(
                    index=h['index'],
                    date=date.fromisoformat(h['date']),
                    price=h['price'],
                    num_peaks=h['num_peaks']
                )
                for h in cache_data.get('breakout_history', [])
            ]

            print(f"✓ 缓存加载成功: {self.symbol}, {len(self.prices)}个数据点, "
                  f"{len(self.active_peaks)}个活跃峰值, {len(self.breakout_history)}个突破历史")
            return True

        except Exception as e:
            print(f"✗ 加载缓存失败: {e}")
            return False

    def _get_cache_path(self) -> Path:
        """获取缓存文件路径"""
        safe_symbol = self.symbol.replace('/', '_')
        # 使用 peak_measure 首字母和 breakout_mode 首字母生成唯一键
        pm = self.peak_measure[0] if self.peak_measure else 'b'
        bm = self.breakout_mode[0]
        return self.cache_dir / f"{safe_symbol}_tw{self.total_window}_ms{self.min_side_bars}_pm{pm}_bm{bm}.pkl"

    def _get_metadata_path(self) -> Path:
        """获取元数据文件路径"""
        safe_symbol = self.symbol.replace('/', '_')
        pm = self.peak_measure[0] if self.peak_measure else 'b'
        bm = self.breakout_mode[0]
        return self.cache_dir / f"{safe_symbol}_tw{self.total_window}_ms{self.min_side_bars}_pm{pm}_bm{bm}_meta.json"

    def clear_cache(self):
        """清除缓存文件"""
        try:
            cache_path = self._get_cache_path()
            meta_path = self._get_metadata_path()

            if cache_path.exists():
                cache_path.unlink()
            if meta_path.exists():
                meta_path.unlink()

            print(f"✓ 缓存已清除: {self.symbol}")
        except Exception as e:
            print(f"✗ 清除缓存失败: {e}")

    def get_status(self) -> dict:
        """获取状态信息"""
        return {
            'symbol': self.symbol,
            'total_bars': len(self.prices),
            'active_peaks': len(self.active_peaks),
            'last_date': self.dates[-1].isoformat() if self.dates else None,
            'cache_exists': self._get_cache_path().exists() if self.use_cache else False
        }
