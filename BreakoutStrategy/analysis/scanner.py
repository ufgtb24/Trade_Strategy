"""批量扫描管理器

从 BreakoutStrategy/UI/managers/scan_manager.py 迁移。
业务逻辑归位：扫描引擎属于 analysis 层，不是 UI 层。
"""

import json
import logging
import os
from datetime import datetime
from multiprocessing import Pool
from pathlib import Path
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

import pandas as pd

from BreakoutStrategy.analysis import BreakoutDetector
from BreakoutStrategy.analysis.features import FeatureCalculator
from BreakoutStrategy.analysis.breakout_scorer import BreakoutScorer
from BreakoutStrategy.analysis.indicators import TechnicalIndicators
from BreakoutStrategy.factor_registry import get_active_factors

def ensure_dir(directory):
    """确保目录存在（从 BreakoutStrategy.dev.utils 内联，避免对 UI 层的反向依赖）"""
    os.makedirs(directory, exist_ok=True)
    return directory


def _serialize_factor_fields(bo) -> dict:
    """从 FACTOR_REGISTRY 动态序列化因子字段"""
    fields = {}
    for fi in get_active_factors():
        val = getattr(bo, fi.key, None)
        if fi.nullable and val is None:
            fields[fi.key] = None
        elif val is None:
            fields[fi.key] = 0 if fi.is_discrete else 0.0
        else:
            fields[fi.key] = int(val) if fi.is_discrete else float(val)
    return fields


# 设置环境变量 DEBUG_VOLUME=1 启用成交量计算调试输出
DEBUG_VOLUME = os.environ.get("DEBUG_VOLUME", "0") == "1"

# 缓冲区计算常量
# 交易日/日历天 ≈ 250/365 ≈ 0.68，转换系数 ≈ 1.5
# 加 10% 安全余量 → 系数 1.65
TRADING_TO_CALENDAR_RATIO = 1.65


def preprocess_dataframe(
    df: pd.DataFrame,
    start_date: str = None,
    end_date: str = None,
    label_max_days: int = 20,
    ma_periods: list = None,
    atr_period: int = 14,
    feat_params: dict = None,
) -> pd.DataFrame:
    """
    数据预处理：截取时间范围 + 计算技术指标 + 写入 range_meta 元数据

    Args:
        df: 原始 OHLCV DataFrame
        start_date: 扫描起始日期
        end_date: 扫描结束日期
        label_max_days: Label 计算所需的后置天数
        ma_periods: 要计算的均线周期列表，默认 [200]
        atr_period: ATR 计算周期，默认 14
        feat_params: FeatureCalculator 配置字典。None 时用默认因子 lookback。

    Returns:
        预处理后的 DataFrame，包含 ma_xxx / atr 列和 df.attrs["range_meta"]
    """
    if ma_periods is None:
        ma_periods = [200]

    # 记录 pkl 原始边界（在 df 被裁切之前）
    pkl_start = df.index[0].date() if len(df) else None
    pkl_end = df.index[-1].date() if len(df) else None

    # 动态计算缓冲区：预计算列（MA/ATR）+ 全部因子 lookback 的最大值
    max_ma_period = max(ma_periods) if ma_periods else 200
    factor_lookback = FeatureCalculator.max_effective_buffer(feat_params)
    required_trading_days = max(max_ma_period, atr_period, factor_lookback)
    buffer_days = int(required_trading_days * TRADING_TO_CALENDAR_RATIO)
    label_buffer_days = int(label_max_days * 1.5)

    buffer_start = None
    buffer_end = None
    if start_date:
        buffer_start = pd.to_datetime(start_date) - pd.Timedelta(days=buffer_days)
        df = df[df.index >= buffer_start]
    if end_date:
        buffer_end = pd.to_datetime(end_date) + pd.Timedelta(days=label_buffer_days)
        df = df[df.index <= buffer_end]

    # 计算均线
    for period in ma_periods:
        df[f"ma_{period}"] = df["close"].rolling(window=period).mean()

    # 计算 ATR
    df["atr"] = TechnicalIndicators.calculate_atr(
        df["high"], df["low"], df["close"], atr_period
    )

    # 计算 scan_start/end_actual（df 已经被裁到 [buffer_start, buffer_end]）
    scan_start_actual = None
    scan_end_actual = None
    if len(df):
        if start_date:
            start_dt = pd.to_datetime(start_date)
            mask_start = df.index >= start_dt
            if mask_start.any():
                scan_start_actual = df.index[int(mask_start.argmax())].date()
            else:
                # df 中全部早于 start_date（理论上不应发生）
                scan_start_actual = df.index[-1].date()
        else:
            scan_start_actual = df.index[0].date()
        if end_date:
            end_dt = pd.to_datetime(end_date)
            idx_le = df.index[df.index <= end_dt]
            if len(idx_le):
                # 找到最后一个 <= end_date 的位置
                scan_end_actual = idx_le[-1].date()
            else:
                scan_end_actual = df.index[0].date()
        else:
            scan_end_actual = df.index[-1].date()

    # 写入范围元数据
    df.attrs["range_meta"] = {
        "pkl_start": pkl_start,
        "pkl_end": pkl_end,
        "scan_start_ideal": pd.to_datetime(start_date).date() if start_date else None,
        "scan_end_ideal": pd.to_datetime(end_date).date() if end_date else None,
        "compute_start_ideal": buffer_start.date() if buffer_start is not None else None,
        "compute_start_actual": df.index[0].date() if len(df) else None,
        "label_buffer_end_ideal": buffer_end.date() if buffer_end is not None else None,
        "label_buffer_end_actual": df.index[-1].date() if len(df) else None,
        "scan_start_actual": scan_start_actual,
        "scan_end_actual": scan_end_actual,
    }

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
    breakout_mode: str = 'body_top',
    feature_calc_config: dict = None,
    scorer_config: dict = None,
    valid_start_index: int = 0,
    valid_end_index: int = None,
    streak_window: int = 20,
    scan_start_date: str = None,
    scan_end_date: str = None,
    min_price: float = None,
    max_price: float = None,
) -> Tuple[List, List, BreakoutDetector]:
    """
    从 DataFrame 计算突破（统一突破计算函数）

    BO 价格过滤前置：当 min_price/max_price 提供时，在 enrich+score 之前
    partition breakout_infos——只对通过价格门的 BO 跑 enrich+score（省 CPU），
    被过滤的 BO 以原始 BreakoutInfo 形式返回，由 dev UI 用于灰色绘制。

    Args:
        df: 数据 DataFrame
        symbol: 股票代码
        total_window: 总窗口大小（左右合计）
        min_side_bars: 单侧最少K线数
        min_relative_height: 最小相对高度
        exceed_threshold: 突破阈值
        peak_supersede_threshold: 峰值合并阈值
        peak_measure: 峰值价格定义 ('high', 'close', 'body_top')
        breakout_mode: 突破确认模式
        feature_calc_config: FeatureCalculator 配置字典
        scorer_config: BreakoutScorer 配置字典
        valid_start_index: 有效检测范围起始索引（之前的数据仅用于 ATR 等指标计算）
        valid_end_index: 有效检测范围结束索引（之后的数据为 Label 缓冲区，不检测）
        scan_start_date: 扫描起始日期字符串（用于写 actual 字段和降级日志）
        scan_end_date: 扫描结束日期字符串（用于写 actual 字段和降级日志）
        min_price: BO 突破日价格下限（None=不过滤）
        max_price: BO 突破日价格上限（None=不过滤）

    Returns:
        (kept_breakouts, filtered_infos, detector) 元组：
        - kept_breakouts: 通过价格门的 Breakout 列表（含完整因子+评分）
        - filtered_infos: 被过滤的 BreakoutInfo 列表（无因子，仅原始检测信息）
        - detector: BreakoutDetector 实例
    """
    _valid_end = valid_end_index if valid_end_index is not None else len(df)

    # 补齐 scan_start/end_actual 到 df.attrs["range_meta"] + 降级日志
    if len(df) and _valid_end > valid_start_index:
        scan_start_actual = df.index[valid_start_index].date()
        scan_end_actual = df.index[_valid_end - 1].date()

        meta = df.attrs.get("range_meta", {})
        meta["scan_start_actual"] = scan_start_actual
        meta["scan_end_actual"] = scan_end_actual
        df.attrs["range_meta"] = meta

        if scan_start_date:
            ideal_start = pd.to_datetime(scan_start_date).date()
            if scan_start_actual > ideal_start:
                logger.info(
                    "scan_start degraded: requested=%s, actual=%s (pkl starts later)",
                    ideal_start, scan_start_actual,
                )

        if scan_end_date:
            ideal_end = pd.to_datetime(scan_end_date).date()
            if scan_end_actual < ideal_end:
                logger.info(
                    "scan_end degraded: requested=%s, actual=%s (pkl ends earlier)",
                    ideal_end, scan_end_actual,
                )

    # 运行突破检测
    detector = BreakoutDetector(
        symbol=symbol,
        total_window=total_window,
        min_side_bars=min_side_bars,
        min_relative_height=min_relative_height,
        exceed_threshold=exceed_threshold,
        peak_supersede_threshold=peak_supersede_threshold,
        peak_measure=peak_measure,
        breakout_mode=breakout_mode,
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
        return [], [], detector

    # Partition by price gate before enrich——被过滤的 BO 不算因子，节省 CPU
    kept_infos: List = []
    filtered_infos: List = []
    if min_price is not None or max_price is not None:
        for info in breakout_infos:
            if (min_price is None or info.current_price >= min_price) and \
               (max_price is None or info.current_price <= max_price):
                kept_infos.append(info)
            else:
                filtered_infos.append(info)
    else:
        kept_infos = list(breakout_infos)

    if not kept_infos:
        return [], filtered_infos, detector

    # 特征计算和评分（仅对 kept_infos）
    feature_calc = FeatureCalculator(config=feature_calc_config or {})
    breakout_scorer = BreakoutScorer(config=scorer_config or {})

    # 使用预计算的 ATR 序列（在 preprocess_dataframe 中计算）
    atr_series = df["atr"] if "atr" in df.columns else TechnicalIndicators.calculate_atr(
        df["high"], df["low"], df["close"], (feature_calc_config or {}).get("atr_period", 14)
    )

    # 预计算每日放量倍数序列（用于 pre_vol 因子）
    vol_ratio_series = FeatureCalculator.precompute_vol_ratio_series(df)

    breakouts = []
    for info in kept_infos:
        # 特征计算（传递预计算的 ATR 序列）
        bo = feature_calc.enrich_breakout(
            df, info, symbol, detector=detector,
            atr_series=atr_series, vol_ratio_series=vol_ratio_series,
        )
        breakouts.append(bo)

    # 批量评分
    breakout_scorer.score_breakouts_batch(breakouts)

    return breakouts, filtered_infos, detector


def _scan_single_stock(args):
    """
    扫描单只股票（用于多进程）

    Args:
        args: (symbol, data_dir, total_window, min_side_bars, min_relative_height,
               exceed_threshold, peak_supersede_threshold, peak_measure, breakout_mode,
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
        breakout_mode,
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

        # 注：旧的 `if len(df) < ANNUAL_VOL_LOOKBACK_BUFFER: skip` 股票级门槛
        # 已删除（实测筛 0/5981 股票，dead code）。per-factor gate 架构下
        # 门控逻辑已移至各因子计算层，同一只股票内早期低 idx BO 的因子值
        # 缺失会导致该因子门控失效，晚期 BO 仍保留。

        # ===== 股票筛选条件检查（成交量 stock-level 预筛）=====
        if min_volume is not None:
            scan_df = df.copy()
            if start_date:
                scan_df = scan_df[scan_df.index >= pd.to_datetime(start_date)]
            if end_date:
                scan_df = scan_df[scan_df.index <= pd.to_datetime(end_date)]

            if scan_df.empty:
                return None

            if scan_df["volume"].mean() <= min_volume:
                return None

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
            feat_params=feature_calc_config,
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

        # 使用统一函数计算突破（检测范围前置限定，价格过滤前置）
        # 被价格门过滤的 BO 不参与 enrich+score（节省 CPU）；filtered_infos
        # 以最小字段（index/date/price/broken_peak_ids）持久化进 JSON，使
        # 浏览模式（cache 路径）能像分析模式一样把 filtered BO 击穿的 peak
        # 走 all_broken_peaks 路径绘制为正常黑色 ▽。
        breakouts, filtered_infos, detector = compute_breakouts_from_dataframe(
            symbol=symbol,
            df=df,
            total_window=total_window,
            min_side_bars=min_side_bars,
            min_relative_height=min_relative_height,
            exceed_threshold=exceed_threshold,
            peak_supersede_threshold=peak_supersede_threshold,
            peak_measure=peak_measure,
            breakout_mode=breakout_mode,
            feature_calc_config=feature_calc_config,
            scorer_config=scorer_config,
            valid_start_index=valid_start_index,
            valid_end_index=valid_end_index,
            streak_window=streak_window,
            min_price=min_price,
            max_price=max_price,
        )

        if not breakouts:
            return None

        # 收集所有曾创建过的峰值。
        # 以 detector.all_peaks 为权威来源：union(active, broken_via_BOs,
        # superseded_by_new_peak) 会漏掉那些"被 price-filtered BO 击穿"的
        # peak（例如 ARQQ 在 [1.0, 10.0] 价格门下 11 个 BO 中 10 个被滤除，
        # 它们携带的 8 个 peak 在旧路径下整体丢失）。detector.all_peaks 在
        # peak 创建时填充，与下游过滤完全解耦。
        # 注意：峰值已在检测阶段通过 valid_start_index 过滤，无需事后过滤。
        all_peaks_dict = {p.id: p for p in detector.all_peaks if p.id is not None}

        active_peak_ids = {p.id for p in detector.active_peaks if p.id in all_peaks_dict}
        superseded_peak_ids = {p.id for p in detector.superseded_by_new_peak if p.id in all_peaks_dict}

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
                    "volume_peak": float(peak.volume_peak)
                    if peak.volume_peak
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
                    "is_superseded": peak.id in superseded_peak_ids,
                    "superseded_peak_ids": list(peak.superseded_peak_ids),
                }
                for peak in sorted(all_peaks_dict.values(), key=lambda p: p.index)
            ],
            "breakouts": [
                {
                    "date": bo.date.isoformat(),
                    "price": float(bo.price),
                    "index": int(bo.index),
                    "broken_peak_ids": bo.broken_peak_ids,
                    "superseded_peak_ids": bo.superseded_peak_ids,
                    "num_peaks_broken": int(bo.num_peaks_broken),
                    "breakout_type": bo.breakout_type,
                    "intraday_change_pct": float(bo.intraday_change_pct)
                    if bo.intraday_change_pct
                    else None,
                    "gap_up_pct": float(bo.gap_up_pct)
                    if hasattr(bo, "gap_up_pct") and bo.gap_up_pct
                    else None,
                    "stability_score": float(bo.stability_score)
                    if hasattr(bo, "stability_score") and bo.stability_score
                    else None,
                    "quality_score": float(bo.quality_score)
                    if bo.quality_score
                    else None,
                    # ATR 相关（非注册因子）
                    "atr_value": float(bo.atr_value)
                    if hasattr(bo, "atr_value") and bo.atr_value
                    else None,
                    "atr_normalized_height": float(bo.atr_normalized_height)
                    if hasattr(bo, "atr_normalized_height") and bo.atr_normalized_height
                    else None,
                    "annual_volatility": float(bo.annual_volatility)
                    if hasattr(bo, "annual_volatility") and bo.annual_volatility
                    else None,
                    # 注册因子（从 FACTOR_REGISTRY 动态序列化）
                    **_serialize_factor_fields(bo),
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
            "filtered_breakouts": [
                {
                    "date": info.current_date.isoformat(),
                    "price": float(info.current_price),
                    "index": int(info.current_index),
                    "broken_peak_ids": info.broken_peak_ids,
                    "superseded_peak_ids": info.superseded_peak_ids,
                }
                for info in filtered_infos
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
        breakout_mode='body_top',
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
            breakout_mode: 突破确认模式
            start_date: 起始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            feature_calc_config: FeatureCalculator 配置字典
            scorer_config: 评分器配置字典
            label_max_days: Label 计算所需的最大天数（用于后置缓冲）
            min_price: 突破最低价格（突破当日价格必须 >= min_price）
            max_price: 突破最高价格（突破当日价格必须 <= max_price）
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
        self.breakout_mode = breakout_mode
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
                self.breakout_mode,
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
                    self.breakout_mode,
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
                    "breakout_mode": self.breakout_mode,
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
