"""交互式UI主窗口"""

import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import numpy as np
import pandas as pd

from BreakthroughStrategy.analysis import BreakthroughDetector
from BreakthroughStrategy.analysis.breakthrough_detector import Breakthrough, Peak
from BreakthroughStrategy.analysis.breakthrough_scorer import BreakthroughScorer

from .charts import ChartCanvasManager
from .config import get_ui_config_loader, get_ui_scan_config_loader
from .managers import NavigationManager, ScanManager, compute_breakthroughs_from_dataframe
from .panels import ParameterPanel, StockListPanel
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
        self.scan_config_loader = get_ui_scan_config_loader()
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
        self.current_json_path = None  # 当前加载的 JSON 文件路径
        self.current_symbol = None  # 当前选中股票

        # 缓存当前计算结果，用于快速重绘
        self.current_df = None
        self.current_breakthroughs = None
        self.current_detector = None

        # DataFrame缓存：{(symbol, start_date, end_date): DataFrame}
        # 用于支持多时间范围缓存
        self._data_cache = {}

        # 创建UI
        self._create_ui()

    def _create_ui(self):
        """创建UI布局"""
        # 模式指示器（最顶部）
        self._create_mode_indicator()

        # 参数面板（顶部）
        self.param_panel = ParameterPanel(
            self.root,
            on_load_callback=self.load_scan_results,
            on_param_changed_callback=self._on_param_changed,
            on_display_option_changed_callback=self._on_display_option_changed,
            on_rescan_all_callback=self._on_rescan_all_clicked,
            on_new_scan_callback=self._on_new_scan_clicked,
            get_json_params_callback=self._get_scan_data,
        )

        # 主容器（PanedWindow分割）
        self.paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.paned.pack(fill=tk.BOTH, expand=True)

        # 左侧：股票列表容器（初始隐藏）
        self.left_frame = ttk.Frame(self.paned, width=400)
        # 注意：初始不添加到 paned，加载数据后再添加

        self.stock_list_panel = StockListPanel(
            self.left_frame,
            on_selection_callback=self._on_stock_selected,
            on_width_changed_callback=self._on_panel_width_changed,
        )

        # 右侧：图表Canvas（初始占满整个区域）
        self.right_frame = ttk.Frame(self.paned)
        self.paned.add(self.right_frame, weight=1)

        # 使用 UI 参数配置创建评分器
        scorer_cfg = self.param_panel.param_loader.get_scorer_params()
        breakthrough_scorer = BreakthroughScorer(config=scorer_cfg)
        self.chart_manager = ChartCanvasManager(
            self.right_frame,
            breakthrough_scorer=breakthrough_scorer
        )

        # 标记左侧面板是否已显示
        self._left_panel_visible = False

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
            self.current_json_path = json_path  # 保存当前文件路径

            # 清空DataFrame缓存（新JSON可能有不同的时间范围）
            self._data_cache.clear()

            # 加载到股票列表
            self.stock_list_panel.load_data(self.scan_data)

            # 显示左侧面板（如果尚未显示）
            self._show_left_panel()

            # 更新状态（显示文件名）
            total_stocks = self.scan_data["scan_metadata"]["stocks_scanned"]
            total_bts = self.scan_data["summary_stats"]["total_breakthroughs"]
            filename = Path(json_path).name
            self.param_panel.set_status(
                f"Loaded {filename}: {total_stocks} stocks, {total_bts} breakthroughs", "green"
            )

            # 更新模式指示器（显示文件名）
            self._update_mode_indicator()

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

        # 获取该股票的时间范围（优先使用JSON中的记录）
        start_date, end_date = self.config_loader.get_time_range_for_stock(
            symbol, self.scan_data
        )

        # 加载股票数据
        df = self._load_stock_data(symbol, start_date, end_date)
        params = self.param_panel.get_params()

        # 尝试使用JSON缓存（快速路径）
        if self._can_use_json_cache(symbol, params, df):
            # try:
            load_start = time.time()
            breakthroughs, detector = self._load_from_json_cache(symbol, params, df)
            load_end = time.time()
            print(
                f"[UI] JSON cache load time for {symbol}: {load_end - load_start:.6f} seconds"
            )
            self.param_panel.set_status(
                f"{symbol}: Loaded from cache ⚡", "blue", font=("Arial", 15)
            )
            # except Exception as e:stock
            #     # 缓存加载失败，降级到慢速路径
            #     print(
            #         f"[UI] Cache load failed for {symbol}: {e}, falling back to full computation"
            #     )
            #     breakthroughs, detector = self._full_computation(symbol, params, df)
        else:
            # 完整计算（慢速路径）
            load_start = time.time()
            breakthroughs, detector = self._full_computation(symbol, params, df)
            load_end = time.time()
            print(
                f"[UI] Full computation time for {symbol}: {load_end - load_start:.6f} seconds"
            )

            # 区分状态显示
            if self.param_panel.get_use_ui_params():
                self.param_panel.set_status(
                    f"{symbol}: Computed with UI params 🔧",
                    "green",
                    font=("Arial", 15),
                )
            else:
                self.param_panel.set_status(
                    f"{symbol}: Computed (cache unavailable) 🐌", "gray"
                )

        if not breakthroughs:
            self.param_panel.set_status(f"{symbol}: No breakthroughs", "gray")
            # 无突破时也需要隐藏临时行
            self.stock_list_panel.hide_temp_row()
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

        # 计算完成后，检查是否需要显示临时行
        if self.param_panel.get_use_ui_params():
            # Analysis Mode: 计算临时统计量并显示
            label_type = self.stock_list_panel.get_label_type()
            temp_stats = self._calculate_temp_stats(breakthroughs, label_type)
            self.stock_list_panel.show_temp_row(symbol, temp_stats)
        else:
            # Browse Mode: 隐藏临时行
            self.stock_list_panel.hide_temp_row()

    def _full_computation(self, symbol: str, params: dict, df: pd.DataFrame) -> tuple:
        """
        完整计算路径（慢速）- 使用统一函数

        Args:
            symbol: 股票代码
            params: 参数字典
            df: DataFrame

        Returns:
            (breakthroughs, detector) 元组
        """
        # 从 UI 参数加载器获取配置
        feature_cfg = self.param_panel.param_loader.get_feature_calculator_params()
        # 合并 label_configs（从扫描配置获取）
        feature_cfg['label_configs'] = self.scan_config_loader.get_label_configs()
        scorer_cfg = self.param_panel.param_loader.get_scorer_params()

        # 使用统一函数计算突破
        breakthroughs, detector = compute_breakthroughs_from_dataframe(
            symbol=symbol,
            df=df,
            total_window=params["total_window"],
            min_side_bars=params["min_side_bars"],
            min_relative_height=params["min_relative_height"],
            exceed_threshold=params["exceed_threshold"],
            peak_supersede_threshold=params.get("peak_supersede_threshold", 0.03),
            feature_calc_config=feature_cfg,
            scorer_config=scorer_cfg,
        )

        self.param_panel.set_status(
            f"{symbol}: Computed {len(breakthroughs)} breakthrough(s)", "green"
        )

        return breakthroughs, detector

    def _can_use_json_cache(self, symbol: str, params: dict, df: pd.DataFrame) -> bool:
        """
        判断是否可以使用JSON缓存（v3.0优化版）

        新逻辑：
        1. 如果勾选了 "Use UI Params"，强制重新计算
        2. 否则，只要 JSON 存在且时间范围匹配，就使用缓存
        3. 不再检查参数匹配（用户负责确保 JSON 的参数是期望的）

        Args:
            symbol: 股票代码
            params: 参数字典（未使用，保留向后兼容）
            df: DataFrame

        Returns:
            是否可以使用缓存
        """
        # 优先检查复选框状态
        if self.param_panel.get_use_ui_params():
            return False  # 用户强制使用 UI 参数重新扫描

        # 检查 JSON 是否已加载
        if not hasattr(self, "scan_data") or not self.scan_data:
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
                elif hasattr(new_index, "__iter__"):
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
            broken_peaks = [
                all_peaks[pid] for pid in broken_peak_ids if pid in all_peaks
            ]

            # 恢复 superseded_peaks（兼容旧缓存）
            superseded_peak_ids = bt_data.get("superseded_peak_ids", [])
            superseded_peaks = [
                all_peaks[pid] for pid in superseded_peak_ids if pid in all_peaks
            ]

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
                elif hasattr(new_index, "__iter__"):
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
            recent_breakthrough_count = bt_data.get("recent_breakthrough_count", 1)

            bt = Breakthrough(
                symbol=symbol,
                date=bt_date,
                price=bt_data["price"],
                index=new_index,  # 使用重新映射的索引
                broken_peaks=broken_peaks,
                superseded_peaks=superseded_peaks,
                breakthrough_type=bt_data.get("breakthrough_type", "yang"),
                price_change_pct=price_change_pct
                if price_change_pct is not None
                else 0.0,
                gap_up=(gap_up_pct if gap_up_pct is not None else 0.0) > 0,
                gap_up_pct=gap_up_pct if gap_up_pct is not None else 0.0,
                volume_surge_ratio=volume_surge_ratio
                if volume_surge_ratio is not None
                else 0.0,
                continuity_days=continuity_days if continuity_days is not None else 0,
                stability_score=stability_score if stability_score is not None else 0.0,
                quality_score=bt_data.get("quality_score"),
                recent_breakthrough_count=recent_breakthrough_count,
            )
            breakthroughs.append(bt)

        # 3. 重建BreakthroughDetector状态（用于绘图）
        detector = BreakthroughDetector(
            symbol=symbol,
            total_window=params["total_window"],
            min_side_bars=params["min_side_bars"],
            min_relative_height=params["min_relative_height"],
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

    def _load_stock_data(
        self,
        symbol: str,
        start_date: str = None,
        end_date: str = None,
    ) -> pd.DataFrame:
        """
        加载股票数据（支持per-stock时间范围缓存）

        Args:
            symbol: 股票代码
            start_date: 起始日期（来自 JSON 的 per-stock 时间范围）
            end_date: 结束日期（来自 JSON 的 per-stock 时间范围）

        Returns:
            DataFrame
        """
        # 时间范围必须由调用方从 JSON 获取并传入

        # 检查缓存
        cache_key = (symbol, start_date, end_date)
        if cache_key in self._data_cache:
            return self._data_cache[cache_key]

        # 从配置文件获取搜索路径列表
        search_paths = self.config_loader.get_stock_data_search_paths()

        # 按优先级依次尝试
        for path_str in search_paths:
            data_path = Path(path_str) / f"{symbol}.pkl"
            if data_path.exists():
                df = pd.read_pickle(data_path)

                # 数据截取
                if start_date:
                    df = df[df.index >= start_date]
                if end_date:
                    df = df[df.index <= end_date]

                # 缓存并返回
                self._data_cache[cache_key] = df
                return df

        # 如果都找不到，抛出异常
        raise FileNotFoundError(
            f"Data file for {symbol} not found in: {', '.join(search_paths)}"
        )

    def _get_scan_data(self):
        """
        获取当前加载的 scan_data

        用于 Parameter Editor 获取 JSON 参数进行对比显示

        Returns:
            scan_data 字典，如果未加载则返回 None
        """
        return self.scan_data if hasattr(self, 'scan_data') and self.scan_data else None

    def _on_param_changed(self):
        """
        参数变化回调

        双模式设计：
        - Browse Mode: 使用 JSON 缓存，不修改 stock list
        - Analysis Mode: 使用 UI 参数计算，但【不更新 stock list】
          （避免不同股票基于不同参数导致数据混乱）
        """
        # 更新模式指示器
        self._update_mode_indicator()

        # 更新 ChartCanvasManager 的评分器
        scorer_cfg = self.param_panel.param_loader.get_scorer_params()
        self.chart_manager.breakthrough_scorer = BreakthroughScorer(config=scorer_cfg)

        # 模式切换时处理临时行
        if not self.param_panel.get_use_ui_params():
            # 切换到 Browse Mode，隐藏临时行
            self.stock_list_panel.hide_temp_row()

        if not self.current_symbol:
            return  # 没有选中股票，不刷新

        # 重新加载当前股票（触发图表刷新）
        selected_data = self.stock_list_panel.get_selected_symbol()
        if selected_data:
            # 获取原始数据
            for stock in self.stock_list_panel.filtered_data:
                if stock["symbol"] == self.current_symbol:
                    self._on_stock_selected(self.current_symbol, stock["raw_data"])
                    # 【关键改动】Analysis Mode 不再更新 stock list 统计值
                    # 删除原有的 _update_stock_list_statistics() 调用
                    break

    def _update_stock_list_statistics(self, symbol: str, breakthroughs: list):
        """
        更新 StockListPanel 中指定股票的统计信息

        Args:
            symbol: 股票代码
            breakthroughs: 突破列表
        """
        # 计算新的统计信息（与 ScanManager 保持一致）
        quality_scores = [
            bt.quality_score for bt in breakthroughs if bt.quality_score is not None
        ]
        avg_quality = (
            sum(quality_scores) / len(quality_scores) if quality_scores else 0.0
        )
        max_quality = max(quality_scores) if quality_scores else 0.0

        # 更新 StockListPanel 中的数据
        for stock in self.stock_list_panel.stock_data:
            if stock["symbol"] == symbol:
                stock["avg_quality"] = avg_quality
                stock["max_quality"] = max_quality
                stock["total_breakthroughs"] = len(breakthroughs)
                break

        # 同步更新 filtered_data
        for stock in self.stock_list_panel.filtered_data:
            if stock["symbol"] == symbol:
                stock["avg_quality"] = avg_quality
                stock["max_quality"] = max_quality
                stock["total_breakthroughs"] = len(breakthroughs)
                break

        # 刷新显示
        self.stock_list_panel._update_tree()

    def _calculate_temp_stats(self, breakthroughs: list, label_type: str) -> dict:
        """
        从突破点列表计算临时统计量

        Args:
            breakthroughs: 突破点列表
            label_type: 当前选择的 label 类型 ("avg", "max", "best_quality", "latest")

        Returns:
            统计量字典，键名与 Stock List 列名一致
        """
        quality_scores = [
            bt.quality_score for bt in breakthroughs
            if bt.quality_score is not None
        ]

        stats = {
            "avg_quality": sum(quality_scores) / len(quality_scores) if quality_scores else 0.0,
            "max_quality": max(quality_scores) if quality_scores else 0.0,
            "total_breakthroughs": len(breakthroughs),
        }

        # 计算 label 列的临时统计量
        label_stats = self._calculate_label_stats_from_breakthroughs(breakthroughs)
        stats["label"] = label_stats.get(label_type)

        return stats

    def _calculate_label_stats_from_breakthroughs(self, breakthroughs: list) -> dict:
        """
        从 Breakthrough 对象列表计算标签统计量

        Args:
            breakthroughs: Breakthrough 对象列表

        Returns:
            统计量字典: {"avg": float, "max": float, "best_quality": float, "latest": float}
        """
        if not breakthroughs:
            return {}

        # 从 breakthroughs 提取 labels
        valid_labels = []
        for bt in breakthroughs:
            if hasattr(bt, 'labels') and bt.labels:
                # 获取第一个 label key 的值
                label_key = list(bt.labels.keys())[0]
                val = bt.labels.get(label_key)
                if val is not None:
                    valid_labels.append((val, bt.quality_score or 0, bt.date))

        if not valid_labels:
            return {}

        stats = {}
        stats["avg"] = sum(v[0] for v in valid_labels) / len(valid_labels)
        stats["max"] = max(v[0] for v in valid_labels)
        stats["best_quality"] = max(valid_labels, key=lambda x: x[1])[0]
        stats["latest"] = max(valid_labels, key=lambda x: x[2])[0]

        return stats

    def _on_navigation_trigger(self):
        """键盘导航触发图表更新"""
        # 注意：此方法已被 StockListPanel 的选择回调覆盖
        # 保留此方法仅为向后兼容，实际不应被调用
        # 因为 _on_fixed_select/_on_main_select 已经触发了 on_selection_callback
        pass

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

    def _show_left_panel(self):
        """
        显示左侧股票列表面板

        在首次加载数据时调用，将左侧面板添加到 PanedWindow
        """
        if self._left_panel_visible:
            return  # 已经显示，无需重复添加

        # 将左侧面板插入到右侧面板之前（位置 0）
        self.paned.insert(0, self.left_frame, weight=1)

        # 更新右侧面板的权重
        self.paned.pane(self.right_frame, weight=3)

        self._left_panel_visible = True

        # 首次显示后，立即调整宽度（因为之前的回调被跳过了）
        required_width = self.stock_list_panel.calculate_required_width()
        self.root.after(10, lambda: self._adjust_sash_position(required_width))

    def _on_panel_width_changed(self, required_width: int):
        """
        StockListPanel 宽度变化回调

        根据 StockListPanel 的所需宽度，动态调整 PanedWindow 的分割线位置。

        Args:
            required_width: StockListPanel 所需的宽度（像素）
        """
        # 只有当左侧面板可见时才调整
        if not self._left_panel_visible:
            return

        # 使用 after() 延迟执行，确保 PanedWindow 已完成布局
        # 避免初始化时的时序问题
        self.root.after(10, lambda: self._adjust_sash_position(required_width))

    def _adjust_sash_position(self, required_width: int):
        """
        调整 PanedWindow 的分割线位置

        Args:
            required_width: StockListPanel 所需的宽度（像素）
        """
        try:
            # sashpos(0, newpos) - 设置第一个分割线的位置（从左边缘开始的像素数）
            self.paned.sashpos(0, required_width)

            # 强制更新布局
            self.paned.update_idletasks()

        except Exception as e:
            # 静默处理错误（例如窗口未完全初始化时）
            # 可选：启用调试日志
            # print(f"[UI] Failed to adjust sash position: {e}")
            pass

    # ==================== 双模式架构 ====================

    def _create_mode_indicator(self):
        """创建模式指示器（顶部状态栏）"""
        self.mode_indicator_frame = tk.Frame(self.root, height=30)
        self.mode_indicator_frame.pack(fill=tk.X)
        self.mode_indicator_frame.pack_propagate(False)  # 固定高度

        self.mode_indicator_label = tk.Label(
            self.mode_indicator_frame,
            text="",
            font=("Arial", 11),
            anchor="w",
            padx=15,
            pady=5,
        )
        self.mode_indicator_label.pack(fill=tk.BOTH, expand=True)

        # 初始状态：Browse Mode
        self._update_mode_indicator()

    def _update_mode_indicator(self):
        """更新模式指示器显示"""
        mode = self.param_panel.get_mode() if hasattr(self, "param_panel") else "browse"

        # 获取文件名（两种模式都显示）
        filename = self._get_loaded_filename()
        # 使用多个空格分隔模式名和文件名
        separator = "          "  # 10个空格

        if mode == "browse":
            # 黄色背景
            if filename:
                text = f"Browse Mode{separator}{filename}"
            else:
                text = "Browse Mode"
            self.mode_indicator_label.config(
                text=text,
                bg="#FFF3CD",  # 浅黄色
                fg="#856404",
            )
            self.mode_indicator_frame.config(bg="#FFF3CD")
        else:
            # 蓝色背景
            if filename:
                text = f"Analysis Mode{separator}{filename}"
            else:
                text = "Analysis Mode"
            self.mode_indicator_label.config(
                text=text,
                bg="#CCE5FF",  # 浅蓝色
                fg="#004085",
            )
            self.mode_indicator_frame.config(bg="#CCE5FF")

    def _get_loaded_filename(self) -> str:
        """获取当前加载的 JSON 文件名"""
        if hasattr(self, "current_json_path") and self.current_json_path:
            return Path(self.current_json_path).name
        return ""

    def _get_json_params_summary(self) -> str:
        """获取 JSON 参数摘要用于显示"""
        if not hasattr(self, "scan_data") or not self.scan_data:
            return "No data loaded"

        metadata = self.scan_data.get("scan_metadata", {})
        scan_date = metadata.get("scan_date", "Unknown")[:10]  # 只取日期部分
        total_stocks = metadata.get("stocks_scanned", 0)

        # 尝试获取参数文件名（如果有）
        detector_params = metadata.get("detector_params", {})
        if detector_params:
            window = detector_params.get("total_window", "?")
            threshold = detector_params.get("exceed_threshold", "?")
            return f"window={window}, threshold={threshold}, {total_stocks} stocks, {scan_date}"

        return f"{total_stocks} stocks, {scan_date}"

    def _on_rescan_all_clicked(self):
        """Rescan All 按钮点击回调"""
        from tkinter import messagebox

        from .dialogs import RescanModeDialog

        if not hasattr(self, "scan_data") or not self.scan_data:
            messagebox.showwarning("Warning", "No scan results loaded")
            return

        if not self.current_json_path:
            messagebox.showwarning("Warning", "No JSON file path available")
            return

        # 弹出 Rescan 模式选择对话框
        dialog = RescanModeDialog(self.root, self.current_json_path)
        result = dialog.show()

        if not result:
            return  # 用户取消

        mode, filename_or_path = result

        # 启动后台扫描
        if mode == RescanModeDialog.MODE_OVERWRITE:
            # 覆盖模式：使用完整路径作为文件名
            self._start_background_rescan(output_filepath=filename_or_path)
        else:
            # 新建文件模式：使用文件名（不含路径）
            self._start_background_rescan(output_filename=filename_or_path)

    def _on_new_scan_clicked(self):
        """New Scan 按钮点击回调 - 根据 config.yaml 从头扫描"""
        from tkinter import messagebox

        from .dialogs import FilenameDialog

        # 获取扫描配置摘要
        scan_summary = self.scan_config_loader.get_scan_summary()
        scan_mode = self.scan_config_loader.get_scan_mode()

        # 确定股票数量
        if scan_mode == "csv":
            try:
                stock_time_ranges = self.scan_config_loader.load_csv_stock_list()
                stock_count = len(stock_time_ranges)
            except Exception as e:
                messagebox.showerror(
                    "CSV Error",
                    f"Failed to load CSV file:\n{str(e)}\n\n"
                    "Please check Scan Settings.",
                )
                return
        else:
            # 全局模式：扫描 data_dir 中的所有 pkl 文件
            from pathlib import Path

            data_dir = Path(self.scan_config_loader.get_data_dir())
            if not data_dir.exists():
                messagebox.showerror(
                    "Data Directory Error",
                    f"Data directory not found:\n{data_dir}\n\n"
                    "Please check Scan Settings.",
                )
                return

            pkl_files = list(data_dir.glob("*.pkl"))
            stock_count = len(pkl_files)

            if stock_count == 0:
                messagebox.showwarning(
                    "No Data",
                    f"No .pkl files found in:\n{data_dir}",
                )
                return

        # 确认对话框
        result = messagebox.askyesno(
            "New Scan",
            f"Start a new scan with current settings?\n\n"
            f"Configuration: {scan_summary}\n"
            f"Stocks to scan: {stock_count}\n\n"
            "This may take a while. Continue?",
        )

        if not result:
            return

        # 弹出文件命名对话框
        filename_dialog = FilenameDialog(self.root, title="Save New Scan Results")
        filename = filename_dialog.show()

        if not filename:
            return  # 用户取消

        # 启动后台新扫描
        self._start_new_scan(output_filename=filename)

    def _start_background_rescan(
        self, output_filename: str = None, output_filepath: str = None
    ):
        """启动后台批量扫描（使用 config.yaml 的时间范围配置）

        Args:
            output_filename: 输出文件名（不含路径，保存到 output_dir）
            output_filepath: 输出文件完整路径（覆盖模式使用）
        """
        import threading
        from tkinter import messagebox

        # 获取股票列表
        symbols = [
            r["symbol"]
            for r in self.scan_data.get("results", [])
            if "error" not in r
        ]

        if not symbols:
            messagebox.showwarning("Warning", "No valid stocks to scan")
            return

        # 获取当前 UI 参数
        params = self.param_panel.get_params()
        feature_cfg = self.param_panel.param_loader.get_feature_calculator_params()
        # 合并 label_configs（从扫描配置获取）
        feature_cfg['label_configs'] = self.scan_config_loader.get_label_configs()
        scorer_cfg = self.param_panel.param_loader.get_scorer_params()

        # 从 scan_config_loader 获取扫描配置
        scan_mode = self.scan_config_loader.get_scan_mode()
        data_dir = self.scan_config_loader.get_data_dir()
        output_dir = self.scan_config_loader.get_output_dir()
        num_workers = self.scan_config_loader.get_num_workers()

        # 准备时间范围配置
        scan_time_config = {"mode": scan_mode}

        if scan_mode == "csv":
            # CSV 模式：加载每只股票的独立时间范围
            try:
                stock_time_ranges = self.scan_config_loader.load_csv_stock_list()
                scan_time_config["stock_time_ranges"] = stock_time_ranges

                # 过滤 symbols：只保留 CSV 中存在的股票
                csv_symbols = set(stock_time_ranges.keys())
                symbols = [s for s in symbols if s in csv_symbols]

                if not symbols:
                    messagebox.showwarning(
                        "Warning",
                        "No stocks found in both scan results and CSV file"
                    )
                    return

            except Exception as e:
                messagebox.showerror(
                    "CSV Load Error",
                    f"Failed to load CSV file:\n{str(e)}"
                )
                return
        else:
            # 全局时间范围模式
            start_date, end_date = self.scan_config_loader.get_date_range()
            scan_time_config["start_date"] = start_date
            scan_time_config["end_date"] = end_date

        # 禁用 UI 交互
        self.param_panel.rescan_all_btn.config(state="disabled")
        mode_desc = self.scan_config_loader.get_scan_summary()
        self.param_panel.set_status(
            f"Scanning {len(symbols)} stocks ({mode_desc})...", "blue"
        )

        # 创建进度窗口
        self._create_progress_window(len(symbols))

        # 启动后台线程
        thread = threading.Thread(
            target=self._do_background_rescan,
            args=(
                symbols,
                params,
                feature_cfg,
                scorer_cfg,
                data_dir,
                output_dir,
                num_workers,
                scan_time_config,
                output_filename,
                output_filepath,
            ),
            daemon=True,
        )
        thread.start()

    def _start_new_scan(self, output_filename: str = None):
        """启动新扫描（根据 config.yaml 配置从头扫描）

        Args:
            output_filename: 输出文件名（不含路径，保存到 output_dir）
        """
        import threading
        from pathlib import Path
        from tkinter import messagebox

        # 获取扫描配置
        scan_mode = self.scan_config_loader.get_scan_mode()
        data_dir = self.scan_config_loader.get_data_dir()
        output_dir = self.scan_config_loader.get_output_dir()
        num_workers = self.scan_config_loader.get_num_workers()
        max_stocks = self.scan_config_loader.get_max_stocks()

        # 获取 UI 参数
        params = self.param_panel.get_params()
        feature_cfg = self.param_panel.param_loader.get_feature_calculator_params()
        # 合并 label_configs（从扫描配置获取）
        feature_cfg['label_configs'] = self.scan_config_loader.get_label_configs()
        scorer_cfg = self.param_panel.param_loader.get_scorer_params()

        # 准备时间范围配置和股票列表
        scan_time_config = {"mode": scan_mode}

        if scan_mode == "csv":
            # CSV 模式
            stock_time_ranges = self.scan_config_loader.load_csv_stock_list()
            symbols = list(stock_time_ranges.keys())
            scan_time_config["stock_time_ranges"] = stock_time_ranges
        else:
            # 全局模式
            data_dir_path = Path(data_dir)
            symbols = [f.stem for f in data_dir_path.glob("*.pkl")]
            start_date, end_date = self.scan_config_loader.get_date_range()
            scan_time_config["start_date"] = start_date
            scan_time_config["end_date"] = end_date

        # 应用 max_stocks 限制
        if max_stocks and len(symbols) > max_stocks:
            symbols = symbols[:max_stocks]

        if not symbols:
            messagebox.showwarning("Warning", "No stocks to scan")
            return

        # 禁用 UI 交互
        self.param_panel.new_scan_btn.config(state="disabled")
        self.param_panel.rescan_all_btn.config(state="disabled")
        mode_desc = self.scan_config_loader.get_scan_summary()
        self.param_panel.set_status(
            f"New scan: {len(symbols)} stocks ({mode_desc})...", "blue"
        )

        # 创建进度窗口
        self._create_progress_window(len(symbols), title="New Scan")

        # 启动后台线程
        thread = threading.Thread(
            target=self._do_background_rescan,
            args=(
                symbols,
                params,
                feature_cfg,
                scorer_cfg,
                data_dir,
                output_dir,
                num_workers,
                scan_time_config,
                output_filename,
                None,  # output_filepath
            ),
            daemon=True,
        )
        thread.start()

    def _create_progress_window(self, total: int, title: str = "Rescanning..."):
        """创建进度窗口"""
        self.progress_window = tk.Toplevel(self.root)
        self.progress_window.title(title)
        self.progress_window.geometry("400x120")
        self.progress_window.transient(self.root)
        self.progress_window.grab_set()

        # 禁止关闭
        self.progress_window.protocol("WM_DELETE_WINDOW", lambda: None)

        ttk.Label(
            self.progress_window,
            text="Rescanning all stocks with UI parameters...",
            font=("Arial", 12),
        ).pack(pady=15)

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            self.progress_window,
            variable=self.progress_var,
            maximum=total,
            length=350,
        )
        self.progress_bar.pack(pady=5)

        self.progress_label = ttk.Label(
            self.progress_window,
            text=f"0 / {total}",
        )
        self.progress_label.pack(pady=5)

        self._progress_total = total

    def _do_background_rescan(
        self,
        symbols,
        params,
        feature_cfg,
        scorer_cfg,
        data_dir,
        output_dir,
        num_workers,
        scan_time_config,
        output_filename=None,
        output_filepath=None,
    ):
        """后台执行批量扫描（支持两种时间范围模式）

        Args:
            symbols: 股票代码列表
            params: 检测器参数
            feature_cfg: 特征计算器配置
            scorer_cfg: 质量评分器配置
            data_dir: 数据目录
            output_dir: 输出目录
            num_workers: 并行worker数量
            scan_time_config: 扫描时间配置，包含：
                - mode: "csv" 或 "global"
                - stock_time_ranges: CSV模式下的股票时间范围字典
                - start_date/end_date: 全局模式下的时间范围
            output_filename: 输出文件名（不含路径，保存到 output_dir）
            output_filepath: 输出文件完整路径（覆盖模式使用，优先级高于 output_filename）
        """
        from pathlib import Path

        scan_mode = scan_time_config.get("mode", "global")

        if scan_mode == "csv":
            # CSV 模式：每只股票有独立的时间范围
            stock_time_ranges = scan_time_config.get("stock_time_ranges", {})

            # 创建 ScanManager（不设置全局时间范围）
            manager = ScanManager(
                output_dir=output_dir,
                total_window=params["total_window"],
                min_side_bars=params["min_side_bars"],
                min_relative_height=params["min_relative_height"],
                exceed_threshold=params["exceed_threshold"],
                peak_supersede_threshold=params.get("peak_supersede_threshold", 0.03),
                start_date=None,
                end_date=None,
                feature_calc_config=feature_cfg,
                scorer_config=scorer_cfg,
            )

            # 执行扫描（传递 per-stock 时间范围）
            results = manager.parallel_scan(
                symbols,
                data_dir=str(data_dir),
                num_workers=num_workers,
                stock_time_ranges=stock_time_ranges,
            )
        else:
            # 全局时间范围模式
            start_date = scan_time_config.get("start_date")
            end_date = scan_time_config.get("end_date")

            # 创建 ScanManager（使用全局时间范围）
            manager = ScanManager(
                output_dir=output_dir,
                total_window=params["total_window"],
                min_side_bars=params["min_side_bars"],
                min_relative_height=params["min_relative_height"],
                exceed_threshold=params["exceed_threshold"],
                peak_supersede_threshold=params.get("peak_supersede_threshold", 0.03),
                start_date=start_date,
                end_date=end_date,
                feature_calc_config=feature_cfg,
                scorer_config=scorer_cfg,
            )

            # 执行扫描（不传递 per-stock 时间范围）
            results = manager.parallel_scan(
                symbols,
                data_dir=str(data_dir),
                num_workers=num_workers,
            )

        # 保存结果
        if output_filepath:
            # 覆盖模式：直接写入指定的完整路径
            output_file = Path(output_filepath)
            manager._save_results_internal(results, output_file)
        else:
            # 新建文件模式：使用 output_filename 或自动生成
            output_file = manager.save_results(results, filename=output_filename)

        # 回到主线程更新 UI
        self.root.after(0, lambda: self._on_rescan_complete(str(output_file)))

    def _on_rescan_complete(self, output_file: str):
        """扫描完成回调"""
        from tkinter import messagebox

        # 关闭进度窗口
        if hasattr(self, "progress_window") and self.progress_window.winfo_exists():
            self.progress_window.destroy()

        # 恢复 UI 交互
        self.param_panel.new_scan_btn.config(state="normal")
        self.param_panel.rescan_all_btn.config(state="normal")

        # 重新加载结果
        self.load_scan_results(output_file)

        # 切换回 Browse Mode
        self.param_panel.use_ui_params_var.set(False)
        self.param_panel._update_combobox_state()
        self._update_mode_indicator()

        messagebox.showinfo(
            "Scan Complete",
            f"Scan completed successfully.\n\nResults saved to:\n{output_file}",
        )
