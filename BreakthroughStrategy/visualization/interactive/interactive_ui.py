"""交互式UI主窗口"""

import tkinter as tk
from functools import lru_cache
from pathlib import Path
from tkinter import ttk

import pandas as pd

from BreakthroughStrategy.analysis import BreakthroughDetector
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
            self.root.state('zoomed')
        except tk.TclError:
            # Linux/Mac - 使用全屏尺寸
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            self.root.geometry(f"{screen_width}x{screen_height}+0+0")

        self.scan_data = None  # 扫描数据
        self.current_symbol = None  # 当前选中股票

        # 创建UI
        self._create_ui()

    def _create_ui(self):
        """创建UI布局"""
        # 参数面板（顶部）
        self.param_panel = ParameterPanel(
            self.root,
            on_load_callback=self.load_scan_results,
            on_param_changed_callback=self._on_param_changed,
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

        self.chart_manager = ChartCanvasManager(right_frame)

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
        股票选择回调

        Args:
            symbol: 股票代码
            stock_data: 股票数据
        """
        self.current_symbol = symbol
        self.param_panel.set_status(f"Loading {symbol}...", "blue")

        # try:
        # 加载股票数据
        df = self._load_stock_data(symbol)

        # 获取当前参数
        params = self.param_panel.get_params()

        # 运行突破检测
        detector = BreakthroughDetector(
            symbol=symbol,
            window=params["window"],
            exceed_threshold=params["exceed_threshold"],
            use_cache=False,
        )
        breakout_infos = detector.batch_add_bars(df, return_breakouts=True)

        if not breakout_infos:
            self.param_panel.set_status(f"{symbol}: No breakthroughs", "gray")
            # 没有突破时不弹框，只更新状态栏
            return

        # 特征计算和评分
        breakthroughs = self._enrich_breakthroughs(breakout_infos, df, symbol, detector)

        # 更新图表
        self.chart_manager.update_chart(df, breakthroughs, detector, symbol)

        self.param_panel.set_status(
            f"{symbol}: {len(breakthroughs)} breakthrough(s)", "green"
        )

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
