"""信号扫描管理器 - 异步执行信号扫描"""

import hashlib
import json
import os
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import yaml


def _make_json_serializable(obj: Any) -> Any:
    """
    递归转换非 JSON 可序列化类型

    处理类型：
    - datetime.date / datetime.datetime -> ISO 字符串
    - numpy.bool_ -> bool
    - numpy.integer -> int
    - numpy.floating -> float
    - numpy.ndarray -> list
    """
    if isinstance(obj, dict):
        return {k: _make_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_make_json_serializable(item) for item in obj]
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, date):
        return obj.isoformat()
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


def compute_config_fingerprint(config: dict) -> str:
    """
    计算配置指纹（用于参数一致性检测）

    Args:
        config: 配置字典

    Returns:
        8 位十六进制指纹
    """
    config_str = json.dumps(config, sort_keys=True, default=str)
    return hashlib.md5(config_str.encode()).hexdigest()[:8]


class SignalScanManager:
    """
    信号扫描管理器

    处理异步扫描执行、进度回调和结果保存。
    """

    def __init__(
        self,
        on_progress: Optional[Callable[[str, str], None]] = None,
        on_complete: Optional[Callable[[dict], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ):
        """
        初始化扫描管理器

        Args:
            on_progress: 进度回调 (message, level)
            on_complete: 完成回调 (scan_data)
            on_error: 错误回调 (error_message)
        """
        self.on_progress = on_progress
        self.on_complete = on_complete
        self.on_error = on_error
        self._scan_thread: Optional[threading.Thread] = None
        self._is_scanning = False

    def is_scanning(self) -> bool:
        """检查是否正在扫描"""
        return self._is_scanning

    def start_scan(
        self,
        data_dir: Path,
        config: dict,
        output_path: Optional[Path] = None,
        max_workers: Optional[int] = None,
        scan_date: Optional[date] = None,
        lookback_days: int = 42,
        filter_config: Optional[Dict] = None,
        forward_return_config: Optional[Dict] = None,
    ):
        """
        启动异步扫描

        Args:
            data_dir: 数据目录
            config: 信号配置
            output_path: 输出 JSON 路径（可选）
            max_workers: 最大工作进程数
            scan_date: 扫描截止日期（可选，None 表示从数据推断）
            lookback_days: 信号统计窗口天数
            filter_config: 股票过滤配置（可选）
            forward_return_config: 前瞻涨幅配置（可选）
        """
        if self._is_scanning:
            if self.on_error:
                self.on_error("Scan already in progress")
            return

        self._is_scanning = True
        self._scan_thread = threading.Thread(
            target=self._scan_worker,
            args=(data_dir, config, output_path, max_workers, scan_date, lookback_days, filter_config, forward_return_config),
            daemon=True,
        )
        self._scan_thread.start()

    def _scan_worker(
        self,
        data_dir: Path,
        config: dict,
        output_path: Optional[Path],
        max_workers: Optional[int],
        scan_date: Optional[date],
        lookback_days: int,
        filter_config: Optional[Dict] = None,
        forward_return_config: Optional[Dict] = None,
    ):
        """扫描工作线程"""
        try:
            import copy
            import pandas as pd
            from BreakoutStrategy.signals import AbsoluteSignalScanner
            from BreakoutStrategy.UI.utils import filter_stocks, compute_entry_date

            # 获取股票列表
            pkl_files = list(data_dir.glob("*.pkl"))
            symbols = [f.stem for f in pkl_files]

            if not symbols:
                raise ValueError(f"No .pkl files found in {data_dir}")

            self._log(f"Found {len(symbols)} stocks in {data_dir}", "info")

            # 确定 scan_date
            if scan_date is not None:
                # 使用用户指定的日期
                self._log(f"Using scan_date: {scan_date} (user specified)", "info")
            else:
                # 从数据中推断（采样前 50 个文件取最新日期）
                scan_date = self._infer_scan_date(data_dir, pkl_files[:50])
                self._log(f"Using scan_date: {scan_date} (inferred from data)", "info")
            self._log(f"Using lookback_days: {lookback_days}", "info")

            # 股票过滤
            if filter_config and filter_config.get("enabled", False):
                entry_date = compute_entry_date(data_dir, scan_date, lookback_days, pkl_files[:10])
                self._log(f"Filtering at entry date {entry_date} (scan_date - {lookback_days} days)...", "info")
                symbols = filter_stocks(
                    symbols=symbols,
                    data_dir=data_dir,
                    entry_date=entry_date,
                    filter_config=filter_config,
                    on_log=self._log,
                )
                if not symbols:
                    raise ValueError("No stocks passed the filter criteria")

            self._log("Starting scan...", "info")

            # 将 lookback_days 注入配置（覆盖任何旧值）
            scan_config = copy.deepcopy(config)
            if "aggregator" not in scan_config:
                scan_config["aggregator"] = {}
            scan_config["aggregator"]["lookback_days"] = lookback_days

            # 注入 forward_return 配置
            if forward_return_config:
                scan_config["forward_return"] = forward_return_config

            # 执行扫描
            scanner = AbsoluteSignalScanner(config=scan_config)

            if max_workers is None:
                max_workers = max(1, os.cpu_count() - 2)

            results = scanner.scan(
                symbols=symbols,
                data_dir=data_dir,
                scan_date=scan_date,
                max_workers=max_workers,
            )

            self._log(f"Scan complete: {len(results)} stocks with signals", "success")

            # 转换为 JSON 格式（使用 scan_config 确保 lookback_days 在 config_snapshot 中）
            scan_data = self._results_to_json(
                results, scan_config, scan_date, len(symbols)
            )

            # 保存到文件
            if output_path:
                self._save_json(scan_data, output_path)
                self._log(f"Saved to {output_path}", "success")

            # 回调完成
            if self.on_complete:
                self.on_complete(scan_data)

        except Exception as e:
            self._log(f"Scan failed: {e}", "error")
            if self.on_error:
                self.on_error(str(e))
        finally:
            self._is_scanning = False

    def _log(self, message: str, level: str = "info"):
        """发送日志消息"""
        if self.on_progress:
            self.on_progress(message, level)

    def _infer_scan_date(self, data_dir: Path, sample_files: list) -> date:
        """
        从数据文件中推断 scan_date

        采样部分文件，取最新的日期作为 scan_date。
        这样可以避免使用 date.today() 导致的时间窗口不匹配问题。

        Args:
            data_dir: 数据目录
            sample_files: 采样的文件列表

        Returns:
            推断出的 scan_date
        """
        import pandas as pd

        latest_dates = []
        for pkl_file in sample_files:
            try:
                df = pd.read_pickle(pkl_file)
                if df is not None and len(df) > 0:
                    latest_dates.append(df.index.max().date())
            except Exception:
                pass

        if latest_dates:
            return max(latest_dates)
        else:
            # 如果无法推断，回退到 today
            return date.today()

    def _results_to_json(
        self,
        results: list,
        config: dict,
        scan_date: date,
        total_stocks: int,
    ) -> dict:
        """
        将扫描结果转换为 JSON 格式

        Args:
            results: SignalStats 列表
            config: 配置字典
            scan_date: 扫描截止日期
            total_stocks: 扫描的股票总数

        Returns:
            JSON 可序列化的字典
        """
        # 构建 metadata
        scan_data = {
            "scan_metadata": {
                "scan_date": str(scan_date),
                "config_fingerprint": compute_config_fingerprint(config),
                "config_snapshot": config,
                "stocks_scanned": total_stocks,
                "total_signals": sum(s.signal_count for s in results),
            },
            "results": [],
        }

        # === 为 D 信号的支撑 trough 分配股票内局部 ID（按时间顺序）===
        # 每个股票独立处理，ID 从 1 开始
        for stats in results:
            all_troughs = []  # [(date_str, index, trough_dict_ref), ...]
            for sig in stats.signals:
                if sig.signal_type.value != "D":
                    continue
                support_status = sig.details.get("support_status", {})
                tests = support_status.get("tests", [])
                if not tests:
                    sig.details["support_troughs"] = []
                    continue
                support_troughs = [t.copy() for t in tests]
                sig.details["support_troughs"] = support_troughs
                for t in support_troughs:
                    all_troughs.append((t.get("date", ""), t.get("index", 0), t))

            # 按时间排序后分配股票内局部 ID
            all_troughs.sort(key=lambda x: (x[0], x[1]))
            for trough_id, (_, _, t_ref) in enumerate(all_troughs, start=1):
                t_ref["id"] = trough_id

        # 转换每个股票结果
        for stats in results:
            # 按类型统计
            b_count = sum(1 for s in stats.signals if s.signal_type.value == "B")
            v_count = sum(1 for s in stats.signals if s.signal_type.value == "V")
            y_count = sum(1 for s in stats.signals if s.signal_type.value == "Y")
            d_count = sum(1 for s in stats.signals if s.signal_type.value == "D")

            result_item = {
                "symbol": stats.symbol,
                "signal_count": stats.signal_count,
                "weighted_sum": _make_json_serializable(stats.weighted_sum),
                "sequence_label": stats.sequence_label,
                "amplitude": round(stats.amplitude, 3),
                "turbulent": bool(stats.turbulent),
                "forward_return": round(stats.forward_return, 4) if stats.forward_return is not None else None,
                "b_count": b_count,
                "v_count": v_count,
                "y_count": y_count,
                "d_count": d_count,
                "latest_signal_date": str(stats.latest_signal_date),
                "latest_price": _make_json_serializable(stats.latest_price),
                "signals": [
                    {
                        "date": str(s.date),
                        "signal_type": s.signal_type.value,
                        "price": _make_json_serializable(s.price),
                        "strength": _make_json_serializable(s.strength),
                        "details": _make_json_serializable(s.details),
                    }
                    for s in stats.signals
                ],
            }
            scan_data["results"].append(result_item)

        return scan_data

    def _save_json(self, data: dict, path: Path):
        """保存 JSON 文件"""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
