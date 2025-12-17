"""交互式UI主窗口"""

import os
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import numpy as np
import pandas as pd

from BreakoutStrategy.analysis import BreakoutDetector
from BreakoutStrategy.analysis.breakout_detector import Breakout, Peak
from BreakoutStrategy.analysis.breakout_scorer import BreakoutScorer

from .charts import ChartCanvasManager
from .config import get_ui_config_loader, get_ui_scan_config_loader
from .managers import NavigationManager, ScanManager, compute_breakouts_from_dataframe, preprocess_dataframe
from .panels import ParameterPanel, StockListPanel
from .utils import show_error_dialog

# 设置环境变量 DEBUG_VOLUME=1 启用成交量计算调试输出
DEBUG_VOLUME = os.environ.get("DEBUG_VOLUME", "0") == "1"


class InteractiveUI:
    """交互式UI主窗口"""

    def __init__(self, root):
        """
        初始化主窗口

        Args:
            root: Tkinter root窗口
        """
        self.root = root
        self.root.title("Breakout Strategy - Interactive Viewer")

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
        self.current_breakouts = None
        self.current_active_peaks = None  # 活跃峰值列表
        self.current_superseded_peaks = None  # 被新峰值取代的峰值列表

        # DataFrame缓存：{(symbol, start_date, end_date): DataFrame}
        # 用于支持多时间范围缓存
        self._data_cache = {}

        # 观察池管理器（懒加载）
        self._pool_mgr = None

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
            on_add_to_pool_callback=self.add_to_observation_pool,
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
        breakout_scorer = BreakoutScorer(config=scorer_cfg)
        self.chart_manager = ChartCanvasManager(
            self.right_frame,
            breakout_scorer=breakout_scorer
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
            total_bos = self.scan_data["summary_stats"]["total_breakouts"]
            filename = Path(json_path).name
            self.param_panel.set_status(
                f"Loaded {filename}: {total_stocks} stocks, {total_bos} breakouts", "green"
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
        if self._can_use_json_cache(symbol):
            # try:
            load_start = time.time()
            breakouts, active_peaks = self._load_from_json_cache(symbol, df)
            # JSON 缓存不包含 superseded_peaks，使用空列表
            superseded_peaks = []
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
            #     breakouts, active_peaks, superseded_peaks = self._full_computation(symbol, params, df)
        else:
            # 完整计算（慢速路径）
            # 传入 start_date 和 end_date 用于过滤缓冲区内的突破和峰值，确保与 JSON 模式一致
            load_start = time.time()
            breakouts, active_peaks, superseded_peaks = self._full_computation(
                symbol, params, df, start_date=start_date, end_date=end_date
            )
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

        if not breakouts:
            self.param_panel.set_status(f"{symbol}: No breakouts", "gray")
            # 无突破时也需要隐藏临时行
            self.stock_list_panel.hide_temp_row()
            # 继续渲染 K 线图（不 return，允许显示无突破股票的走势）

        # 缓存结果
        self.current_df = df
        self.current_breakouts = breakouts
        self.current_active_peaks = active_peaks
        self.current_superseded_peaks = superseded_peaks

        # 裁剪 df 到显示范围（移除 ATR 缓冲期，保留 Label 缓冲期）
        # 注意：_load_stock_data 添加前后缓冲，图表显示 [start_date, end_date + label_buffer]
        display_df, index_offset, label_buffer_start = self._trim_df_for_display(
            df, start_date, end_date
        )

        # 调整 breakout 和 peak 的 index 以匹配裁剪后的 df
        display_breakouts = self._adjust_breakout_indices(breakouts, index_offset)
        display_active_peaks = self._adjust_peak_indices(active_peaks, index_offset)
        display_superseded_peaks = self._adjust_peak_indices(superseded_peaks, index_offset)

        # 获取显示选项并更新图表
        display_options = self.param_panel.get_display_options()
        self.chart_manager.update_chart(
            display_df, display_breakouts, display_active_peaks,
            display_superseded_peaks, symbol, display_options,
            label_buffer_start_idx=label_buffer_start
        )

        # 计算完成后，检查是否需要显示临时行
        if self.param_panel.get_use_ui_params():
            # Analysis Mode: 计算临时统计量并显示
            label_type = self.stock_list_panel.get_label_type()
            temp_stats = self._calculate_temp_stats(breakouts, label_type)
            self.stock_list_panel.show_temp_row(symbol, temp_stats)
        else:
            # Browse Mode: 隐藏临时行
            self.stock_list_panel.hide_temp_row()

    def _full_computation(
        self, symbol: str, params: dict, df: pd.DataFrame,
        start_date: str = None, end_date: str = None
    ) -> tuple:
        """
        完整计算路径（慢速）- 使用统一函数

        Args:
            symbol: 股票代码
            params: 参数字典
            df: DataFrame
            start_date: 扫描起始日期（用于确定有效检测范围起始索引）
            end_date: 扫描结束日期（用于确定有效检测范围结束索引）

        Returns:
            (breakouts, active_peaks, superseded_peaks) 元组
        """
        # 从 UI 参数加载器获取配置（算法参数）
        feature_cfg = self.param_panel.param_loader.get_feature_calculator_params()
        scorer_cfg = self.param_panel.param_loader.get_scorer_params()

        # 合并 label_configs（扫描参数，始终从 JSON 获取，确保与原始扫描一致）
        label_configs = self.config_loader.get_label_configs_from_json(self.scan_data)
        if label_configs is None:
            # Fallback：如果 JSON 中没有，使用当前配置
            label_configs = self.scan_config_loader.get_label_configs()
        feature_cfg['label_configs'] = label_configs

        # 计算有效检测范围索引（排除 ATR 缓冲区和 Label 缓冲区）
        valid_start_index = 0
        valid_end_index = len(df)

        if start_date:
            scan_start_dt = pd.to_datetime(start_date)
            # 找到第一个 >= scan_start_date 的索引
            mask = df.index >= scan_start_dt
            if mask.any():
                valid_start_index = mask.argmax()

        if end_date:
            scan_end_dt = pd.to_datetime(end_date)
            # 找到最后一个 <= scan_end_date 的索引 + 1
            mask = df.index <= scan_end_dt
            if mask.any():
                # 找到最后一个 True 的位置 + 1
                valid_end_index = mask[::-1].argmax()
                valid_end_index = len(df) - valid_end_index

        # 调试输出：UI 完整计算路径数据预处理详情
        if DEBUG_VOLUME:
            df_start = df.index[0].strftime("%Y-%m-%d") if hasattr(df.index[0], 'strftime') else str(df.index[0])
            df_end = df.index[-1].strftime("%Y-%m-%d") if hasattr(df.index[-1], 'strftime') else str(df.index[-1])
            print(f"[DEBUG_VOLUME][UI_ANALYSIS] symbol={symbol}, "
                  f"scan_range=[{start_date}, {end_date}], "
                  f"df_range=[{df_start}, {df_end}], len(df)={len(df)}, "
                  f"valid_start_index={valid_start_index}, valid_end_index={valid_end_index}")

        # 使用统一函数计算突破（检测范围前置限定）
        breakouts, detector = compute_breakouts_from_dataframe(
            symbol=symbol,
            df=df,
            total_window=params["total_window"],
            min_side_bars=params["min_side_bars"],
            min_relative_height=params["min_relative_height"],
            exceed_threshold=params["exceed_threshold"],
            peak_supersede_threshold=params.get("peak_supersede_threshold", 0.03),
            peak_measure=params.get("peak_measure", "body_top"),
            breakout_modes=params.get("breakout_modes", ["body_top"]),
            feature_calc_config=feature_cfg,
            scorer_config=scorer_cfg,
            valid_start_index=valid_start_index,
            valid_end_index=valid_end_index,
            streak_window=params.get("streak_window", 20),
        )

        # 提取 active_peaks 和 superseded_peaks
        # 注意：峰值和突破已在检测阶段通过 valid_start_index/valid_end_index 过滤，无需事后过滤
        active_peaks = detector.active_peaks if detector else []
        superseded_peaks = detector.superseded_by_new_peak if detector else []

        self.param_panel.set_status(
            f"{symbol}: Computed {len(breakouts)} breakout(s)", "green"
        )

        return breakouts, active_peaks, superseded_peaks

    def _can_use_json_cache(self, symbol: str) -> bool:
        """
        判断是否可以使用JSON缓存

        逻辑：
        1. 如果勾选了 "Use UI Params"，强制重新计算
        2. 否则，只要 JSON 存在该股票数据，就使用缓存

        Args:
            symbol: 股票代码

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

        # 注意：不再检查时间范围
        # 原因：_load_stock_data 会添加 30 天 ATR 缓冲，导致 df.index[0] < scan_start
        # 而 get_time_range_for_stock 返回的时间范围本身就来自 JSON，无需再次验证
        return True

    def _load_from_json_cache(self, symbol: str, df: pd.DataFrame) -> tuple:
        """
        从JSON缓存加载数据，重建对象（使用适配器）

        Args:
            symbol: 股票代码
            df: DataFrame

        Returns:
            (breakouts, active_peaks) 元组

        Raises:
            ValueError: 如果股票数据未找到
        """
        from BreakoutStrategy.observation.adapters import BreakoutJSONAdapter

        # 查找股票数据
        stock_data = None
        for result in self.scan_data.get("results", []):
            if result.get("symbol") == symbol:
                stock_data = result
                break

        if not stock_data:
            raise ValueError(f"Stock {symbol} not found in JSON")

        # 使用适配器加载（不再需要 detector_params）
        adapter = BreakoutJSONAdapter()
        result = adapter.load_single(symbol, stock_data, df)

        return result.breakouts, result.active_peaks

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

                # 数据预处理：截取时间范围 + 计算技术指标（复用 scan_manager 逻辑）
                # 扫描参数（label_max_days）：始终从 JSON 获取，确保与原始扫描一致
                label_max_days = self.config_loader.get_label_max_days_from_json(
                    self.scan_data
                )
                if label_max_days is None:
                    # Fallback：如果 JSON 中没有，使用当前配置
                    label_max_days = self.scan_config_loader.get_label_max_days()
                # 获取技术指标周期（从参数面板配置）
                atr_period = 14  # 默认值
                ma_period = 200  # 默认值
                if hasattr(self, 'param_panel') and self.param_panel:
                    feature_cfg = self.param_panel.param_loader.get_feature_calculator_params()
                    atr_period = feature_cfg.get("atr_period", 14)
                    ma_period = feature_cfg.get("ma_period", 200)
                df = preprocess_dataframe(
                    df,
                    start_date=start_date,
                    end_date=end_date,
                    label_max_days=label_max_days,
                    ma_periods=[ma_period],
                    atr_period=atr_period,
                )

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

    def _trim_df_for_display(
        self, df: pd.DataFrame, start_date: str = None, end_date: str = None
    ) -> tuple:
        """
        裁剪 DataFrame 到显示范围（移除 ATR 缓冲期，保留 Label 缓冲期）

        Args:
            df: 包含缓冲期的 DataFrame
            start_date: 用户配置的起始日期 (YYYY-MM-DD)
            end_date: 用户配置的结束日期 (YYYY-MM-DD)

        Returns:
            (display_df, index_offset, label_buffer_start_idx) 元组
            - display_df: 裁剪后的 DataFrame（包含 Label 缓冲期）
            - index_offset: 前置裁剪掉的行数（用于调整 breakout/peak index）
            - label_buffer_start_idx: Label 缓冲区在 display_df 中的起始索引（用于视觉区分）
        """
        label_buffer_start_idx = None

        # 前置裁剪（移除 ATR 缓冲期）
        if not start_date:
            first_idx = 0
        else:
            start_dt = pd.to_datetime(start_date)
            mask = df.index >= start_dt
            if not mask.any():
                return df, 0, None
            first_idx = mask.argmax()

        # 计算 Label 缓冲区起始位置（end_date 之后的第一个位置）
        if end_date:
            end_dt = pd.to_datetime(end_date)
            # 找到 <= end_date 的最后一个位置（在原 df 中）
            end_mask = df.index <= end_dt
            if end_mask.any():
                # 使用 searchsorted 找到正确位置
                end_positions = df.index.searchsorted(end_dt, side='right')
                if end_positions > first_idx:
                    # Label 缓冲区起始索引（相对于 display_df）
                    label_buffer_start_idx = end_positions - first_idx

        display_df = df.iloc[first_idx:].copy()
        return display_df, first_idx, label_buffer_start_idx

    def _adjust_breakout_indices(self, breakouts: list, offset: int) -> list:
        """
        调整 breakout 对象的 index 以匹配裁剪后的 DataFrame

        Args:
            breakouts: 原始 breakout 列表
            offset: index 偏移量

        Returns:
            调整后的 breakout 列表（浅拷贝，只修改 index）
        """
        if offset == 0:
            return breakouts

        adjusted = []
        for bo in breakouts:
            # 跳过在显示范围之前的 breakout
            if bo.index < offset:
                continue
            # 创建浅拷贝并调整 index
            new_bo = bo.__class__.__new__(bo.__class__)
            new_bo.__dict__.update(bo.__dict__)
            new_bo.index = bo.index - offset
            # 同时调整 broken_peaks 的 index
            if hasattr(new_bo, 'broken_peaks') and new_bo.broken_peaks:
                new_bo.broken_peaks = self._adjust_peak_indices(
                    new_bo.broken_peaks, offset
                )
            adjusted.append(new_bo)
        return adjusted

    def _adjust_peak_indices(self, peaks: list, offset: int) -> list:
        """
        调整 peak 对象的 index 以匹配裁剪后的 DataFrame

        Args:
            peaks: 原始 peak 列表
            offset: index 偏移量

        Returns:
            调整后的 peak 列表（浅拷贝，只修改 index）
        """
        if offset == 0:
            return peaks

        adjusted = []
        for peak in peaks:
            # 跳过在显示范围之前的 peak
            if peak.index < offset:
                continue
            # 创建浅拷贝并调整 index
            new_peak = peak.__class__.__new__(peak.__class__)
            new_peak.__dict__.update(peak.__dict__)
            new_peak.index = peak.index - offset
            adjusted.append(new_peak)
        return adjusted

    def _on_param_changed(self):
        """
        参数变化回调

        双模式设计：
        - Browse Mode: 使用 JSON 缓存，不修改 stock list
        - Analysis Mode: 使用 UI 参数计算，但【不更新 stock list】
          （避免不同股票基于不同参数导致数据混乱）
        """
        # 清空 DataFrame 缓存，确保使用新参数重新预处理数据
        # （因为 atr_period/ma_period 变化会影响 preprocess_dataframe 的结果）
        self._data_cache.clear()

        # 更新模式指示器
        self._update_mode_indicator()

        # 更新 ChartCanvasManager 的评分器
        scorer_cfg = self.param_panel.param_loader.get_scorer_params()
        self.chart_manager.breakout_scorer = BreakoutScorer(config=scorer_cfg)

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

    def _update_stock_list_statistics(self, symbol: str, breakouts: list):
        """
        更新 StockListPanel 中指定股票的统计信息

        Args:
            symbol: 股票代码
            breakouts: 突破列表
        """
        # 计算新的统计信息（与 ScanManager 保持一致）
        quality_scores = [
            bo.quality_score for bo in breakouts if bo.quality_score is not None
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
                stock["total_breakouts"] = len(breakouts)
                break

        # 同步更新 filtered_data
        for stock in self.stock_list_panel.filtered_data:
            if stock["symbol"] == symbol:
                stock["avg_quality"] = avg_quality
                stock["max_quality"] = max_quality
                stock["total_breakouts"] = len(breakouts)
                break

        # 刷新显示
        self.stock_list_panel._update_tree()

    def _calculate_temp_stats(self, breakouts: list, label_type: str) -> dict:
        """
        从突破点列表计算临时统计量

        Args:
            breakouts: 突破点列表
            label_type: 当前选择的 label 类型 ("avg", "max", "best_quality", "latest")

        Returns:
            统计量字典，键名与 Stock List 列名一致
        """
        quality_scores = [
            bo.quality_score for bo in breakouts
            if bo.quality_score is not None
        ]

        stats = {
            "avg_quality": sum(quality_scores) / len(quality_scores) if quality_scores else 0.0,
            "max_quality": max(quality_scores) if quality_scores else 0.0,
            "total_breakouts": len(breakouts),
        }

        # 计算 label 列的临时统计量
        label_stats = self._calculate_label_stats_from_breakouts(breakouts)
        stats["label"] = label_stats.get(label_type)

        return stats

    def _calculate_label_stats_from_breakouts(self, breakouts: list) -> dict:
        """
        从 Breakout 对象列表计算标签统计量

        Args:
            breakouts: Breakout 对象列表

        Returns:
            统计量字典: {"avg": float, "max": float, "best_quality": float, "latest": float}
        """
        if not breakouts:
            return {}

        # 从 breakouts 提取 labels
        valid_labels = []
        for bo in breakouts:
            if hasattr(bo, 'labels') and bo.labels:
                # 获取第一个 label key 的值
                label_key = list(bo.labels.keys())[0]
                val = bo.labels.get(label_key)
                if val is not None:
                    valid_labels.append((val, bo.quality_score or 0, bo.date))

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
            self.current_breakouts,
            self.current_active_peaks,
            self.current_superseded_peaks or [],
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
        """New Scan 按钮点击回调 - 根据 scan_config.yaml 从头扫描"""
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
        """启动后台批量扫描（使用 scan_config.yaml 的时间范围配置）

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
        """启动新扫描（根据 scan_config.yaml 配置从头扫描）

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
                peak_measure=params.get("peak_measure", "body_top"),
                breakout_modes=params.get("breakout_modes", ["body_top"]),
                streak_window=params.get("streak_window", 20),
                start_date=None,
                end_date=None,
                feature_calc_config=feature_cfg,
                scorer_config=scorer_cfg,
                label_max_days=self.scan_config_loader.get_label_max_days(),
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

            # 获取股票筛选条件
            min_price, max_price, min_volume = self.scan_config_loader.get_filter_config()

            # 创建 ScanManager（使用全局时间范围）
            manager = ScanManager(
                output_dir=output_dir,
                total_window=params["total_window"],
                min_side_bars=params["min_side_bars"],
                min_relative_height=params["min_relative_height"],
                exceed_threshold=params["exceed_threshold"],
                peak_supersede_threshold=params.get("peak_supersede_threshold", 0.03),
                peak_measure=params.get("peak_measure", "body_top"),
                breakout_modes=params.get("breakout_modes", ["body_top"]),
                streak_window=params.get("streak_window", 20),
                start_date=start_date,
                end_date=end_date,
                feature_calc_config=feature_cfg,
                scorer_config=scorer_cfg,
                label_max_days=self.scan_config_loader.get_label_max_days(),
                min_price=min_price,
                max_price=max_price,
                min_volume=min_volume,
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

    # ==================== 观察池集成 ====================

    def _get_or_create_pool_manager(self):
        """
        获取或创建观察池管理器（懒加载）

        Returns:
            PoolManager 实例
        """
        if self._pool_mgr is None:
            from datetime import date
            from BreakoutStrategy.observation import create_backtest_pool_manager
            self._pool_mgr = create_backtest_pool_manager(date.today())
        return self._pool_mgr

    def add_to_observation_pool(self):
        """
        将当前股票的突破添加到观察池

        此方法将当前显示的所有突破添加到观察池中，
        用于后续的买入信号评估。
        """
        from tkinter import messagebox

        if not hasattr(self, 'current_breakouts') or not self.current_breakouts:
            self.param_panel.set_status("No breakouts to add", "orange")
            return

        pool_mgr = self._get_or_create_pool_manager()
        added = 0
        for bo in self.current_breakouts:
            if pool_mgr.add_from_breakout(bo):
                added += 1

        # 更新状态
        symbol = self.current_symbol or "Unknown"
        if added > 0:
            self.param_panel.set_status(
                f"Added {added} breakouts from {symbol} to pool", "green"
            )
        else:
            self.param_panel.set_status(
                f"No new breakouts added (may already exist)", "orange"
            )

    def show_pool_status(self):
        """
        显示观察池状态

        在状态栏中显示当前观察池的统计信息。
        """
        pool_mgr = self._get_or_create_pool_manager()

        realtime_count = len(pool_mgr.realtime_pool.get_all('active'))
        daily_count = len(pool_mgr.daily_pool.get_all('active'))
        total = realtime_count + daily_count

        status_msg = f"Pool Status: Realtime={realtime_count}, Daily={daily_count}, Total={total}"
        self.param_panel.set_status(status_msg, "blue")

    def clear_observation_pool(self):
        """
        清空观察池

        移除所有观察池中的条目。
        """
        if self._pool_mgr is None:
            self.param_panel.set_status("Pool is empty", "gray")
            return

        result = self._pool_mgr.clear_all()
        cleared = result['realtime_cleared'] + result['daily_cleared']
        self.param_panel.set_status(f"Cleared {cleared} entries from pool", "green")
