"""批量扫描管理器"""

import json
import os
from datetime import datetime
from multiprocessing import Pool
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

from BreakoutStrategy.analysis import BreakoutDetector
from BreakoutStrategy.analysis.features import FeatureCalculator
from BreakoutStrategy.analysis.breakout_scorer import BreakoutScorer
from BreakoutStrategy.analysis.indicators import TechnicalIndicators

from ..utils import ensure_dir

# 设置环境变量 DEBUG_VOLUME=1 启用成交量计算调试输出
DEBUG_VOLUME = os.environ.get("DEBUG_VOLUME", "0") == "1"

# 缓冲区计算常量
# 交易日/日历天 ≈ 250/365 ≈ 0.68，转换系数 ≈ 1.5
# 加 10% 安全余量 → 系数 1.65
TRADING_TO_CALENDAR_RATIO = 1.65

# 成交量回看窗口（需与 features.py 中的 VOLUME_LOOKBACK 保持一致）
VOLUME_LOOKBACK_BUFFER = 63

# 年化波动率回看窗口（用于 Overshoot Penalty, Breakout Day Strength Bonus）
ANNUAL_VOL_LOOKBACK_BUFFER = 252


def preprocess_dataframe(
    df: pd.DataFrame,
    start_date: str = None,
    end_date: str = None,
    label_max_days: int = 20,
    ma_periods: list = None,
    atr_period: int = 14,
) -> pd.DataFrame:
    """
    数据预处理：截取时间范围 + 计算技术指标

    Args:
        df: 原始 OHLCV DataFrame
        start_date: 扫描起始日期
        end_date: 扫描结束日期
        label_max_days: Label 计算所需的后置天数
        ma_periods: 要计算的均线周期列表，默认 [200]
        atr_period: ATR 计算周期，默认 14

    Returns:
        预处理后的 DataFrame，包含 ma_xxx 和 atr 列
    """
    if ma_periods is None:
        ma_periods = [200]

    # 动态计算缓冲区：取均线周期、成交量回看、年化波动率回看的最大值，转换为日历天
    max_ma_period = max(ma_periods) if ma_periods else 200
    required_trading_days = max(max_ma_period, VOLUME_LOOKBACK_BUFFER, ANNUAL_VOL_LOOKBACK_BUFFER)
    buffer_days = int(required_trading_days * TRADING_TO_CALENDAR_RATIO)
    label_buffer_days = int(label_max_days * 1.5)

    if start_date:
        buffer_start = pd.to_datetime(start_date) - pd.Timedelta(days=buffer_days)
        df = df[df.index >= buffer_start]
    if end_date:
        buffer_end = pd.to_datetime(end_date) + pd.Timedelta(days=label_buffer_days)
        df = df[df.index <= buffer_end]

    # 计算均线（在缓冲数据上计算，确保显示时有完整值）
    for period in ma_periods:
        df[f"ma_{period}"] = df["close"].rolling(window=period).mean()

    # 计算 ATR（用于突破检测和特征计算）
    df["atr"] = TechnicalIndicators.calculate_atr(
        df["high"], df["low"], df["close"], atr_period
    )

    return df


def compute_breakouts_from_dataframe(
    symbol: str,
    df: pd.DataFrame,
    total_window: int,
    min_side_bars: int,
    min_relative_height: float,
    exceed_threshold: float,
    peak_supersede_threshold: float,
    peak_measure: str = 'body_top',
    breakout_modes: list = None,
    feature_calc_config: dict = None,
    scorer_config: dict = None,
    valid_start_index: int = 0,
    valid_end_index: int = None,
    streak_window: int = 20,
) -> Tuple[List, BreakoutDetector]:
    """
    从 DataFrame 计算突破（统一突破计算函数）

    Args:
        symbol: 股票代码
        df: 数据 DataFrame
        total_window: 总窗口大小（左右合计）
        min_side_bars: 单侧最少K线数
        min_relative_height: 最小相对高度
        exceed_threshold: 突破阈值
        peak_supersede_threshold: 峰值合并阈值
        peak_measure: 峰值价格定义 ('high', 'close', 'body_top')
        breakout_modes: 突破确认模式列表
        feature_calc_config: FeatureCalculator 配置字典
        scorer_config: BreakoutScorer 配置字典
        valid_start_index: 有效检测范围起始索引（之前的数据仅用于 ATR 等指标计算）
        valid_end_index: 有效检测范围结束索引（之后的数据为 Label 缓冲区，不检测）

    Returns:
        (breakouts, detector) 元组
    """
    # 运行突破检测
    detector = BreakoutDetector(
        symbol=symbol,
        total_window=total_window,
        min_side_bars=min_side_bars,
        min_relative_height=min_relative_height,
        exceed_threshold=exceed_threshold,
        peak_supersede_threshold=peak_supersede_threshold,
        peak_measure=peak_measure,
        breakout_modes=breakout_modes,
        streak_window=streak_window,
        use_cache=False,
    )
    breakout_infos = detector.batch_add_bars(
        df,
        return_breakouts=True,
        valid_start_index=valid_start_index,
        valid_end_index=valid_end_index,
    )

    if not breakout_infos:
        return [], detector

    # 特征计算和评分
    feature_calc = FeatureCalculator(config=feature_calc_config or {})
    breakout_scorer = BreakoutScorer(config=scorer_config or {})

    # 使用预计算的 ATR 序列（在 preprocess_dataframe 中计算）
    atr_series = df["atr"] if "atr" in df.columns else TechnicalIndicators.calculate_atr(
        df["high"], df["low"], df["close"], (feature_calc_config or {}).get("atr_period", 14)
    )

    breakouts = []
    for info in breakout_infos:
        # 特征计算（传递预计算的 ATR 序列）
        bo = feature_calc.enrich_breakout(df, info, symbol, detector=detector, atr_series=atr_series)
        breakouts.append(bo)

    # 批量评分
    breakout_scorer.score_breakouts_batch(breakouts)

    return breakouts, detector


def _scan_single_stock(args):
    """
    扫描单只股票（用于多进程）

    Args:
        args: (symbol, data_dir, total_window, min_side_bars, min_relative_height,
               exceed_threshold, peak_supersede_threshold, peak_measure, breakout_modes,
               streak_window, start_date, end_date, feature_calc_config, scorer_config,
               label_max_days, min_price, max_price, min_volume)

    Returns:
        结果字典，若被过滤返回 None
    """
    (
        symbol,
        data_dir,
        total_window,
        min_side_bars,
        min_relative_height,
        exceed_threshold,
        peak_supersede_threshold,
        peak_measure,
        breakout_modes,
        streak_window,
        start_date,
        end_date,
        feature_calc_config,
        scorer_config,
        label_max_days,
        min_price,
        max_price,
        min_volume,
    ) = args

    file_path = Path(data_dir) / f"{symbol}.pkl"

    if not file_path.exists():
        return {"symbol": symbol, "error": "File not found"}

    try:
        # 加载数据
        df = pd.read_pickle(file_path)

        # ===== 数据充足性检查：确保有足够的历史数据计算所有指标 =====
        if len(df) < ANNUAL_VOL_LOOKBACK_BUFFER:
            return {
                "symbol": symbol,
                "skipped": True,
                "reason": f"insufficient_history ({len(df)} < {ANNUAL_VOL_LOOKBACK_BUFFER})",
            }

        # ===== 股票筛选条件检查（在预处理之前，仅检查扫描时间范围内的数据）=====
        if min_price is not None or max_price is not None or min_volume is not None:
            # 截取扫描时间范围内的数据（不含缓冲区）
            scan_df = df.copy()
            if start_date:
                scan_df = scan_df[scan_df.index >= pd.to_datetime(start_date)]
            if end_date:
                scan_df = scan_df[scan_df.index <= pd.to_datetime(end_date)]

            if scan_df.empty:
                return None  # 时间范围内无数据，被过滤

            # 价格范围检查：时间范围内 low 必须 > min_price
            if min_price is not None and scan_df["low"].min() <= min_price:
                return None  # 被过滤

            # 价格范围检查：时间范围内 high 必须 < max_price
            if max_price is not None and scan_df["high"].max() >= max_price:
                return None  # 被过滤

            # 成交量检查：时间范围内平均成交量必须 > min_volume
            if min_volume is not None and scan_df["volume"].mean() <= min_volume:
                return None  # 被过滤

        # 数据预处理：截取时间范围 + 计算技术指标（MA、ATR）
        atr_period = (feature_calc_config or {}).get("atr_period", 14)
        ma_period = (feature_calc_config or {}).get("ma_period", 200)
        df = preprocess_dataframe(
            df,
            start_date=start_date,
            end_date=end_date,
            label_max_days=label_max_days or 20,
            ma_periods=[ma_period],
            atr_period=atr_period,
        )

        scan_start_date = start_date  # 保存原始扫描起始日期
        scan_end_date = end_date      # 保存原始扫描结束日期（用于过滤突破）

        if df.empty:
            return {"symbol": symbol, "error": "Empty dataframe after filtering"}

        # 计算有效检测范围索引（排除 ATR 缓冲区和 Label 缓冲区）
        valid_start_index = 0
        valid_end_index = len(df)

        if scan_start_date:
            scan_start_dt = pd.to_datetime(scan_start_date)
            # 找到第一个 >= scan_start_date 的索引
            mask = df.index >= scan_start_dt
            if mask.any():
                valid_start_index = mask.argmax()

        if scan_end_date:
            scan_end_dt = pd.to_datetime(scan_end_date)
            # 找到最后一个 <= scan_end_date 的索引 + 1
            mask = df.index <= scan_end_dt
            if mask.any():
                # 找到最后一个 True 的位置 + 1
                valid_end_index = mask[::-1].argmax()
                valid_end_index = len(df) - valid_end_index

        # 调试输出：batch scan 数据预处理详情
        if DEBUG_VOLUME:
            df_start = df.index[0].strftime("%Y-%m-%d") if hasattr(df.index[0], 'strftime') else str(df.index[0])
            df_end = df.index[-1].strftime("%Y-%m-%d") if hasattr(df.index[-1], 'strftime') else str(df.index[-1])
            print(f"[DEBUG_VOLUME][BATCH_SCAN] symbol={symbol}, "
                  f"scan_range=[{scan_start_date}, {scan_end_date}], "
                  f"df_range=[{df_start}, {df_end}], len(df)={len(df)}, "
                  f"valid_start_index={valid_start_index}, valid_end_index={valid_end_index}")

        # 使用统一函数计算突破（检测范围前置限定）
        breakouts, detector = compute_breakouts_from_dataframe(
            symbol=symbol,
            df=df,
            total_window=total_window,
            min_side_bars=min_side_bars,
            min_relative_height=min_relative_height,
            exceed_threshold=exceed_threshold,
            peak_supersede_threshold=peak_supersede_threshold,
            peak_measure=peak_measure,
            breakout_modes=breakout_modes,
            feature_calc_config=feature_calc_config,
            scorer_config=scorer_config,
            valid_start_index=valid_start_index,
            valid_end_index=valid_end_index,
            streak_window=streak_window,
        )

        if not breakouts:
            return {
                "symbol": symbol,
                "scan_start_date": scan_start_date
                if scan_start_date
                else df.index[0].strftime("%Y-%m-%d"),
                "scan_end_date": scan_end_date
                if scan_end_date
                else df.index[-1].strftime("%Y-%m-%d"),
                "data_points": len(df),
                "active_peaks": len(detector.active_peaks),
                "total_breakouts": 0,
                "avg_quality": 0.0,
                "max_quality": 0.0,
                "breakouts": [],
            }

        # 收集所有峰值（active + broken）并分配唯一ID
        all_peaks_dict = {}  # {id: Peak}
        peak_id_counter = 1

        # 1. 收集active peaks并分配ID
        for peak in detector.active_peaks:
            if peak.id is None:
                peak.id = peak_id_counter
                peak_id_counter += 1
            all_peaks_dict[peak.id] = peak

        # 2. 收集broken peaks并分配ID（去重）
        for bo in breakouts:
            for peak in bo.broken_peaks:
                if peak.id is None:  # 未分配ID
                    peak.id = peak_id_counter
                    all_peaks_dict[peak_id_counter] = peak
                    peak_id_counter += 1
                elif peak.id not in all_peaks_dict:
                    all_peaks_dict[peak.id] = peak

        # 3. 标记active状态
        # 注意：峰值已在检测阶段通过 valid_start_index 过滤，无需事后过滤
        active_peak_ids = {p.id for p in detector.active_peaks if p.id in all_peaks_dict}

        # 计算质量评分统计
        quality_scores = [
            bo.quality_score
            for bo in breakouts
            if bo.quality_score is not None
        ]
        avg_quality = (
            sum(quality_scores) / len(quality_scores) if quality_scores else 0.0
        )
        max_quality = max(quality_scores) if quality_scores else 0.0

        # 统计 multi-peak 数量
        multi_peak_count = sum(1 for bo in breakouts if bo.num_peaks_broken > 1)

        # 转换为可序列化格式
        result = {
            "symbol": symbol,
            "scan_start_date": start_date
            if start_date
            else df.index[0].strftime("%Y-%m-%d"),
            "scan_end_date": end_date
            if end_date
            else df.index[-1].strftime("%Y-%m-%d"),
            "data_points": len(df),
            "active_peaks": len(detector.active_peaks),
            "total_breakouts": len(breakouts),
            "avg_quality": avg_quality,
            "max_quality": max_quality,
            "multi_peak_count": multi_peak_count,
            "all_peaks": [
                {
                    "id": peak.id,
                    "price": float(peak.price),
                    "date": peak.date.isoformat(),
                    "index": int(peak.index),
                    "volume_surge_ratio": float(peak.volume_surge_ratio)
                    if peak.volume_surge_ratio
                    else 0.0,
                    "candle_change_pct": float(peak.candle_change_pct)
                    if peak.candle_change_pct
                    else 0.0,
                    "left_suppression_days": int(peak.left_suppression_days)
                    if peak.left_suppression_days
                    else 0,
                    "right_suppression_days": int(peak.right_suppression_days)
                    if peak.right_suppression_days
                    else 0,
                    "relative_height": float(peak.relative_height)
                    if peak.relative_height
                    else 0.0,
                    "is_active": peak.id in active_peak_ids,
                }
                for peak in sorted(all_peaks_dict.values(), key=lambda p: p.index)
            ],
            "breakouts": [
                {
                    "date": bo.date.isoformat(),
                    "price": float(bo.price),
                    "index": int(bo.index),
                    "broken_peak_ids": bo.broken_peak_ids,  # 使用ID引用而非完整对象
                    "superseded_peak_ids": bo.superseded_peak_ids,  # 被真正移除的峰值ID
                    "num_peaks_broken": int(bo.num_peaks_broken),
                    "breakout_type": bo.breakout_type,
                    "intraday_change_pct": float(bo.intraday_change_pct)
                    if bo.intraday_change_pct
                    else None,
                    "gap_up_pct": float(bo.gap_up_pct)
                    if hasattr(bo, "gap_up_pct") and bo.gap_up_pct
                    else None,
                    "gap_atr_ratio": float(bo.gap_atr_ratio)
                    if hasattr(bo, "gap_atr_ratio") and bo.gap_atr_ratio
                    else None,
                    "volume_surge_ratio": float(bo.volume_surge_ratio)
                    if bo.volume_surge_ratio
                    else None,
                    "momentum": float(bo.momentum)
                    if hasattr(bo, "momentum") and bo.momentum
                    else None,
                    "stability_score": float(bo.stability_score)
                    if hasattr(bo, "stability_score") and bo.stability_score
                    else None,
                    "quality_score": float(bo.quality_score)
                    if bo.quality_score
                    else None,
                    # 连续突破次数（Momentum）
                    "recent_breakout_count": int(bo.recent_breakout_count)
                    if hasattr(bo, "recent_breakout_count")
                    else 1,
                    # 距上次突破的交易日间隔（Drought）
                    "days_since_last_breakout": int(bo.days_since_last_breakout)
                    if hasattr(bo, "days_since_last_breakout") and bo.days_since_last_breakout is not None
                    else None,
                    # ATR 相关
                    "atr_value": float(bo.atr_value)
                    if hasattr(bo, "atr_value") and bo.atr_value
                    else None,
                    "atr_normalized_height": float(bo.atr_normalized_height)
                    if hasattr(bo, "atr_normalized_height") and bo.atr_normalized_height
                    else None,
                    "daily_return_atr_ratio": float(bo.daily_return_atr_ratio)
                    if hasattr(bo, "daily_return_atr_ratio") and bo.daily_return_atr_ratio
                    else None,
                    "pk_momentum": float(bo.pk_momentum)
                    if hasattr(bo, "pk_momentum") and bo.pk_momentum
                    else None,
                    # 波动率动态阈值相关
                    "gain_5d": float(bo.gain_5d)
                    if hasattr(bo, "gain_5d") and bo.gain_5d
                    else None,
                    "annual_volatility": float(bo.annual_volatility)
                    if hasattr(bo, "annual_volatility") and bo.annual_volatility
                    else None,
                    # 模式标签
                    "pattern_label": getattr(bo, 'pattern_label', 'basic'),
                    # 回测标签
                    "labels": {
                        k: float(v) if v is not None else None
                        for k, v in (bo.labels or {}).items()
                    },
                }
                for bo in sorted(
                    breakouts,
                    key=lambda x: x.quality_score if x.quality_score else 0,
                    reverse=True,
                )
            ],
        }

        # 注意：股票级标签统计量（avg/max/best_quality/latest）在 UI 层动态计算
        # 避免在 Configure Columns 中显示冗余的统计量选项

        return result

    except Exception as e:
        return {"symbol": symbol, "error": str(e)}


class ScanManager:
    """扫描管理器"""

    def __init__(
        self,
        output_dir="outputs/analysis",
        total_window=10,
        min_side_bars=2,
        min_relative_height=0.05,
        exceed_threshold=0.005,
        peak_supersede_threshold=0.03,
        peak_measure='body_top',
        breakout_modes=None,
        streak_window=20,
        start_date=None,
        end_date=None,
        feature_calc_config=None,
        scorer_config=None,
        label_max_days=None,
        min_price=None,
        max_price=None,
        min_volume=None,
    ):
        """
        初始化扫描管理器

        Args:
            output_dir: 输出目录
            total_window: 总窗口大小（左右合计）
            min_side_bars: 单侧最少K线数
            min_relative_height: 最小相对高度
            exceed_threshold: 突破阈值
            peak_supersede_threshold: 峰值合并阈值
            peak_measure: 峰值价格定义 ('high', 'close', 'body_top')
            breakout_modes: 突破确认模式列表
            start_date: 起始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            feature_calc_config: FeatureCalculator 配置字典
            scorer_config: 评分器配置字典
            label_max_days: Label 计算所需的最大天数（用于后置缓冲）
            min_price: 最低价格限制（时间范围内 low 必须 > min_price）
            max_price: 最高价格限制（时间范围内 high 必须 < max_price）
            min_volume: 最小平均成交量（时间范围内平均成交量必须 > min_volume）
        """
        self.output_dir = Path(output_dir)
        ensure_dir(self.output_dir)

        self.total_window = total_window
        self.min_side_bars = min_side_bars
        self.min_relative_height = min_relative_height
        self.exceed_threshold = exceed_threshold
        self.peak_supersede_threshold = peak_supersede_threshold
        self.peak_measure = peak_measure
        self.breakout_modes = breakout_modes or ['body_top']
        self.streak_window = streak_window
        self.start_date = start_date
        self.end_date = end_date
        self.scan_date = datetime.now().isoformat()

        # 保存特征计算和评分配置
        self.feature_calc_config = feature_calc_config if feature_calc_config else {}
        self.scorer_config = scorer_config if scorer_config else {}
        self.label_max_days = label_max_days or 20

        # 股票筛选条件（仅 Global 模式有效）
        self.min_price = min_price
        self.max_price = max_price
        self.min_volume = min_volume

    def scan_stock(self, symbol: str, data_dir: str = "datasets/pkls") -> Dict:
        """
        扫描单只股票

        Args:
            symbol: 股票代码
            data_dir: 数据目录

        Returns:
            结果字典，若被过滤返回 None
        """
        return _scan_single_stock(
            (
                symbol,
                data_dir,
                self.total_window,
                self.min_side_bars,
                self.min_relative_height,
                self.exceed_threshold,
                self.peak_supersede_threshold,
                self.peak_measure,
                self.breakout_modes,
                self.streak_window,
                self.start_date,
                self.end_date,
                self.feature_calc_config,
                self.scorer_config,
                self.label_max_days,
                self.min_price,
                self.max_price,
                self.min_volume,
            )
        )

    def parallel_scan(
        self,
        symbols: List[str],
        data_dir: str = "datasets/pkls",
        num_workers: int = 8,
        stock_time_ranges: Dict[str, tuple] = None,
    ) -> List[Dict]:
        """
        并行扫描多只股票

        Args:
            symbols: 股票代码列表
            data_dir: 数据目录
            num_workers: 并行worker数
            stock_time_ranges: 每只股票的时间范围（可选）
                              格式：{symbol: (start_date, end_date)}
                              如果为None，使用全局的 self.start_date 和 self.end_date

        Returns:
            结果列表（不含被过滤的股票）
        """
        print(f"开始扫描 {len(symbols)} 只股票...")
        print(f"使用 {num_workers} 个并行进程")
        print(
            f"参数: total_window={self.total_window}, min_side_bars={self.min_side_bars}, "
            f"min_relative_height={self.min_relative_height}, exceed_threshold={self.exceed_threshold}"
        )

        # 打印模式信息
        if stock_time_ranges:
            print(f"扫描模式: CSV索引模式（每只股票独立时间范围）")
            # CSV 模式不使用筛选条件
            min_price, max_price, min_volume = None, None, None
        else:
            print(f"扫描模式: 全局时间范围模式")
            if self.start_date or self.end_date:
                print(f"时间范围: {self.start_date} - {self.end_date}")
            # 打印筛选条件（如果有）
            if self.min_price or self.max_price or self.min_volume:
                print(f"筛选条件: min_price={self.min_price}, max_price={self.max_price}, min_volume={self.min_volume}")
            min_price, max_price, min_volume = self.min_price, self.max_price, self.min_volume

        # 构建参数列表
        args = []
        for sym in symbols:
            # 判断使用 per-stock 时间范围还是全局时间范围
            if stock_time_ranges and sym in stock_time_ranges:
                start_date, end_date = stock_time_ranges[sym]
            else:
                start_date, end_date = self.start_date, self.end_date

            args.append(
                (
                    sym,
                    data_dir,
                    self.total_window,
                    self.min_side_bars,
                    self.min_relative_height,
                    self.exceed_threshold,
                    self.peak_supersede_threshold,
                    self.peak_measure,
                    self.breakout_modes,
                    self.streak_window,
                    start_date,
                    end_date,
                    self.feature_calc_config,
                    self.scorer_config,
                    self.label_max_days,
                    min_price,
                    max_price,
                    min_volume,
                )
            )

        with Pool(processes=num_workers) as pool:
            all_results = pool.map(_scan_single_stock, args)

        # 过滤结果：区分跳过（数据不足）和筛选（条件过滤）
        all_results = [r for r in all_results if r is not None]
        skipped_results = [r for r in all_results if r.get("skipped")]
        valid_results = [r for r in all_results if not r.get("skipped")]

        # 打印统计
        print(f"\n扫描完成！共 {len(valid_results)} 只股票")
        if skipped_results:
            print(f"跳过 {len(skipped_results)} 只股票（数据不足）")

        return valid_results

    def _save_results_internal(self, results: List[Dict], output_path: Path):
        """内部方法：保存结果"""
        # 统计信息
        successful_scans = [r for r in results if "total_breakouts" in r]
        error_scans = [r for r in results if "error" in r]

        # 计算统计数据
        total_breakouts = sum(
            r.get("total_breakouts", 0) for r in successful_scans
        )
        stocks_with_breakouts = sum(
            1 for r in successful_scans if r.get("total_breakouts", 0) > 0
        )

        # 收集所有质量评分
        all_quality_scores = []
        for r in successful_scans:
            for bo in r.get("breakouts", []):
                if bo.get("quality_score"):
                    all_quality_scores.append(bo["quality_score"])

        output_data = {
            "scan_metadata": {
                "schema_version": "3.0",  # 升级到v3.0，保存完整参数
                "scan_date": self.scan_date,
                "total_stocks": len(results),
                "stocks_scanned": len(successful_scans),
                "scan_errors": len(error_scans),
                "start_date": self.start_date,
                "end_date": self.end_date,
                # 分组保存参数（v3.0新格式）
                "detector_params": {
                    "total_window": self.total_window,
                    "min_side_bars": self.min_side_bars,
                    "min_relative_height": self.min_relative_height,
                    "exceed_threshold": self.exceed_threshold,
                    "peak_supersede_threshold": self.peak_supersede_threshold,
                    "peak_measure": self.peak_measure,
                    "breakout_modes": self.breakout_modes,
                },
                "feature_calculator_params": self.feature_calc_config,
                "quality_scorer_params": self.scorer_config,
            },
            "results": results,
            "summary_stats": {
                "total_breakouts": total_breakouts,
                "stocks_with_breakouts": stocks_with_breakouts,
                "avg_breakouts_per_stock": total_breakouts
                / len(successful_scans)
                if successful_scans
                else 0,
                "avg_quality_score": sum(all_quality_scores) / len(all_quality_scores)
                if all_quality_scores
                else 0,
            },
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

    def save_results(self, results: List[Dict], filename: str = None):
        """
        保存扫描结果

        Args:
            results: 结果列表
            filename: 文件名（可选）

        Returns:
            保存路径
        """
        if filename is None:
            filename = f"scan_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        output_path = self.output_dir / filename
        self._save_results_internal(results, output_path)

        print(f"\n结果已保存: {output_path}")
        print(f"总股票数: {len(results)}")

        # 打印简要统计
        successful_scans = [r for r in results if "total_breakouts" in r]
        error_scans = [r for r in results if "error" in r]

        print(f"成功扫描: {len(successful_scans)}")
        print(f"扫描错误: {len(error_scans)}")

        if successful_scans:
            total_bos = sum(r.get("total_breakouts", 0) for r in successful_scans)
            print(f"总突破数: {total_bos}")

        return output_path

    def load_results(self, input_path: str) -> Dict:
        """
        加载已保存的扫描结果

        Args:
            input_path: 输入文件路径

        Returns:
            扫描结果字典

        Raises:
            ValueError: 如果JSON版本不支持
        """
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 版本检查和自动迁移
        schema_version = data.get("scan_metadata", {}).get("schema_version", "1.0")
        metadata = data["scan_metadata"]

        if schema_version == "2.0":
            # v2.0 → v3.0 自动迁移
            print(f"检测到 v2.0 格式，自动迁移到 v3.0...")
            # 重构参数结构（将旧的 window 转换为新的三个参数）
            old_window = metadata.pop("window", 5)
            metadata["detector_params"] = {
                "total_window": old_window * 2,  # 旧逻辑：左右各window，新逻辑：合计
                "min_side_bars": old_window,     # 保持单侧要求
                "min_relative_height": 0.0,      # 旧逻辑不检查相对高度
                "exceed_threshold": metadata.pop("exceed_threshold"),
                "peak_supersede_threshold": metadata.pop("peak_supersede_threshold"),
            }
            # 添加默认参数
            metadata["feature_calculator_params"] = self._get_default_feature_params()
            metadata["quality_scorer_params"] = self._get_default_scorer_params()
            metadata["schema_version"] = "3.0"
            print("迁移完成（使用默认特征和评分参数）")

        elif schema_version != "3.0":
            raise ValueError(
                f"Unsupported JSON format (version {schema_version}). "
                f"Please re-scan with the latest version to generate v3.0 JSON."
            )

        print(f"加载扫描结果: {input_path}")
        print(f"扫描日期: {data['scan_metadata']['scan_date']}")
        print(f"总股票数: {data['scan_metadata']['total_stocks']}")
        print(f"成功扫描: {data['scan_metadata']['stocks_scanned']}")

        return data

    def _get_default_feature_params(self) -> Dict:
        """获取 FeatureCalculator 默认参数（用于 v2.0 迁移）"""
        return {
            "stability_lookforward": 10,
            "continuity_lookback": 5,
        }

    def _get_default_scorer_params(self) -> Dict:
        """获取评分器默认参数（用于 v2.0 迁移）"""
        return {
            # Peak weights (仅筹码堆积因子: volume + candle)
            "peak_weight_volume": 0.60,
            "peak_weight_candle": 0.40,
            # Breakout weights
            "bo_weight_change": 0.15,
            "bo_weight_gap": 0.08,
            "bo_weight_volume": 0.17,
            "bo_weight_continuity": 0.12,
            "bo_weight_stability": 0.13,
            "bo_weight_resistance": 0.18,
            "bo_weight_historical": 0.17,
            # Resistance sub-weights
            "res_weight_quantity": 0.30,
            "res_weight_density": 0.30,
            "res_weight_quality": 0.40,
            # Historical sub-weights (relative_height 替换 suppression)
            "hist_weight_oldest_age": 0.55,
            "hist_weight_relative_height": 0.45,
            # Scalar params
            "time_decay_baseline": 0.3,
            "time_decay_half_life": 84,
            "historical_significance_saturation": 252,
            "historical_quality_threshold": 70,
        }
