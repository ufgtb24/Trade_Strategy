"""
绝对信号批量扫描器

批量扫描股票，返回按信号数量排序的结果。
支持多进程并行扫描。
"""

import pickle
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

from .aggregator import SignalAggregator
from .composite import calculate_amplitude, calculate_signal_freshness
from .factory import (
    calculate_max_buffer_days,
    create_detectors as _create_detectors,
    create_support_analyzer as _create_support_analyzer,
)
from .models import AbsoluteSignal, SignalStats


def scan_single_stock(
    symbol: str,
    df,
    config: dict,
    scan_date: Optional[date] = None,
    skip_validation: bool = False,
) -> Tuple[List[AbsoluteSignal], List[AbsoluteSignal], dict]:
    """
    扫描单个股票的信号（公共 API）

    与批量扫描使用完全相同的检测逻辑，确保结果一致。
    适用于 UI 分析模式的实时计算。

    Args:
        symbol: 股票代码
        df: 股票数据 DataFrame（已加载）
        config: 检测器配置
        scan_date: 扫描截止日期，None 则使用数据末尾
        skip_validation: 跳过数据完整性检查（UI 模式使用）

    Returns:
        (all_signals, filtered_signals, metadata)
        - all_signals: 检测到的所有信号
        - filtered_signals: 在 lookback 窗口内的信号
        - metadata: 包含 cutoff_date, end_date, scan_date_idx 等信息
    """
    if df is None or len(df) == 0:
        return [], [], {"error": "empty data"}

    # 获取 lookback_days
    aggregator_config = config.get("aggregator", {})
    lookback_days = aggregator_config.get("lookback_days", 42)
    buffer_days = calculate_max_buffer_days(config)

    metadata = {
        "lookback_days": lookback_days,
        "buffer_days": buffer_days,
    }

    # 计算 lookback 窗口
    if scan_date is not None:
        mask = df.index.date <= scan_date
        if not mask.any():
            return [], [], {"error": f"scan_date {scan_date} before data start"}

        scan_date_idx = mask.sum() - 1

        if not skip_validation:
            df_start = df.index[0].date()
            df_end = df.index[-1].date()

            # 数据完整性检查
            required_calendar_days = int((lookback_days + buffer_days) / 0.7)
            earliest_required = scan_date - timedelta(days=required_calendar_days)
            if df_start > earliest_required:
                return [], [], {"error": f"data starts too late: {df_start}"}

            stale_days = (scan_date - df_end).days
            if stale_days > 7:
                return [], [], {"error": f"data stale: ended {stale_days} days before scan_date"}

        end_date = df.index[scan_date_idx].date()
        cutoff_idx = max(0, scan_date_idx - lookback_days + 1)
        cutoff_date = df.index[cutoff_idx].date()

        slice_start = max(0, scan_date_idx - lookback_days - buffer_days)
        df_slice = df.iloc[slice_start : scan_date_idx + 1]
    else:
        # 未指定 scan_date，使用数据末尾
        scan_date_idx = len(df) - 1
        if len(df) > lookback_days:
            cutoff_date = df.index[-lookback_days].date()
            cutoff_idx = len(df) - lookback_days
        else:
            cutoff_date = df.index[0].date()
            cutoff_idx = 0
        end_date = df.index[-1].date()

        # 统一使用 scan_date_idx 计算切片范围（与 if 分支一致）
        slice_start = max(0, scan_date_idx - lookback_days - buffer_days)
        df_slice = df.iloc[slice_start : scan_date_idx + 1]

    metadata.update({
        "scan_date_idx": scan_date_idx,
        "cutoff_idx": cutoff_idx,
        "cutoff_date": cutoff_date,
        "end_date": end_date,
        "slice_start": slice_start,
        "df_slice_len": len(df_slice),
    })

    # 检测信号
    all_signals: List[AbsoluteSignal] = []
    detectors = _create_detectors(config)
    for detector in detectors:
        try:
            all_signals.extend(detector.detect(df_slice, symbol))
        except Exception as e:
            print(f"Warning: {symbol} detection error: {e}")

    # 支撑分析（填充 B/D 信号的 support_status）
    support_analyzer = _create_support_analyzer(config)
    if support_analyzer is not None:
        # scan_date_idx 相对于 df_slice 的索引
        slice_scan_idx = len(df_slice) - 1
        support_analyzer.enrich_signals(df_slice, all_signals, slice_scan_idx)

    # 计算 lookback 窗口内价格振幅（用于异常走势检测）
    metadata["amplitude"] = calculate_amplitude(df_slice, lookback_days)

    # 过滤信号
    filtered_signals = [s for s in all_signals if cutoff_date <= s.date <= end_date]

    # 计算信号鲜度并存入 details（聚合器通过 details["freshness"] 读取）
    close_col = "Close" if "Close" in df_slice.columns else "close"
    current_price = df_slice[close_col].iloc[-1]
    for sig in filtered_signals:
        freshness = calculate_signal_freshness(
            sig, df_slice, current_price, end_date
        )
        sig.details["freshness"] = freshness

    return all_signals, filtered_signals, metadata


def _scan_single_stock(
    symbol: str, data_dir: str, config: dict, scan_date: Optional[date] = None
) -> Tuple[List[AbsoluteSignal], List[str], Optional[str], float, Optional[float]]:
    """
    扫描单个股票（worker 函数，用于多进程）

    内部调用 scan_single_stock() 公共 API。

    Args:
        symbol: 股票代码
        data_dir: 数据目录路径
        config: 检测器配置
        scan_date: 扫描截止日期

    Returns:
        (信号列表, 跳过的股票列表, 跳过原因 or None, amplitude, forward_return)
    """
    skipped: List[str] = []

    # 加载数据
    pkl_path = Path(data_dir) / f"{symbol}.pkl"
    if not pkl_path.exists():
        return [], skipped, "file not found", 0.0, None

    try:
        with open(pkl_path, "rb") as f:
            df = pickle.load(f)
    except Exception as e:
        return [], skipped, f"load error: {e}", 0.0, None

    # 调用公共 API
    all_signals, filtered_signals, metadata = scan_single_stock(
        symbol=symbol,
        df=df,
        config=config,
        scan_date=scan_date,
        skip_validation=False,
    )

    if "error" in metadata:
        return [], skipped, metadata["error"], 0.0, None

    # 计算 forward_return（前瞻涨幅）
    forward_return = None
    fr_config = config.get("forward_return")
    if fr_config and fr_config.get("enabled", False) and scan_date is not None:
        fr_days = fr_config.get("days", 42)
        # scan_date 之后的 fr_days 个交易日
        future = df[df.index.date > scan_date].iloc[:fr_days]
        if len(future) < fr_days:
            return [], skipped, "insufficient future data", 0.0, None

        scan_date_idx = metadata.get("scan_date_idx", 0)
        close_col = "Close" if "Close" in df.columns else "close"
        high_col = "High" if "High" in df.columns else "high"
        base_price = df[close_col].iloc[scan_date_idx]
        if base_price > 0:
            forward_return = (future[high_col].max() - base_price) / base_price

    return filtered_signals, skipped, None, metadata.get("amplitude", 0.0), forward_return


class AbsoluteSignalScanner:
    """
    绝对信号批量扫描器

    批量扫描股票，使用 4 种检测器检测信号，
    聚合统计后按信号数量排序返回。

    参数：
        config: 配置字典，包含各检测器参数
    """

    def __init__(self, config: Optional[dict] = None):
        self._config = config if config is not None else {}

        # 初始化聚合器
        aggregator_config = self._config.get("aggregator", {})
        self.aggregator = SignalAggregator(
            lookback_days=aggregator_config.get("lookback_days", 42)
        )

        # 用于存储跳过的股票（检测器内部跳过）
        self._skipped_symbols: List[str] = []
        # 用于存储因数据不完整而跳过的股票 {symbol: reason}
        self._excluded_symbols: dict = {}

    def scan(
        self,
        symbols: List[str],
        data_dir: Path,
        scan_date: Optional[date] = None,
        max_workers: Optional[int] = None,
    ) -> List[SignalStats]:
        """
        并行扫描股票，返回按信号数量排序的结果

        Args:
            symbols: 股票代码列表
            data_dir: 数据目录路径（包含 {symbol}.pkl 文件）
            scan_date: 扫描截止日期，信号窗口为 [scan_date - lookback_days, scan_date]
            max_workers: 最大工作进程数（默认为 CPU 核心数）

        Returns:
            按 signal_count 降序排列的 SignalStats 列表
        """
        if scan_date is None:
            scan_date = date.today()

        all_signals: List[AbsoluteSignal] = []
        all_skipped: List[str] = []
        excluded_symbols: dict = {}
        amplitude_by_symbol: dict = {}
        forward_return_by_symbol: dict = {}
        data_dir_str = str(data_dir)

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    _scan_single_stock, symbol, data_dir_str, self._config, scan_date
                ): symbol
                for symbol in symbols
            }

            for future in as_completed(futures):
                symbol = futures[future]
                try:
                    signals, skipped, skip_reason, amplitude, forward_return = future.result()
                    if skip_reason is not None:
                        excluded_symbols[symbol] = skip_reason
                    else:
                        all_signals.extend(signals)
                        all_skipped.extend(skipped)
                        amplitude_by_symbol[symbol] = amplitude
                        if forward_return is not None:
                            forward_return_by_symbol[symbol] = forward_return
                except Exception as e:
                    print(f"Worker error for {symbol}: {e}")
                    excluded_symbols[symbol] = f"worker error: {e}"

        self._skipped_symbols = all_skipped
        self._excluded_symbols = excluded_symbols

        # 聚合并排序
        results = self.aggregator.aggregate(all_signals, scan_date, amplitude_by_symbol)

        # 注入 forward_return 到 SignalStats
        for stats in results:
            if stats.symbol in forward_return_by_symbol:
                stats.forward_return = forward_return_by_symbol[stats.symbol]

        return results

    def get_skipped_symbols(self) -> List[str]:
        """获取所有被跳过的股票（去重）- 检测器内部跳过"""
        return list(set(self._skipped_symbols))

    def get_excluded_symbols(self) -> dict:
        """获取因数据不完整而被排除的股票及原因"""
        return self._excluded_symbols
