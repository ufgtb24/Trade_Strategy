"""
突破检测模块（增量式架构）

基于增量式算法重构，核心特性：
1. 增量添加价格数据，维护活跃峰值列表
2. 支持价格相近的峰值共存（形成阻力区）
3. 一次突破可能突破多个峰值
4. 支持持久化缓存（可选）
5. 计算峰值质量特征
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
    峰值数据结构（增强版）

    包含质量评估特征
    """
    index: int                      # 在价格序列中的索引
    price: float                    # 峰值价格
    date: date                      # 峰值日期

    # Peak 唯一标识符
    id: Optional[int] = None        # 峰值唯一ID（用于追踪）

    # 质量特征
    volume_surge_ratio: float = 0.0      # 放量倍数
    candle_change_pct: float = 0.0       # K线涨跌幅
    left_suppression_days: int = 0       # 左侧压制天数
    right_suppression_days: int = 0      # 右侧压制天数（突破时更新）
    relative_height: float = 0.0         # 相对高度

    # 质量评分（由QualityScorer计算）
    quality_score: Optional[float] = None


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

    @property
    def num_peaks_broken(self) -> int:
        """突破的峰值数量"""
        return len(self.broken_peaks)

    @property
    def broken_peak_ids(self) -> List[int]:
        """被突破的峰值ID列表"""
        return [p.id for p in self.broken_peaks if p.id is not None]

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
class BreakthroughRecord:
    """
    突破历史记录（轻量级，仅用于连续突破判断）

    用于追踪近期突破，计算 Momentum 评分
    """
    index: int          # 突破点索引
    date: date          # 突破日期
    price: float        # 突破价格
    num_peaks: int      # 突破的峰值数量


@dataclass
class Breakthrough:
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
    breakthrough_type: str          # 'yang', 'yin', 'shadow'
    price_change_pct: float         # 突破日涨跌幅
    gap_up: bool                    # 是否跳空
    gap_up_pct: float               # 跳空幅度
    volume_surge_ratio: float       # 放量倍数
    continuity_days: int            # 连续上涨天数
    stability_score: float          # 稳定性分数

    # 质量评分（由QualityScorer计算）
    quality_score: Optional[float] = None

    # 回测标签（由FeatureCalculator计算）
    # 格式：{"label_5_20": 0.15, "label_3_10": None}
    labels: Dict[str, Optional[float]] = field(default_factory=dict)

    # 连续突破信息（由 FeatureCalculator 填充）
    recent_breakthrough_count: int = 1  # 近期突破次数（至少包括自己）

    @property
    def num_peaks_broken(self) -> int:
        return len(self.broken_peaks)

    @property
    def broken_peak_ids(self) -> List[int]:
        """被突破的峰值ID列表"""
        return [p.id for p in self.broken_peaks if p.id is not None]

    @property
    def highest_peak_broken(self) -> Peak:
        return max(self.broken_peaks, key=lambda p: p.price)

    @property
    def peak_price_range(self) -> float:
        if len(self.broken_peaks) == 0:
            return 0.0
        prices = [p.price for p in self.broken_peaks]
        return max(prices) - min(prices)


class BreakthroughDetector:
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
                 momentum_window: int = 20,
                 use_cache: bool = False,
                 cache_dir: str = "./cache"):
        """
        初始化突破检测器

        Args:
            symbol: 股票代码
            total_window: 总窗口大小（左右两侧合计需超过的K线数）
            min_side_bars: 单侧最少K线数（左右各至少超过此数量）
            min_relative_height: 最小相对高度（峰值相对窗口内最低点的幅度下限）
            exceed_threshold: 突破确认阈值（默认0.5%）
            peak_supersede_threshold: 峰值覆盖阈值（默认3%）
                - 新峰值超过旧峰值 < 3% → 两者共存（形成阻力区）
                - 新峰值超过旧峰值 > 3% → 删除旧峰值（已被明显超越）
            momentum_window: 连续突破统计窗口（默认20个交易日）
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
        self.momentum_window = momentum_window
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

        self.peak_id_counter = 0   # Peak ID 计数器（用于生成唯一ID）
        self.last_updated = None

        # 突破历史（用于连续突破加成）
        self.breakthrough_history: List[BreakthroughRecord] = []

        # 如果启用缓存，尝试加载
        if use_cache:
            self.cache_dir.mkdir(exist_ok=True)
            self._load_cache()

    def add_bar(self,
                row: pd.Series,
                auto_save: bool = True) -> Optional[BreakoutInfo]:
        """
        添加新的K线数据

        Args:
            row: K线数据（包含open, high, low, close, volume）
            auto_save: 是否自动保存缓存

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

        # 1. 先进行峰值检测（在固定窗口内）
        #    峰值不会在窗口的最后 min_side_bars 个位置，
        #    所以峰值会在突破检测之前被添加
        if current_idx >= self.total_window:
            self._detect_peak_in_window(current_idx)

        # 2. 再检查突破（使用high价格）
        breakout_info = self._check_breakouts(current_idx, high, bar_date)

        # 3. 保存缓存
        if self.use_cache and auto_save:
            if len(self.prices) % 10 == 0 or breakout_info:
                self._save_cache()

        return breakout_info

    def batch_add_bars(self,
                      df: pd.DataFrame,
                      return_breakouts: bool = True) -> List[BreakoutInfo]:
        """
        批量添加K线数据

        用于初始化或历史回测

        Args:
            df: OHLCV数据
            return_breakouts: 是否返回突破列表

        Returns:
            所有突破信息
        """
        all_breakouts = []

        for i in range(len(df)):
            row = df.iloc[i]
            breakout_info = self.add_bar(row, auto_save=False)

            if return_breakouts and breakout_info:
                all_breakouts.append(breakout_info)

        if self.use_cache:
            self._save_cache()

        return all_breakouts

    def _detect_peak_in_window(self, current_idx: int):
        """
        在固定窗口内检测峰值

        窗口：[current_idx - total_window, current_idx - 1]，共 total_window 个元素

        峰值判定条件（3点必须都满足）：
        1. 在窗口内是最高点
        2. 该点的局部索引不在前 min_side_bars 或后 min_side_bars 个位置
        3. (peak_high - window_min_low) / window_min_low >= min_relative_height

        支持价格相近的峰值共存，形成阻力区
        """
        window_start = current_idx - self.total_window

        if window_start < 0:
            return

        # 窗口 [window_start, current_idx)，包含 total_window 个元素，不含 current_idx
        window_highs = self.highs[window_start:current_idx]
        window_size = len(window_highs)  # = total_window

        # 条件1：找到窗口内的最高点
        max_high = max(window_highs)
        max_local_idx = window_highs.index(max_high)

        # 条件2：检查是否在有效范围内
        # 前 min_side_bars 个位置：局部索引 [0, min_side_bars - 1]
        # 后 min_side_bars 个位置：局部索引 [window_size - min_side_bars, window_size - 1]
        if max_local_idx < self.min_side_bars:
            return  # 在窗口前部，不是有效峰值
        if max_local_idx >= window_size - self.min_side_bars:
            return  # 在窗口后部，不是有效峰值

        # 计算全局索引
        peak_global_idx = window_start + max_local_idx

        # 检查是否已经添加过这个峰值（避免重复添加）
        for existing_peak in self.active_peaks:
            if existing_peak.index == peak_global_idx:
                return

        # 条件3：检查相对高度
        window_lows = self.lows[window_start:current_idx]
        window_min_low = min(window_lows)
        relative_height = (max_high - window_min_low) / window_min_low if window_min_low > 0 else 0
        if relative_height < self.min_relative_height:
            return  # 相对高度不足

        # 所有条件满足，创建峰值
        peak = self._create_peak(peak_global_idx, max_high, self.dates[peak_global_idx], current_idx)

        # 决定保留哪些旧峰值（支持共存）
        remaining_peaks = []
        for old_peak in self.active_peaks:
            if old_peak.price > max_high:
                # 旧峰值更高 → 始终保留
                remaining_peaks.append(old_peak)
            else:
                # 新峰值更高，检查价格差距
                exceed_pct = (max_high - old_peak.price) / old_peak.price
                if exceed_pct < self.peak_supersede_threshold:
                    # 差距小于阈值 → 保留（形成阻力区）
                    remaining_peaks.append(old_peak)
                # else: 差距大于阈值 → 删除（已被明显超越）

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
        volume_surge_ratio = self.volumes[idx] / avg_volume if avg_volume > 0 else 1.0

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

        return Peak(
            index=idx,
            price=price,
            date=date_val,
            id=peak_id,
            volume_surge_ratio=volume_surge_ratio,
            candle_change_pct=candle_change_pct,
            left_suppression_days=left_suppression,
            right_suppression_days=right_suppression,
            relative_height=relative_height
        )

    def _check_breakouts(self,
                        current_idx: int,
                        current_high: float,
                        current_date: date) -> Optional[BreakoutInfo]:
        """
        检查突破

        采用双阈值设计：
        - exceed_threshold (0.5%): 用于突破检测（敏感）
        - peak_supersede_threshold (3%): 用于峰值移除（保守）

        这样设计的目的：
        - 突破幅度在 0.5%-3% 之间时，记录突破但保留峰值
        - 保留的峰值可以在后续突破中再次被突破（突破巩固）
        - 多个价格接近的峰值可以在同一次突破中被同时突破

        Returns:
            如果有突破，返回BreakoutInfo（包含所有被突破的峰值）
            如果没有突破，返回None
        """
        broken_peaks = []
        remaining_peaks = []

        for peak in self.active_peaks:
            exceed_threshold_price = peak.price * (1 + self.exceed_threshold)
            supersede_threshold_price = peak.price * (1 + self.peak_supersede_threshold)

            if current_high > exceed_threshold_price:
                # 突破检测（敏感阈值 0.5%）
                peak.right_suppression_days = current_idx - peak.index - 1
                broken_peaks.append(peak)

                # 峰值移除判断（保守阈值 3%）
                if current_high <= supersede_threshold_price:
                    # 突破幅度 <= 3%：保留峰值，下次还能被突破（突破巩固）
                    remaining_peaks.append(peak)
                # else: 突破幅度 > 3%：真正移除峰值
            else:
                # 未突破，保留
                remaining_peaks.append(peak)

        # 更新活跃峰值列表
        self.active_peaks = remaining_peaks

        # 如果有突破，返回信息
        if broken_peaks:
            # 记录突破历史（用于连续突破加成）
            self.breakthrough_history.append(BreakthroughRecord(
                index=current_idx,
                date=current_date,
                price=current_high,
                num_peaks=len(broken_peaks)
            ))

            return BreakoutInfo(
                current_index=current_idx,
                current_price=current_high,
                current_date=current_date,
                broken_peaks=broken_peaks
            )

        return None

    def get_recent_breakthrough_count(self, current_idx: int) -> int:
        """
        获取时间窗口内的突破次数（包括当前突破）

        Args:
            current_idx: 当前K线索引

        Returns:
            近期突破次数
        """
        count = sum(
            1 for h in self.breakthrough_history
            if h.index <= current_idx and current_idx - h.index <= self.momentum_window
        )
        return max(count, 1)  # 至少返回1（包括自己）

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
                        'volume_surge_ratio': p.volume_surge_ratio,
                        'candle_change_pct': p.candle_change_pct,
                        'left_suppression_days': p.left_suppression_days,
                        'right_suppression_days': p.right_suppression_days,
                        'relative_height': p.relative_height,
                        'quality_score': p.quality_score
                    }
                    for p in self.active_peaks
                ],
                'peak_id_counter': self.peak_id_counter,
                'total_window': self.total_window,
                'min_side_bars': self.min_side_bars,
                'min_relative_height': self.min_relative_height,
                'exceed_threshold': self.exceed_threshold,
                'peak_supersede_threshold': self.peak_supersede_threshold,
                'momentum_window': self.momentum_window,
                'breakthrough_history': [
                    {
                        'index': h.index,
                        'date': h.date.isoformat(),
                        'price': h.price,
                        'num_peaks': h.num_peaks
                    }
                    for h in self.breakthrough_history
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
                cache_data.get('peak_supersede_threshold') != self.peak_supersede_threshold):
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
                    volume_surge_ratio=p['volume_surge_ratio'],
                    candle_change_pct=p['candle_change_pct'],
                    left_suppression_days=p['left_suppression_days'],
                    right_suppression_days=p['right_suppression_days'],
                    relative_height=p['relative_height'],
                    quality_score=p.get('quality_score')
                )
                for p in cache_data['active_peaks']
            ]

            # 恢复 peak_id_counter（兼容旧缓存）
            self.peak_id_counter = cache_data.get('peak_id_counter', 0)

            # 恢复 breakthrough_history（兼容旧缓存）
            self.breakthrough_history = [
                BreakthroughRecord(
                    index=h['index'],
                    date=date.fromisoformat(h['date']),
                    price=h['price'],
                    num_peaks=h['num_peaks']
                )
                for h in cache_data.get('breakthrough_history', [])
            ]

            print(f"✓ 缓存加载成功: {self.symbol}, {len(self.prices)}个数据点, "
                  f"{len(self.active_peaks)}个活跃峰值, {len(self.breakthrough_history)}个突破历史")
            return True

        except Exception as e:
            print(f"✗ 加载缓存失败: {e}")
            return False

    def _get_cache_path(self) -> Path:
        """获取缓存文件路径"""
        safe_symbol = self.symbol.replace('/', '_')
        return self.cache_dir / f"{safe_symbol}_tw{self.total_window}_ms{self.min_side_bars}.pkl"

    def _get_metadata_path(self) -> Path:
        """获取元数据文件路径"""
        safe_symbol = self.symbol.replace('/', '_')
        return self.cache_dir / f"{safe_symbol}_tw{self.total_window}_ms{self.min_side_bars}_meta.json"

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
