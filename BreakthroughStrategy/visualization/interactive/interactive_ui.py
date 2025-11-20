"""交互式UI主窗口"""

import time
import tkinter as tk
from functools import lru_cache
from pathlib import Path
from tkinter import ttk

import numpy as np
import pandas as pd

from BreakthroughStrategy.analysis import BreakthroughDetector
from BreakthroughStrategy.analysis.breakthrough_detector import Breakthrough, Peak
from BreakthroughStrategy.analysis.features import FeatureCalculator
from BreakthroughStrategy.analysis.quality_scorer import QualityScorer

from .chart_canvas_manager import ChartCanvasManager
from .navigation_manager import NavigationManager
from .parameter_panel import ParameterPanel
from .scan_manager import ScanManager
from .stock_list_panel import StockListPanel
from .ui_config_loader import get_ui_config_loader
from .utils import show_error_dialog


class InteractiveUI:
    """交互式UI主窗口"""

    def __init__(self, root):
        """
        初始化主窗口

        Args:
            root: Tkinter root窗口
        """
        self.root = root
        self.root.title("Breakthrough Strategy - Interactive Viewer")

        # 从配置文件加载窗口大小
        self.config_loader = get_ui_config_loader()
        width, height = self.config_loader.get_window_size()
        self.root.geometry(f"{width}x{height}")

        # 启动时窗口最大化（跨平台兼容）
        try:
            # Windows
            self.root.state("zoomed")
        except tk.TclError:
            # Linux/Mac - 使用全屏尺寸
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            self.root.geometry(f"{screen_width}x{screen_height}+0+0")

        self.scan_data = None  # 扫描数据
        self.current_symbol = None  # 当前选中股票

        # 缓存当前计算结果，用于快速重绘
        self.current_df = None
        self.current_breakthroughs = None
        self.current_detector = None

        # 创建UI
        self._create_ui()

    def _create_ui(self):
        """创建UI布局"""
        # 参数面板（顶部）
        self.param_panel = ParameterPanel(
            self.root,
            on_load_callback=self.load_scan_results,
            on_param_changed_callback=self._on_param_changed,
            on_display_option_changed_callback=self._on_display_option_changed,
        )

        # 主容器（PanedWindow分割）
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # 左侧：股票列表（30%宽度）
        left_frame = ttk.Frame(paned, width=400)
        paned.add(left_frame, weight=1)

        self.stock_list_panel = StockListPanel(
            left_frame, on_selection_callback=self._on_stock_selected
        )

        # 右侧：图表Canvas（70%宽度）
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=3)

        self.chart_manager = ChartCanvasManager(
            right_frame, ui_config=self.config_loader.get_all_config()
        )

        # 键盘导航管理器
        self.navigation_manager = NavigationManager(
            self.root, self.stock_list_panel.fixed_tree, self._on_navigation_trigger
        )

        # 不显示欢迎信息，让右侧保持空白（为K线图预留空间）

    def load_scan_results(self, json_path: str):
        """
        加载扫描结果

        Args:
            json_path: JSON文件路径
        """
        try:
            self.param_panel.set_status("Loading...", "blue")

            # 使用ScanManager加载
            manager = ScanManager()
            self.scan_data = manager.load_results(json_path)

            # 加载到股票列表
            self.stock_list_panel.load_data(self.scan_data)

            # 更新状态
            total_stocks = self.scan_data["scan_metadata"]["stocks_scanned"]
            total_bts = self.scan_data["summary_stats"]["total_breakthroughs"]
            self.param_panel.set_status(
                f"Loaded {total_stocks} stocks, {total_bts} breakthroughs", "green"
            )

            # 成功时不弹框，只更新状态栏

        except Exception as e:
            self.param_panel.set_status("Load failed", "red")
            # 失败时显示大字体错误对话框
            show_error_dialog(
                self.root,
                "Error",
                f"Failed to load scan results:\n\n{str(e)}",
                font_size=16,
            )

    def _on_stock_selected(self, symbol: str, stock_data: dict):
        """
        股票选择回调（优化版：双路径加载）

        Args:
            symbol: 股票代码
            stock_data: 股票数据
        """
        self.current_symbol = symbol
        self.param_panel.set_status(f"Loading {symbol}...", "blue")

        # 加载股票数据
        df = self._load_stock_data(symbol)
        params = self.param_panel.get_params()

        # 尝试使用JSON缓存（快速路径）
        if self._can_use_json_cache(symbol, params, df):
            # try:
            load_start=time.time()
            breakthroughs, detector = self._load_from_json_cache(symbol, params, df)
            load_end=time.time()
            print(f"[UI] JSON cache load time for {symbol}: {load_end - load_start:.6f} seconds")
            self.param_panel.set_status(f"{symbol}: Loaded from cache ⚡", "blue")
            # except Exception as e:
            #     # 缓存加载失败，降级到慢速路径
            #     print(
            #         f"[UI] Cache load failed for {symbol}: {e}, falling back to full computation"
            #     )
            #     breakthroughs, detector = self._full_computation(symbol, params, df)
        else:
            # 完整计算（慢速路径）
            load_start=time.time()
            breakthroughs, detector = self._full_computation(symbol, params, df)
            load_end=time.time()
            print(f"[UI] Full computation time for {symbol}: {load_end - load_start:.6f} seconds")

        if not breakthroughs:
            self.param_panel.set_status(f"{symbol}: No breakthroughs", "gray")
            return

        # 缓存结果
        self.current_df = df
        self.current_breakthroughs = breakthroughs
        self.current_detector = detector

        # 获取显示选项并更新图表
        display_options = self.param_panel.get_display_options()
        self.chart_manager.update_chart(
            df, breakthroughs, detector, symbol, display_options
        )

    def _full_computation(self, symbol: str, params: dict, df: pd.DataFrame) -> tuple:
        """
        完整计算路径（慢速）

        Args:
            symbol: 股票代码
            params: 参数字典
            df: DataFrame

        Returns:
            (breakthroughs, detector) 元组
        """
        # 运行突破检测
        detector = BreakthroughDetector(
            symbol=symbol,
            window=params["window"],
            exceed_threshold=params["exceed_threshold"],
            use_cache=False,
        )
        breakout_infos = detector.batch_add_bars(df, return_breakouts=True)

        if not breakout_infos:
            return [], detector

        # 特征计算和评分
        breakthroughs = self._enrich_breakthroughs(breakout_infos, df, symbol, detector)

        self.param_panel.set_status(
            f"{symbol}: Computed {len(breakthroughs)} breakthrough(s)", "green"
        )

        return breakthroughs, detector

    def _can_use_json_cache(self, symbol: str, params: dict, df: pd.DataFrame) -> bool:
        """
        判断是否可以使用JSON缓存（优化版）

        条件：
        1. 已加载JSON数据
        2. 参数匹配（window, exceed_threshold, peak_merge_threshold）
        3. UI时间范围包含于JSON扫描范围（df_range ⊆ json_range）

        Args:
            symbol: 股票代码
            params: 参数字典
            df: DataFrame

        Returns:
            是否可以使用缓存
        """
        if not hasattr(self, "scan_data") or not self.scan_data:
            return False

        metadata = self.scan_data.get("scan_metadata", {})

        # 检查参数匹配
        if (
            metadata.get("window") != params["window"]
            or abs(metadata.get("exceed_threshold") - params["exceed_threshold"]) > 1e-6
            or abs(
                metadata.get("peak_merge_threshold", 0.03)
                - params.get("peak_merge_threshold", 0.03)
            )
            > 1e-6
        ):
            return False

        # 查找该股票的数据
        stock_data = None
        for result in self.scan_data.get("results", []):
            if result.get("symbol") == symbol:
                stock_data = result
                break

        if not stock_data:
            return False

        # 检查时间范围（UI范围必须包含于JSON范围）
        scan_start = pd.to_datetime(stock_data.get("scan_start_date"))
        scan_end = pd.to_datetime(stock_data.get("scan_end_date"))
        df_start = df.index[0]
        df_end = df.index[-1]

        # UI范围必须完全包含在JSON范围内
        if df_start < scan_start or df_end > scan_end:
            return False

        return True

    def _load_from_json_cache(
        self, symbol: str, params: dict, df: pd.DataFrame
    ) -> tuple:
        """
        从JSON缓存加载数据，重建对象（优化版：支持时间范围过滤和索引重映射）

        Args:
            symbol: 股票代码
            params: 参数字典
            df: DataFrame

        Returns:
            (breakthroughs, detector) 元组

        Raises:
            ValueError: 如果股票数据未找到
        """
        from datetime import datetime

        # 查找股票数据
        stock_data = None
        for result in self.scan_data.get("results", []):
            if result.get("symbol") == symbol:
                stock_data = result
                break

        if not stock_data:
            raise ValueError(f"Stock {symbol} not found in JSON")

        # 获取 UI 的时间范围
        df_start = df.index[0].date()
        df_end = df.index[-1].date()

        # 1. 重建Peak对象，过滤时间范围外的峰值，并重新映射索引
        all_peaks = {}
        for peak_data in stock_data.get("all_peaks", []):
            peak_date = datetime.fromisoformat(peak_data["date"]).date()

            # 过滤：只保留在 UI 时间范围内的峰值
            if not (df_start <= peak_date <= df_end):
                continue

            # 重新映射索引：根据日期在新 DataFrame 中查找位置
            try:
                new_index = df.index.get_loc(pd.Timestamp(peak_date))
                # get_loc() 可能返回整数、切片或布尔数组，需要处理
                if isinstance(new_index, slice):
                    # 如果是切片，取第一个索引
                    new_index = new_index.start
                elif hasattr(new_index, '__iter__'):
                    # 如果是数组/列表，取第一个 True 的位置
                    new_index = np.where(new_index)[0][0]
                # 确保是整数类型
                new_index = int(new_index)
            except (KeyError, IndexError):
                # 如果精确日期不存在或无法转换，跳过该峰值
                continue

            peak = Peak(
                index=new_index,  # 使用重新映射的索引
                price=peak_data["price"],
                date=peak_date,
                id=peak_data["id"],  # ID 保持不变
                volume_surge_ratio=peak_data.get("volume_surge_ratio", 0.0),
                candle_change_pct=peak_data.get("candle_change_pct", 0.0),
                left_suppression_days=peak_data.get("left_suppression_days", 0),
                right_suppression_days=peak_data.get("right_suppression_days", 0),
                relative_height=peak_data.get("relative_height", 0.0),
                quality_score=peak_data.get("quality_score"),
            )
            all_peaks[peak.id] = peak

        # 2. 重建Breakthrough对象，过滤时间范围外的突破点，并重新映射索引
        breakthroughs = []
        for bt_data in stock_data.get("breakthroughs", []):
            bt_date = datetime.fromisoformat(bt_data["date"]).date()

            # 过滤：只保留在 UI 时间范围内的突破点
            if not (df_start <= bt_date <= df_end):
                continue

            # 过滤：只保留 broken_peaks 中仍然存在的峰值（已通过时间范围过滤）
            broken_peak_ids = bt_data["broken_peak_ids"]
            broken_peaks = [all_peaks[pid] for pid in broken_peak_ids if pid in all_peaks]

            # 如果所有 broken_peaks 都被过滤掉了，跳过该突破点
            if not broken_peaks:
                continue

            # 重新映射索引：根据日期在新 DataFrame 中查找位置
            try:
                new_index = df.index.get_loc(pd.Timestamp(bt_date))
                # get_loc() 可能返回整数、切片或布尔数组，需要处理
                if isinstance(new_index, slice):
                    # 如果是切片，取第一个索引
                    new_index = new_index.start
                elif hasattr(new_index, '__iter__'):
                    # 如果是数组/列表，取第一个 True 的位置
                    new_index = np.where(new_index)[0][0]
                # 确保是整数类型
                new_index = int(new_index)
            except (KeyError, IndexError):
                # 如果精确日期不存在或无法转换，跳过该突破点
                continue

            # 处理可能为 None 的字段
            price_change_pct = bt_data.get("price_change_pct")
            gap_up_pct = bt_data.get("gap_up_pct")
            volume_surge_ratio = bt_data.get("volume_surge_ratio")
            continuity_days = bt_data.get("continuity_days")
            stability_score = bt_data.get("stability_score")

            bt = Breakthrough(
                symbol=symbol,
                date=bt_date,
                price=bt_data["price"],
                index=new_index,  # 使用重新映射的索引
                broken_peaks=broken_peaks,
                breakthrough_type=bt_data.get("breakthrough_type", "yang"),
                price_change_pct=price_change_pct if price_change_pct is not None else 0.0,
                gap_up=(gap_up_pct if gap_up_pct is not None else 0.0) > 0,
                gap_up_pct=gap_up_pct if gap_up_pct is not None else 0.0,
                volume_surge_ratio=volume_surge_ratio if volume_surge_ratio is not None else 0.0,
                continuity_days=continuity_days if continuity_days is not None else 0,
                stability_score=stability_score if stability_score is not None else 0.0,
                quality_score=bt_data.get("quality_score"),
            )
            breakthroughs.append(bt)

        # 3. 重建BreakthroughDetector状态（用于绘图）
        detector = BreakthroughDetector(
            symbol=symbol,
            window=params["window"],
            exceed_threshold=params["exceed_threshold"],
            use_cache=False,
        )

        # 恢复active_peaks（根据is_active标记，同时过滤时间范围）
        active_peaks = [
            peak
            for peak in all_peaks.values()
            if any(
                pd.get("id") == peak.id and pd.get("is_active", False)
                for pd in stock_data.get("all_peaks", [])
            )
        ]
        detector.active_peaks = active_peaks

        return breakthroughs, detector

    @lru_cache(maxsize=10)
    def _load_stock_data(self, symbol: str) -> pd.DataFrame:
        """
        加载股票数据（带LRU缓存）

        Args:
            symbol: 股票代码

        Returns:
            DataFrame
        """
        # 从配置文件获取搜索路径列表
        search_paths = self.config_loader.get_stock_data_search_paths()

        # 按优先级依次尝试
        for path_str in search_paths:
            data_path = Path(path_str) / f"{symbol}.pkl"
            if data_path.exists():
                df = pd.read_pickle(data_path)

                # 获取数据截取配置
                start_date, end_date = self.config_loader.get_date_range()

                # 数据截取
                if start_date:
                    df = df[df.index >= start_date]
                if end_date:
                    df = df[df.index <= end_date]

                return df

        # 如果都找不到，抛出异常
        raise FileNotFoundError(
            f"Data file for {symbol} not found in: {', '.join(search_paths)}"
        )

    def _enrich_breakthroughs(self, breakout_infos, df, symbol, detector):
        """
        丰富突破数据（特征计算和质量评分）

        Args:
            breakout_infos: 原始突破信息
            df: 数据
            symbol: 股票代码
            detector: 检测器

        Returns:
            丰富后的突破列表
        """
        feature_calc = FeatureCalculator()
        quality_scorer = QualityScorer()

        breakthroughs = []
        for info in breakout_infos:
            # 为峰值评分
            for peak in info.broken_peaks:
                if peak.quality_score is None:
                    quality_scorer.score_peak(peak)

            # 特征计算
            bt = feature_calc.enrich_breakthrough(df, info, symbol)
            breakthroughs.append(bt)

        # 批量评分
        quality_scorer.score_breakthroughs_batch(breakthroughs)

        # 为检测器的活跃峰值评分
        if detector and hasattr(detector, "active_peaks"):
            for peak in detector.active_peaks:
                if peak.quality_score is None:
                    quality_scorer.score_peak(peak)

        return breakthroughs

    def _on_param_changed(self):
        """参数变化回调"""
        if not self.current_symbol:
            return  # 没有选中股票，不刷新

        # 重新加载当前股票（触发图表刷新）
        selected_data = self.stock_list_panel.get_selected_symbol()
        if selected_data:
            # 获取原始数据
            for stock in self.stock_list_panel.filtered_data:
                if stock["symbol"] == self.current_symbol:
                    self._on_stock_selected(self.current_symbol, stock["raw_data"])
                    break

    def _on_navigation_trigger(self):
        """键盘导航触发图表更新"""
        # 获取当前选中的股票
        selection = self.stock_list_panel.fixed_tree.selection()
        if not selection:
            return

        symbol = selection[0]

        # 找到对应的原始数据
        for stock in self.stock_list_panel.filtered_data:
            if stock["symbol"] == symbol:
                self._on_stock_selected(symbol, stock["raw_data"])
                break

    def _on_display_option_changed(self):
        """显示选项变化回调（只重绘，不重新计算）"""
        if not self.current_symbol or self.current_df is None:
            return

        # 获取显示选项
        display_options = self.param_panel.get_display_options()

        # 使用缓存的数据更新图表
        self.chart_manager.update_chart(
            self.current_df,
            self.current_breakthroughs,
            self.current_detector,
            self.current_symbol,
            display_options,
        )
