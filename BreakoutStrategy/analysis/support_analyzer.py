"""
支撑分析工具

分析 B/D 信号后的支撑状态。

B 信号：使用状态机模型（阻力转支撑）
    RISING → TESTING → CONFIRMED/BROKEN
                ↑           │
                └───────────┘

D 信号：使用 trough 计数方法
    统计信号后落在支撑区间内的 trough 数量

设计原则：
- B 信号：pk_num 回顾过去（突破了多少阻力）
- D 信号：tr_num 展望未来（累积了多少支撑）
"""

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import List, Optional, TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from BreakoutStrategy.signals.models import AbsoluteSignal


class SupportState(Enum):
    """支撑状态"""
    RISING = "rising"           # 价格上涨中，等待回调
    TESTING = "testing"         # 正在测试支撑
    CONFIRMED = "confirmed"     # 支撑成功确认
    BROKEN = "broken"           # 支撑失败


@dataclass
class SupportZone:
    """支撑区间"""
    lower: float        # 下界 = TR1（硬边界）或 anchor_price - tolerance（B 信号）
    upper: float        # 上界 = max(TR1, TR2) + tolerance（D 信号）
    anchor_price: float # 锚点价格（TR1 或前一日低点）
    tolerance: float    # 容差


@dataclass
class SupportTest:
    """支撑测试记录"""
    enter_date: date    # 进入支撑区间日期
    exit_date: date     # 离开支撑区间日期
    min_price: float    # 测试期间最低价
    success: bool       # 是否支撑成功


@dataclass
class SupportStatus:
    """支撑状态结果"""
    status: str                             # "rising" | "testing" | "confirmed" | "broken"
    support_zone: Optional[List[float]]     # [lower, upper]
    test_count: int = 0                     # 成功测试次数
    tests: List[dict] = field(default_factory=list)  # 测试记录列表
    max_pullback_pct: Optional[float] = None  # 最大回撤百分比
    last_test_date: Optional[str] = None    # 最后测试日期
    break_date: Optional[str] = None        # 支撑跌破日期


class SupportAnalyzer:
    """
    支撑分析器

    分析信号后的支撑状态：
    1. B 信号：状态机模型（阻力转支撑）
    2. D 信号：trough 计数方法（统计支撑区间内的 trough 数量）
    """

    def __init__(
        self,
        breakout_tolerance_pct: float = 5.0,
        trough_tolerance_pct: float = 5.0,
        max_lookforward_days: int = 90,
    ):
        """
        Args:
            breakout_tolerance_pct: Breakout 支撑缓冲带宽度（默认 5%）
            trough_tolerance_pct: Double Trough 支撑区上界扩展（默认 5%）
            max_lookforward_days: 最大向前分析天数（默认 90 天）
        """
        self.breakout_tolerance_pct = breakout_tolerance_pct
        self.trough_tolerance_pct = trough_tolerance_pct
        self.max_lookforward_days = max_lookforward_days

    def analyze_breakout_support(
        self, df: pd.DataFrame, signal: "AbsoluteSignal", scan_date_idx: int
    ) -> SupportStatus:
        """
        分析 B 信号后的支撑状态

        支撑位 = 信号前一日的最低价
        支撑区间 = [support_level - tolerance, support_level + tolerance * 0.5]

        Args:
            df: OHLCV 数据
            signal: B 信号
            scan_date_idx: 扫描日期索引（分析到此为止）

        Returns:
            支撑状态
        """
        # 找到信号日期在 df 中的索引
        signal_idx = self._find_signal_index(df, signal.date)
        if signal_idx is None or signal_idx < 1:
            return SupportStatus(status="rising", support_zone=None)

        # 支撑位 = 信号前一日的最低价
        support_level = float(df["low"].iloc[signal_idx - 1])
        tolerance = support_level * (self.breakout_tolerance_pct / 100)

        zone = SupportZone(
            lower=support_level - tolerance,
            upper=support_level + tolerance * 0.5,
            anchor_price=support_level,
            tolerance=tolerance,
        )

        return self._run_state_machine(df, signal_idx, scan_date_idx, zone, signal.price)

    def analyze_double_trough_support(
        self, df: pd.DataFrame, signal: "AbsoluteSignal", scan_date_idx: int
    ) -> tuple[int, SupportStatus]:
        """
        分析 D 信号后的支撑状态（trough 计数方法）

        支撑区间锚定 TR2（确认价格）：
        - lower = TR2 - tolerance * 0.5（允许轻微跌破）
        - upper = TR2 + tolerance

        跌破检测：trough.close < zone.lower
        统计信号后落在支撑区间内的 trough 数量（排除 TR2 本身）。

        Args:
            df: OHLCV 数据
            signal: D 信号
            scan_date_idx: 扫描日期索引

        Returns:
            (tr_num, support_status) - tr_num = 1 + 区间内 trough 数量
        """
        details = signal.details
        tr1_price = details.get("trough1_price", 0)
        tr2_price = details.get("trough2_price", 0)
        tr2_idx = details.get("trough2_idx")
        tr2_window_end = details.get("trough2_window_end")

        if tr1_price <= 0:
            return 1, SupportStatus(status="rising", support_zone=None)

        # 找到信号日期在 df 中的索引
        signal_idx = self._find_signal_index(df, signal.date)
        if signal_idx is None:
            return 1, SupportStatus(status="rising", support_zone=None)

        # 定义支撑区间（锚定 TR2）
        tolerance = tr2_price * (self.trough_tolerance_pct / 100)
        zone = SupportZone(
            lower=tr2_price - tolerance * 0.5,  # 下限 = TR2 - 容差的一半
            upper=tr2_price + tolerance,         # 上限 = TR2 + 容差
            anchor_price=tr2_price,              # 锚点改为 TR2
            tolerance=tolerance,
        )

        # 分析范围：信号后到扫描日期
        end_idx = min(scan_date_idx + 1, signal_idx + self.max_lookforward_days + 1, len(df))

        # TR2 在 window_end 日被确认，支撑测试从 window_end + 1 开始
        # 避免将 TR2 确认窗口内的 trough 误判为支撑测试
        support_start_idx = tr2_window_end if tr2_window_end is not None else signal_idx

        # 优先从 details 读取 Close 检测的 troughs（零重复计算）
        cached_troughs_close = details.get("troughs_close")
        if cached_troughs_close:
            # 重建 Trough 对象
            from datetime import datetime
            from BreakoutStrategy.signals.detectors.trough import Trough
            all_troughs = [
                Trough(
                    index=t["index"],
                    price=t["price"],
                    date=datetime.strptime(t["date"], "%Y-%m-%d").date(),
                )
                for t in cached_troughs_close
                if t["index"] < end_idx  # 仅保留分析范围内的 trough
            ]
        else:
            # 回退：重新检测（兼容旧信号）
            from BreakoutStrategy.signals.detectors.trough import TroughDetector
            trough_detector = TroughDetector(
                window=6,
                min_side_bars=1,      # 解决边界问题：有效范围从 [2,3] 扩展到 [1,4]
                measure="close"       # 支撑测试用 Close：判断收盘价是否守住支撑
            )
            analysis_df = df.iloc[:end_idx]
            all_troughs = trough_detector.detect_troughs(analysis_df)

        # 筛选信号后的 trough（排除 TR2）
        troughs_in_zone = []
        status = "rising"
        break_date = None
        max_pullback_pct = 0.0

        for trough in all_troughs:
            # 跳过 TR2 确认日期（window_end）之前的 trough
            if trough.index <= support_start_idx:
                continue

            # 跳过 TR2 本身（根据索引）
            if tr2_idx is not None and trough.index == tr2_idx:
                continue

            # 获取该 trough 对应 K 线的 Close
            bar_close = float(df["close"].iloc[trough.index])

            # 更新最大回撤（使用 Close 计算回撤）
            if signal.price > 0:
                pullback = (signal.price - bar_close) / signal.price * 100
                max_pullback_pct = max(max_pullback_pct, pullback)

            # 跌破检测：trough.close < zone.lower
            if bar_close < zone.lower:
                status = "broken"
                break_date = str(trough.date)
                break

            # 支撑测试：trough.close 落入支撑带
            if bar_close <= zone.upper:
                troughs_in_zone.append({
                    "date": str(trough.date),
                    "price": round(bar_close, 2),
                    "index": trough.index,
                })

        # 如果没有跌破，根据是否有 trough 确定状态
        if status != "broken":
            status = "confirmed" if troughs_in_zone else "rising"

        # tr_num = 1 (TR2) + 区间内 trough 数量
        tr_num = 1 + len(troughs_in_zone)

        return tr_num, SupportStatus(
            status=status,
            support_zone=[zone.lower, zone.upper],
            test_count=len(troughs_in_zone),
            tests=troughs_in_zone,
            max_pullback_pct=round(max_pullback_pct, 2) if max_pullback_pct > 0 else None,
            last_test_date=troughs_in_zone[-1]["date"] if troughs_in_zone else None,
            break_date=break_date,
        )

    def _find_signal_index(self, df: pd.DataFrame, signal_date: date) -> Optional[int]:
        """找到信号日期在 df 中的位置索引"""
        # 转换 signal_date 为与 df.index 相同的类型
        if hasattr(df.index, 'date'):
            # DatetimeIndex
            matches = df.index.date == signal_date
        else:
            # 可能是其他类型的索引
            try:
                matches = df.index == pd.Timestamp(signal_date)
            except Exception:
                return None

        if not matches.any():
            return None

        return int(df.index.get_loc(df.index[matches][0]))

    def _run_state_machine(
        self,
        df: pd.DataFrame,
        signal_idx: int,
        scan_date_idx: int,
        zone: SupportZone,
        signal_price: float,
    ) -> SupportStatus:
        """
        运行状态机分析支撑

        状态转换：
        - RISING → TESTING: bar.low <= zone.upper
        - TESTING → CONFIRMED: bar.close > zone.upper
        - TESTING → BROKEN: bar.close < zone.lower
        - CONFIRMED → RISING: 自动转换

        Args:
            df: OHLCV 数据
            signal_idx: 信号索引
            scan_date_idx: 扫描结束索引
            zone: 支撑区间
            signal_price: 信号价格（用于计算回撤）

        Returns:
            支撑状态
        """
        state = SupportState.RISING
        tests: List[SupportTest] = []
        current_test_start: Optional[int] = None
        current_test_min: float = float('inf')
        max_pullback_pct: float = 0.0
        break_date: Optional[str] = None

        # 分析范围：信号后到扫描日期
        start_idx = signal_idx + 1
        end_idx = min(scan_date_idx + 1, signal_idx + self.max_lookforward_days + 1, len(df))

        for i in range(start_idx, end_idx):
            bar_low = float(df["low"].iloc[i])
            bar_close = float(df["close"].iloc[i])
            bar_date = df.index[i]

            # 更新最大回撤
            if signal_price > 0:
                pullback = (signal_price - bar_low) / signal_price * 100
                max_pullback_pct = max(max_pullback_pct, pullback)

            if state == SupportState.RISING:
                # 检查是否进入支撑测试
                if bar_low <= zone.upper:
                    state = SupportState.TESTING
                    current_test_start = i
                    current_test_min = bar_low

            elif state == SupportState.TESTING:
                current_test_min = min(current_test_min, bar_low)

                if bar_close < zone.lower:
                    # 支撑失败
                    state = SupportState.BROKEN
                    break_date = str(bar_date)[:10]
                    tests.append(SupportTest(
                        enter_date=df.index[current_test_start].date() if hasattr(df.index[current_test_start], 'date') else df.index[current_test_start],
                        exit_date=bar_date.date() if hasattr(bar_date, 'date') else bar_date,
                        min_price=current_test_min,
                        success=False,
                    ))
                    break
                elif bar_close > zone.upper:
                    # 支撑成功，记录测试并重置状态
                    tests.append(SupportTest(
                        enter_date=df.index[current_test_start].date() if hasattr(df.index[current_test_start], 'date') else df.index[current_test_start],
                        exit_date=bar_date.date() if hasattr(bar_date, 'date') else bar_date,
                        min_price=current_test_min,
                        success=True,
                    ))
                    state = SupportState.RISING
                    current_test_start = None
                    current_test_min = float('inf')

        # 构建返回结果
        successful_tests = [t for t in tests if t.success]
        last_test_date = str(tests[-1].exit_date) if tests else None

        return SupportStatus(
            status=state.value,
            support_zone=[zone.lower, zone.upper],
            test_count=len(successful_tests),
            tests=[
                {
                    "enter_date": str(t.enter_date),
                    "exit_date": str(t.exit_date),
                    "min_price": round(t.min_price, 2),
                    "success": t.success,
                }
                for t in tests
            ],
            max_pullback_pct=round(max_pullback_pct, 2) if max_pullback_pct > 0 else None,
            last_test_date=last_test_date,
            break_date=break_date,
        )

    def enrich_signals(
        self, df: pd.DataFrame, signals: List["AbsoluteSignal"], scan_date_idx: int
    ) -> List["AbsoluteSignal"]:
        """
        为信号列表填充支撑分析结果

        Args:
            df: OHLCV 数据
            signals: 信号列表
            scan_date_idx: 扫描日期索引

        Returns:
            填充后的信号列表（原地修改）
        """
        for signal in signals:
            # 使用 .value 比较避免循环导入
            signal_type_value = signal.signal_type.value

            if signal_type_value == "B":  # BREAKOUT
                status = self.analyze_breakout_support(df, signal, scan_date_idx)
                signal.details["support_status"] = {
                    "status": status.status,
                    "support_zone": status.support_zone,
                    "test_count": status.test_count,
                    "tests": status.tests,
                    "max_pullback_pct": status.max_pullback_pct,
                    "last_test_date": status.last_test_date,
                    "break_date": status.break_date,
                }

            elif signal_type_value == "D":  # DOUBLE_TROUGH
                tr_num, status = self.analyze_double_trough_support(df, signal, scan_date_idx)
                signal.details["tr_num"] = tr_num

                signal.details["support_status"] = {
                    "status": status.status,
                    "support_zone": status.support_zone,
                    "test_count": status.test_count,
                    "tests": status.tests,
                    "max_pullback_pct": status.max_pullback_pct,
                    "last_test_date": status.last_test_date,
                    "break_date": status.break_date,
                }

        return signals
