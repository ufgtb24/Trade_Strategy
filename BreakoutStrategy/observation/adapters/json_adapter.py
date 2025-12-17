"""
JSON 扫描结果适配器

将 JSON 格式的扫描结果转换为 Breakout 对象，支持：
- 单股票加载（带时间范围过滤和索引重映射）
- 批量加载（按突破日期分组）
- 与 UI 和观察池系统的无缝集成

核心逻辑提取自 UI/main.py:_load_from_json_cache()
"""
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from BreakoutStrategy.analysis import Breakout, Peak


@dataclass
class LoadResult:
    """单个股票的加载结果"""
    breakouts: List[Breakout]
    active_peaks: List[Peak]  # 活跃峰值列表（用于 UI 绘图）
    peaks: Dict[str, Peak]  # {peak_id: Peak}


class BreakoutJSONAdapter:
    """
    JSON ↔ Breakout 转换适配器

    职责：
    - 从 JSON 扫描结果重建 Peak 和 Breakout 对象
    - 处理时间范围过滤和索引重映射
    - 支持单股票和批量加载

    使用示例：
        adapter = BreakoutJSONAdapter()

        # 单股票加载
        result = adapter.load_single(symbol, stock_data, df)
        breakouts = result.breakouts

        # 批量加载
        breakouts_by_date = adapter.load_batch(json_data, data_dir)
    """

    def __init__(self, detector_params: Optional[dict] = None):
        """
        初始化适配器

        Args:
            detector_params: [DEPRECATED] 不再使用，保留仅为向后兼容
        """
        # detector_params 不再使用，保留参数签名仅为向后兼容
        pass

    def load_single(
        self,
        symbol: str,
        stock_data: dict,
        df: pd.DataFrame,
        rebuild_detector: bool = True,  # DEPRECATED: 保留仅为向后兼容
        scan_start_date: str = None,    # DEPRECATED: 不再使用，JSON 数据已通过检测范围前置限定
        scan_end_date: str = None,      # DEPRECATED: 不再使用，JSON 数据已通过检测范围前置限定
    ) -> LoadResult:
        """
        从 JSON 数据重建单个股票的 Breakout 对象

        注意：JSON 数据已通过检测范围前置限定（detection range pre-limiting）
        在检测阶段正确过滤，无需在此处进行时间范围过滤。

        Args:
            symbol: 股票代码
            stock_data: JSON 中的单个股票数据（已是过滤后的数据）
            df: 该股票的 DataFrame（用于索引映射）
            rebuild_detector: [DEPRECATED] 不再使用，保留仅为向后兼容
            scan_start_date: [DEPRECATED] 不再使用，保留仅为向后兼容
            scan_end_date: [DEPRECATED] 不再使用，保留仅为向后兼容

        Returns:
            LoadResult(breakouts, active_peaks, peaks)
        """
        # 1. 重建 Peak 对象（JSON 数据已是过滤后的，无需时间范围过滤）
        all_peaks = self._rebuild_peaks(stock_data, df)

        # 2. 重建 Breakout 对象
        breakouts = self._rebuild_breakouts(symbol, stock_data, df, all_peaks)

        # 3. 提取活跃峰值
        active_peaks = self._extract_active_peaks(stock_data, all_peaks)

        return LoadResult(
            breakouts=breakouts,
            active_peaks=active_peaks,
            peaks=all_peaks
        )

    def load_batch(
        self,
        json_data: dict,
        data_dir: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Dict[date, List[Breakout]]:
        """
        批量加载 JSON 扫描结果，按突破日期分组

        Args:
            json_data: JSON 数据（包含 results 列表）
            data_dir: PKL 数据目录
            start_date: 可选，过滤起始日期
            end_date: 可选，过滤结束日期

        Returns:
            {date: [Breakout, ...]} 按突破日期分组的结果
        """
        breakouts_by_date: Dict[date, List[Breakout]] = {}
        data_path = Path(data_dir)

        for stock_data in json_data.get("results", []):
            symbol = stock_data.get("symbol")
            if not symbol:
                continue

            # 加载 DataFrame
            df = self._load_dataframe(symbol, data_path, stock_data)
            if df is None or df.empty:
                continue

            # 加载该股票的突破
            result = self.load_single(symbol, stock_data, df, rebuild_detector=False)

            # 按日期分组
            for bo in result.breakouts:
                # 可选的日期过滤
                if start_date and bo.date < start_date:
                    continue
                if end_date and bo.date > end_date:
                    continue

                if bo.date not in breakouts_by_date:
                    breakouts_by_date[bo.date] = []
                breakouts_by_date[bo.date].append(bo)

        return breakouts_by_date

    def load_from_file(
        self,
        json_path: str,
        data_dir: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Dict[date, List[Breakout]]:
        """
        从 JSON 文件加载并转换

        Args:
            json_path: JSON 文件路径
            data_dir: PKL 数据目录
            start_date: 可选，过滤起始日期
            end_date: 可选，过滤结束日期

        Returns:
            {date: [Breakout, ...]} 按突破日期分组的结果
        """
        with open(json_path, 'r') as f:
            json_data = json.load(f)
        return self.load_batch(json_data, data_dir, start_date, end_date)

    # ===== 内部方法 =====

    def _rebuild_peaks(
        self,
        stock_data: dict,
        df: pd.DataFrame,
    ) -> Dict[str, Peak]:
        """
        重建 Peak 对象，处理索引映射

        注意：JSON 数据已通过检测范围前置限定在检测阶段过滤，
        此处无需进行时间范围过滤。

        Args:
            stock_data: JSON 中的单个股票数据（已是过滤后的数据）
            df: DataFrame

        Returns:
            {peak_id: Peak} 字典
        """
        all_peaks = {}

        for peak_data in stock_data.get("all_peaks", []):
            peak_date = datetime.fromisoformat(peak_data["date"]).date()

            # 重新映射索引
            new_index = self._get_df_index(df, peak_date)
            if new_index is None:
                continue

            peak = Peak(
                index=new_index,
                price=peak_data["price"],
                date=peak_date,
                id=peak_data["id"],
                volume_surge_ratio=peak_data.get("volume_surge_ratio", 0.0),
                candle_change_pct=peak_data.get("candle_change_pct", 0.0),
                left_suppression_days=peak_data.get("left_suppression_days", 0),
                right_suppression_days=peak_data.get("right_suppression_days", 0),
                relative_height=peak_data.get("relative_height", 0.0),
            )
            all_peaks[peak.id] = peak

        return all_peaks

    def _rebuild_breakouts(
        self,
        symbol: str,
        stock_data: dict,
        df: pd.DataFrame,
        all_peaks: Dict[str, Peak],
    ) -> List[Breakout]:
        """
        重建 Breakout 对象

        注意：JSON 数据已通过检测范围前置限定在检测阶段过滤，
        此处无需进行时间范围过滤。

        Args:
            symbol: 股票代码
            stock_data: JSON 中的单个股票数据（已是过滤后的数据）
            df: DataFrame
            all_peaks: 已重建的 Peak 字典

        Returns:
            Breakout 列表
        """
        breakouts = []

        for bo_data in stock_data.get("breakouts", []):
            bo_date = datetime.fromisoformat(bo_data["date"]).date()

            # 重建关联的 Peak
            broken_peak_ids = bo_data.get("broken_peak_ids", [])
            broken_peaks = [
                all_peaks[pid] for pid in broken_peak_ids if pid in all_peaks
            ]

            superseded_peak_ids = bo_data.get("superseded_peak_ids", [])
            superseded_peaks = [
                all_peaks[pid] for pid in superseded_peak_ids if pid in all_peaks
            ]

            # 安全检查：如果 broken_peaks 为空，跳过该突破点
            # 注意：在新的检测范围前置限定方案下，这种情况不应发生
            if not broken_peaks:
                continue

            # 重新映射索引
            new_index = self._get_df_index(df, bo_date)
            if new_index is None:
                continue

            # 处理可能为 None 的字段
            bo = Breakout(
                symbol=symbol,
                date=bo_date,
                price=bo_data["price"],
                index=new_index,
                broken_peaks=broken_peaks,
                superseded_peaks=superseded_peaks,
                breakout_type=bo_data.get("breakout_type", "yang"),
                intraday_change_pct=bo_data.get("intraday_change_pct") or 0.0,
                gap_up=(bo_data.get("gap_up_pct") or 0.0) > 0,
                gap_up_pct=bo_data.get("gap_up_pct") or 0.0,
                gap_atr_ratio=bo_data.get("gap_atr_ratio") or 0.0,
                volume_surge_ratio=bo_data.get("volume_surge_ratio") or 0.0,
                momentum=bo_data.get("momentum") or 0.0,
                stability_score=bo_data.get("stability_score") or 0.0,
                quality_score=bo_data.get("quality_score"),
                recent_breakout_count=bo_data.get("recent_breakout_count", 1),
                days_since_last_breakout=bo_data.get("days_since_last_breakout"),
                atr_value=bo_data.get("atr_value") or 0.0,
                atr_normalized_height=bo_data.get("atr_normalized_height") or 0.0,
                daily_return_atr_ratio=bo_data.get("daily_return_atr_ratio") or 0.0,
                pk_momentum=bo_data.get("pk_momentum") or 0.0,
                gain_5d=bo_data.get("gain_5d") or 0.0,
                annual_volatility=bo_data.get("annual_volatility") or 0.0,
            )
            bo.pattern_label = bo_data.get("pattern_label", "basic")
            breakouts.append(bo)

        return breakouts

    def _extract_active_peaks(
        self,
        stock_data: dict,
        all_peaks: Dict[str, Peak]
    ) -> List[Peak]:
        """
        从 JSON 数据提取活跃峰值列表

        Args:
            stock_data: JSON 中的单个股票数据
            all_peaks: 已重建的 Peak 字典

        Returns:
            活跃峰值列表
        """
        active_peaks = [
            peak
            for peak in all_peaks.values()
            if any(
                peak_data.get("id") == peak.id and peak_data.get("is_active", False)
                for peak_data in stock_data.get("all_peaks", [])
            )
        ]
        return active_peaks

    def _get_df_index(self, df: pd.DataFrame, target_date: date) -> Optional[int]:
        """
        将日期映射到 DataFrame 索引

        Args:
            df: DataFrame
            target_date: 目标日期

        Returns:
            索引位置，如果找不到返回 None
        """
        try:
            idx = df.index.get_loc(pd.Timestamp(target_date))

            # get_loc() 可能返回整数、切片或布尔数组
            if isinstance(idx, slice):
                idx = idx.start
            elif hasattr(idx, "__iter__"):
                idx = np.where(idx)[0][0]

            return int(idx)
        except (KeyError, IndexError):
            return None

    def _load_dataframe(
        self,
        symbol: str,
        data_path: Path,
        stock_data: dict
    ) -> Optional[pd.DataFrame]:
        """
        加载股票的 DataFrame

        Args:
            symbol: 股票代码
            data_path: 数据目录
            stock_data: JSON 中的股票数据（包含时间范围）

        Returns:
            DataFrame 或 None
        """
        pkl_path = data_path / f"{symbol}.pkl"
        if not pkl_path.exists():
            return None

        try:
            df = pd.read_pickle(pkl_path)

            # 如果 JSON 中有时间范围，应用过滤
            time_range = stock_data.get("time_range", {})
            if time_range:
                start = time_range.get("start")
                end = time_range.get("end")
                if start:
                    df = df[df.index >= pd.Timestamp(start)]
                if end:
                    df = df[df.index <= pd.Timestamp(end)]

            return df
        except Exception:
            return None
