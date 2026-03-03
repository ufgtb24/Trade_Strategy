"""交互式UI主窗口（信号扫描版）"""

import copy
import json
import shutil
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import pandas as pd
import yaml

from .charts import ChartCanvasManager
from .config import get_ui_config_loader
from .dialogs import ScanSettingsDialog
from .editors import SignalConfigEditor
from .managers import SignalScanManager, compute_config_fingerprint
from .panels import DisplayControlBar, ModeIndicator, OutputPanel, ParameterPanel, StockListPanel, SymbolFilterPanel
from .utils import show_error_dialog


class InteractiveUI:
    """交互式UI主窗口（信号扫描版）"""

    def __init__(self, root):
        """初始化主窗口"""
        self.root = root
        self.root.title("Signal Scanner - Interactive Viewer")

        self.config_loader = get_ui_config_loader()
        width, height = self.config_loader.get_window_size()
        self.root.geometry(f"{width}x{height}")

        try:
            self.root.state("zoomed")
        except tk.TclError:
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            self.root.geometry(f"{screen_width}x{screen_height}+0+0")

        # 状态
        self.scan_data = None
        self.current_json_path = None
        self.current_symbol = None
        self._data_cache = {}

        # 配置文件管理
        project_root = self.config_loader.get_project_root()
        self._params_dir = project_root / "configs" / "signals" / "params"
        self._ensure_params_dir()
        self._active_config_path = self._params_dir / "default.yaml"
        self._ui_config = self._load_signal_config_from_path(self._active_config_path)
        self._json_config_fingerprint = None

        # 扫描设置
        self._data_dir = Path(self.config_loader.get_stock_data_dir())
        self._output_dir = Path(self.config_loader.get_scan_results_dir())

        # 从配置加载 scan_date，如果没有保存过则使用今天的日期
        saved_date = self.config_loader.get_scan_date()
        if saved_date:
            from datetime import datetime
            self._scan_date = datetime.strptime(saved_date, "%Y-%m-%d").date()
        else:
            self._scan_date = date.today()

        self._lookback_days = 42  # 信号统计窗口天数

        # 向后兼容：如果配置文件中有 aggregator.lookback_days，使用它作为初始值
        if "aggregator" in self._ui_config:
            legacy_lookback = self._ui_config["aggregator"].get("lookback_days")
            if legacy_lookback:
                self._lookback_days = legacy_lookback

        # 股票过滤配置
        self._filter_config = self.config_loader.get_stock_filter_config()

        # 前瞻涨幅配置
        self._forward_return_config = self.config_loader.get_forward_return_config()

        # 显示配置（独立于信号配置）
        display_config = self.config_loader.get_display_config()
        self._before_months = display_config.get("before_months", 6)
        self._after_months = display_config.get("after_months", 1)

        # 扫描管理器
        self.scan_manager = SignalScanManager(
            on_progress=self._on_scan_progress,
            on_complete=self._on_scan_complete,
            on_error=self._on_scan_error,
        )

        self._create_ui()

    def _ensure_params_dir(self):
        """确保 params 目录存在，不存在时从默认配置复制"""
        if not self._params_dir.exists():
            self._params_dir.mkdir(parents=True, exist_ok=True)
        default_path = self._params_dir / "default.yaml"
        if not default_path.exists():
            source = self._params_dir.parent / "absolute_signals.yaml"
            if source.exists():
                shutil.copy2(source, default_path)

    def _load_signal_config_from_path(self, path: Path) -> dict:
        """从指定路径加载信号配置"""
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        return {}

    def _load_signal_config(self) -> dict:
        """加载信号配置（委托到 _active_config_path）"""
        return self._load_signal_config_from_path(self._active_config_path)

    def _create_ui(self):
        """创建UI布局"""
        # 模式指示器（顶部）
        self.mode_indicator = ModeIndicator(self.root)
        self.mode_indicator.set_active_config(self._active_config_path.name)

        # 参数面板
        self.param_panel = ParameterPanel(
            self.root,
            on_load_callback=self.load_scan_results,
            on_scan_callback=self._on_new_scan_clicked,
            on_edit_config_callback=self._on_edit_config_clicked,
            on_rescan_callback=self._on_rescan_clicked,
            on_settings_callback=self._on_settings_clicked,
            on_mode_changed_callback=self._on_mode_changed,
            on_config_file_changed_callback=self._on_config_file_changed,
        )
        self.param_panel.refresh_config_files(
            self._params_dir, self._active_config_path.name
        )

        # 主容器
        self.paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.paned.pack(fill=tk.BOTH, expand=True)

        # 左侧：股票列表
        self.left_frame = ttk.Frame(self.paned, width=400)
        self.stock_list_panel = StockListPanel(
            self.left_frame,
            on_selection_callback=self._on_stock_selected,
            on_width_changed_callback=self._on_panel_width_changed,
        )

        # 右侧：图表 + 显示控制栏
        self.right_frame = ttk.Frame(self.paned)
        self.paned.add(self.right_frame, weight=1)

        # 图表容器（填充剩余空间）
        self.chart_container = ttk.Frame(self.right_frame)
        self.chart_container.pack(fill=tk.BOTH, expand=True)
        self.chart_manager = ChartCanvasManager(self.chart_container)

        # 底部控制栏容器
        self.bottom_control_frame = ttk.Frame(self.right_frame)
        self.bottom_control_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(5, 5))

        # 符号筛选面板（左侧）
        self._symbol_filter_config = self.config_loader.get_symbol_filter_config()
        self.symbol_filter_panel = SymbolFilterPanel(
            self.bottom_control_frame,
            on_change_callback=self._on_symbol_filter_changed,
            initial_state=self._symbol_filter_config,
        )
        self.symbol_filter_panel.pack(side=tk.LEFT, padx=(10, 20))

        # 显示控制栏（右侧）
        self.display_control_bar = DisplayControlBar(
            self.bottom_control_frame,
            on_change_callback=self._on_display_changed,
            on_lookback_callback=self._on_lookback_changed,
            initial_before=self._before_months,
            initial_after=self._after_months,
            initial_lookback=self._lookback_days,
        )
        self.display_control_bar.pack(side=tk.LEFT, padx=(0, 10))

        self._left_panel_visible = False

        # 输出面板（底部）
        self.output_panel = OutputPanel(self.root, initial_visible=False)

    def load_scan_results(self, json_path: str):
        """加载扫描结果"""
        try:
            self.param_panel.set_status("Loading...", "blue")
            self.output_panel.log(f"Loading {json_path}...")

            with open(json_path, "r", encoding="utf-8") as f:
                self.scan_data = json.load(f)

            # 为 D 信号补充 support_troughs 字段（兼容旧缓存）
            self._ensure_support_troughs(self.scan_data)

            self.current_json_path = json_path
            self._data_cache.clear()

            # 获取 JSON 配置指纹
            metadata = self.scan_data.get("scan_metadata", {})
            self._json_config_fingerprint = metadata.get("config_fingerprint")

            # 更新模式指示器
            filename = Path(json_path).name
            self.mode_indicator.set_json_filename(filename)
            self._update_mode_indicator()

            # 加载到股票列表
            self.stock_list_panel.load_data(self.scan_data)
            self._show_left_panel()

            total_stocks = len(self.scan_data.get("results", []))
            self.param_panel.set_status(
                f"Loaded {filename}: {total_stocks} stocks", "green"
            )
            self.output_panel.log(f"Loaded {total_stocks} stocks", "success")

        except Exception as e:
            self.param_panel.set_status("Load failed", "red")
            self.output_panel.log(f"Load failed: {e}", "error")
            show_error_dialog(
                self.root, "Error", f"Failed to load scan results:\n\n{str(e)}"
            )

    def _ensure_support_troughs(self, scan_data: dict):
        """
        为 D 信号补充 support_troughs 字段（兼容旧缓存），按时间顺序分配股票内局部 ID
        """
        # 每个股票独立处理，ID 从 1 开始
        for result in scan_data.get("results", []):
            all_troughs = []  # [(date_str, index, trough_dict_ref), ...]
            for sig in result.get("signals", []):
                if sig.get("signal_type") != "D":
                    continue
                details = sig.get("details", {})
                # 如果已有 support_troughs 且有 id，跳过该股票
                existing = details.get("support_troughs", [])
                if existing and existing[0].get("id") is not None:
                    continue
                support_status = details.get("support_status", {})
                tests = support_status.get("tests", [])
                if not tests:
                    details["support_troughs"] = []
                    continue
                support_troughs = [t.copy() for t in tests]
                details["support_troughs"] = support_troughs
                for t in support_troughs:
                    all_troughs.append((t.get("date", ""), t.get("index", 0), t))

            # 按时间排序后分配股票内局部 ID
            all_troughs.sort(key=lambda x: (x[0], x[1]))
            for trough_id, (_, _, t_ref) in enumerate(all_troughs, start=1):
                t_ref["id"] = trough_id

    def _on_stock_selected(self, symbol: str, stock_data: dict):
        """股票选择回调"""
        self.current_symbol = symbol
        self.param_panel.set_status(f"Loading {symbol}...", "blue")

        try:
            df = self._load_stock_data(symbol)

            if df is None or df.empty:
                self.param_panel.set_status(f"{symbol}: No data", "orange")
                self.stock_list_panel.hide_temp_row()
                return

            # 使用 JSON 的 scan_date 对齐数据（浏览模式和分析模式统一）
            # 这确保高亮区域与 JSON 中信号的时间窗口一致
            # 同时保留 scan_date 之后的 after_months 数据用于显示
            scan_date = None
            if self.scan_data:
                scan_date_str = self.scan_data.get("scan_metadata", {}).get("scan_date")
                if scan_date_str:
                    from datetime import datetime, timedelta
                    scan_date = datetime.strptime(scan_date_str[:10], "%Y-%m-%d").date()

                    # 计算 after 截止日期（保留 after_months 的数据）
                    after_calendar_days = int(self._after_months * 30) + 10  # buffer
                    after_cutoff = scan_date + timedelta(days=after_calendar_days)

                    # 截取数据：保留到 after 截止日期
                    df = df[df.index.date <= after_cutoff]
                    if df.empty:
                        self.param_panel.set_status(f"{symbol}: No data before scan date", "orange")
                        self.stock_list_panel.hide_temp_row()
                        return

            # 获取显示参数（从实例变量，由 DisplayControlBar 控制）
            lookback_days = self._lookback_days
            before_months = self._before_months
            after_months = self._after_months
            before_days = before_months * 21
            after_days = after_months * 21

            # ===== 基于 scan_date 位置计算 display_df 范围 =====
            # 浏览模式下：scan_date 是锚点，显示 before + lookback + after 区域
            # 分析模式下：df 末尾是锚点（scan_date 为 None）
            if scan_date is not None:
                # 找到 scan_date 在 df 中的索引（最后一个 <= scan_date 的日期）
                scan_date_idx = None
                for i, idx in enumerate(df.index):
                    if idx.date() <= scan_date:
                        scan_date_idx = i
                if scan_date_idx is None:
                    scan_date_idx = len(df) - 1

                # 基于 scan_date 位置计算 display_df 范围
                # 起始：scan_date 前 (before_days + lookback_days) 天
                display_start_idx = max(0, scan_date_idx - before_days - lookback_days + 1)
                # 结束：scan_date 后 after_days 天
                display_end_idx = min(len(df), scan_date_idx + after_days + 1)

                # 检测边界：scan_date 之前 lookback_days（与批量扫描一致）
                detection_end_idx = scan_date_idx
                detection_start_idx = max(0, detection_end_idx - lookback_days + 1)
            else:
                # 分析模式：以 df 末尾为锚点
                display_days = before_days + lookback_days + after_days
                display_start_idx = max(0, len(df) - display_days)
                display_end_idx = len(df)

                # 检测边界：df 末尾
                detection_end_idx = len(df) - 1
                detection_start_idx = max(0, detection_end_idx - lookback_days + 1)

            # 创建 display_df（用于图表显示）
            display_df = df.iloc[display_start_idx:display_end_idx]

            # ===== 检测边界日期（用于信号过滤）=====
            detection_start_date = df.index[detection_start_idx].date()
            detection_end_date = df.index[detection_end_idx].date()

            # 获取信号列表
            if self.param_panel.is_analysis_mode():
                # 分析模式：实时计算，使用与批量扫描一致的 scan_date 截取逻辑
                signals = self._compute_signals_for_stock(symbol, scan_date=scan_date)
            else:
                # 浏览模式：从 JSON 读取
                signals = stock_data.get("signals", [])

            # 过滤信号：只保留检测窗口内的信号（检查上下限）
            from datetime import datetime

            filtered_signals = []
            for sig in signals:
                sig_date_str = sig.get("date")
                if sig_date_str:
                    sig_date = datetime.strptime(sig_date_str, "%Y-%m-%d").date()
                    if detection_start_date <= sig_date <= detection_end_date:
                        filtered_signals.append(sig)

            # ===== 计算高亮索引（基于 scan_date/detection 边界在 display_df 中的相对位置）=====
            # 高亮区域 = lookback 区间 = detection_start ~ detection_end
            # 直接通过索引计算（更高效、更准确）
            highlight_end_idx = detection_end_idx - display_start_idx
            highlight_start_idx = detection_start_idx - display_start_idx

            # 边界检查
            highlight_start_idx = max(0, highlight_start_idx)
            highlight_end_idx = min(len(display_df) - 1, highlight_end_idx)

            # ===== DEBUG: 信号与高亮区域匹配调试 =====
            print("\n" + "=" * 60)
            print(f"DEBUG [{symbol}] Signal/Highlight Alignment (scan_date 锚点版)")
            print("=" * 60)
            print(f"  scan_date: {scan_date} (浏览模式锚点)" if scan_date else "  scan_date: None (分析模式，以df末尾为锚点)")
            print(f"  df length: {len(df)}, date range: {df.index[0].date()} ~ {df.index[-1].date()}")
            print(f"  display_df length: {len(display_df)}, date range: {display_df.index[0].date()} ~ {display_df.index[-1].date()}")
            print(f"  display_start_idx: {display_start_idx}, display_end_idx: {display_end_idx if scan_date else len(df)}")
            print(f"  lookback_days: {lookback_days}, before_days: {before_days}, after_days: {after_days}")
            print(f"  Detection bounds: {detection_start_date} ~ {detection_end_date} (lookback 区间)")
            print(f"  Highlight idx in display_df: [{highlight_start_idx}, {highlight_end_idx}]")
            print(f"  Expected: before={before_days} | lookback={highlight_end_idx - highlight_start_idx + 1} | after={len(display_df) - highlight_end_idx - 1}")
            print(f"  Total signals: {len(signals)}, Filtered signals: {len(filtered_signals)}")

            # 过滤掉的信号
            rejected_signals = [sig for sig in signals if sig not in filtered_signals]
            if rejected_signals and len(rejected_signals) <= 5:
                print(f"  Rejected signals (outside detection):")
                for sig in rejected_signals:
                    print(f"    - {sig.get('date')} {sig.get('signal_type')}")
            elif rejected_signals:
                print(f"  Rejected signals: {len(rejected_signals)} (too many to list)")

            # 保留的信号
            if filtered_signals and len(filtered_signals) <= 5:
                print(f"  Kept signals (inside detection):")
                for sig in filtered_signals:
                    print(f"    - {sig.get('date')} {sig.get('signal_type')}")
            elif filtered_signals:
                print(f"  Kept signals: {len(filtered_signals)} (too many to list)")
                sorted_sigs = sorted(filtered_signals, key=lambda s: s.get('date', ''))
                print(f"    Earliest: {sorted_sigs[0].get('date')} {sorted_sigs[0].get('signal_type')}")
                print(f"    Latest: {sorted_sigs[-1].get('date')} {sorted_sigs[-1].get('signal_type')}")
            print("=" * 60 + "\n")
            # ===== END DEBUG =====

            # 构建 display_options（包含符号筛选配置）
            display_options = {
                "symbol_filter": self._symbol_filter_config,
            }

            self.chart_manager.update_chart(
                df=display_df,
                signals=filtered_signals,
                symbol=symbol,
                display_options=display_options,
                lookback_days=lookback_days,
                before_days=before_months * 21,
                after_days=after_months * 21,
                highlight_start_idx=highlight_start_idx,
                highlight_end_idx=highlight_end_idx,
            )

            # 处理临时统计行
            if self.param_panel.is_analysis_mode():
                temp_stats = self._compute_temp_stats_from_signals(filtered_signals)
                self.stock_list_panel.show_temp_row(symbol, temp_stats)
            else:
                self.stock_list_panel.hide_temp_row()

            signal_count = len(filtered_signals)
            total_signals = len(signals)
            self.param_panel.set_status(
                f"{symbol}: {signal_count}/{total_signals} signals (in lookback)", "green"
            )

        except Exception as e:
            self.param_panel.set_status(f"{symbol}: Error", "red")
            self.output_panel.log(f"Error loading {symbol}: {e}", "error")
            self.stock_list_panel.hide_temp_row()

    def _load_stock_data(self, symbol: str) -> pd.DataFrame:
        """加载股票数据（根据显示配置截取）"""
        if symbol in self._data_cache:
            return self._data_cache[symbol]

        search_paths = self.config_loader.get_stock_data_search_paths()

        for path_str in search_paths:
            data_path = Path(path_str) / f"{symbol}.pkl"
            if data_path.exists():
                df = pd.read_pickle(data_path)

                if "close" not in df.columns and "Close" in df.columns:
                    df = df.rename(
                        columns={
                            "Open": "open",
                            "High": "high",
                            "Low": "low",
                            "Close": "close",
                            "Volume": "volume",
                        }
                    )

                # 计算显示所需天数（使用实例变量，由 DisplayControlBar 控制）
                lookback_days = self._lookback_days
                before_months = self._before_months
                after_months = self._after_months

                # 计算检测缓冲区（使用 factory 统一函数）
                from BreakoutStrategy.signals.factory import calculate_max_buffer_days
                detection_buffer = calculate_max_buffer_days(self._ui_config)

                # 显示天数 = before + lookback + after（每月约21交易日）
                display_days = (
                    before_months * 21 +
                    lookback_days +
                    after_months * 21
                )

                # 总加载天数 = 显示天数 + 检测缓冲区
                total_days = display_days + detection_buffer

                if len(df) > total_days:
                    df = df.iloc[-total_days:]

                self._data_cache[symbol] = df
                return df

        raise FileNotFoundError(
            f"Data file for {symbol} not found in: {', '.join(search_paths)}"
        )

    def _compute_signals_for_stock(self, symbol: str, scan_date: date = None) -> list:
        """使用统一入口计算信号（与批量扫描完全一致）

        调用 scan_single_stock() 公共 API，确保与批量扫描使用相同的检测逻辑。

        Args:
            symbol: 股票代码
            scan_date: 扫描截止日期
        """
        from BreakoutStrategy.signals.scanner import scan_single_stock

        # 加载股票数据
        search_paths = self.config_loader.get_stock_data_search_paths()
        df = None

        for path_str in search_paths:
            data_path = Path(path_str) / f"{symbol}.pkl"
            if data_path.exists():
                df = pd.read_pickle(data_path)
                if "close" not in df.columns and "Close" in df.columns:
                    df = df.rename(
                        columns={
                            "Open": "open",
                            "High": "high",
                            "Low": "low",
                            "Close": "close",
                            "Volume": "volume",
                        }
                    )
                break

        if df is None:
            print(f"Warning: Could not load data for {symbol}")
            return []

        # 注入 lookback_days 到配置（与批量扫描一致）
        config = self._ui_config.copy()
        if "aggregator" not in config:
            config["aggregator"] = {}
        config["aggregator"]["lookback_days"] = self._lookback_days

        # 调用统一入口
        all_signals, filtered_signals, metadata = scan_single_stock(
            symbol=symbol,
            df=df,
            config=config,
            scan_date=scan_date,
            skip_validation=True,  # UI 模式跳过数据完整性检查
        )

        if "error" in metadata:
            print(f"Warning: {symbol} scan error: {metadata['error']}")
            return []

        # 转换为 dict 格式（与原实现保持一致）
        signals_dict = [
            {
                "date": str(s.date),
                "signal_type": s.signal_type.value,
                "price": s.price,
                "details": s.details,
            }
            for s in sorted(filtered_signals, key=lambda x: x.date, reverse=True)
        ]

        # 为 D 信号补充 support_troughs 字段（按时间顺序分配全局 ID）
        all_troughs = []  # [(date_str, index, trough_dict_ref), ...]
        for sig in signals_dict:
            if sig.get("signal_type") != "D":
                continue
            details = sig.get("details", {})
            support_status = details.get("support_status", {})
            tests = support_status.get("tests", [])
            if not tests:
                details["support_troughs"] = []
                continue
            support_troughs = [t.copy() for t in tests]
            details["support_troughs"] = support_troughs
            for t in support_troughs:
                all_troughs.append((t.get("date", ""), t.get("index", 0), t))

        # 按时间排序后分配 ID
        all_troughs.sort(key=lambda x: (x[0], x[1]))
        for trough_id, (_, _, t_ref) in enumerate(all_troughs, start=1):
            t_ref["id"] = trough_id

        return signals_dict

    def _compute_temp_stats_from_signals(self, signals: list) -> dict:
        """从信号列表计算临时统计量（用于分析模式临时行显示）"""
        stats = {
            "signal_count": len(signals),
            "b_count": 0,
            "v_count": 0,
            "y_count": 0,
            "d_count": 0,
        }
        for sig in signals:
            signal_type = sig.get("signal_type", "")
            if signal_type == "B":
                stats["b_count"] += 1
            elif signal_type == "V":
                stats["v_count"] += 1
            elif signal_type == "Y":
                stats["y_count"] += 1
            elif signal_type == "D":
                stats["d_count"] += 1
        return stats

    def _on_new_scan_clicked(self):
        """New Scan 按钮点击"""
        if self.scan_manager.is_scanning():
            messagebox.showwarning("Warning", "Scan already in progress")
            return

        # 询问输出文件名
        default_filename = f"signals_{date.today()}.json"
        output_path = filedialog.asksaveasfilename(
            title="Save Scan Results",
            initialdir=str(self._output_dir),
            initialfile=default_filename,
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
        )

        if not output_path:
            return

        self.param_panel.set_scan_enabled(False)
        self.output_panel.set_visible(True)
        self.output_panel.log("Starting new scan...", "info")

        self.scan_manager.start_scan(
            data_dir=self._data_dir,
            config=self._ui_config,
            output_path=Path(output_path),
            scan_date=self._scan_date,
            lookback_days=self._lookback_days,
            filter_config=self._filter_config,
            forward_return_config=self._forward_return_config,
        )

    def _on_rescan_clicked(self):
        """Rescan All 按钮点击"""
        if not self.scan_data:
            messagebox.showinfo("Info", "No scan results loaded. Use New Scan first.")
            return

        if self.scan_manager.is_scanning():
            messagebox.showwarning("Warning", "Scan already in progress")
            return

        # 使用 UI 配置重新扫描
        result = messagebox.askyesno(
            "Rescan All",
            "This will rescan all stocks with current UI config.\nContinue?",
        )
        if not result:
            return

        # 询问输出文件名
        default_filename = f"signals_{date.today()}_rescan.json"
        output_path = filedialog.asksaveasfilename(
            title="Save Rescan Results",
            initialdir=str(self._output_dir),
            initialfile=default_filename,
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
        )

        if not output_path:
            return

        self.param_panel.set_scan_enabled(False)
        self.param_panel.set_rescan_enabled(False)
        self.output_panel.set_visible(True)
        self.output_panel.log("Starting rescan with UI config...", "info")

        self.scan_manager.start_scan(
            data_dir=self._data_dir,
            config=self._ui_config,
            output_path=Path(output_path),
            scan_date=self._scan_date,
            lookback_days=self._lookback_days,
            filter_config=self._filter_config,
            forward_return_config=self._forward_return_config,
        )

    def _on_edit_config_clicked(self):
        """Edit Config 按钮点击"""
        SignalConfigEditor(
            parent=self.root,
            config_path=self._active_config_path,
            on_apply_callback=self._on_config_applied,
            on_save_as_callback=self._on_config_saved_as,
        )

    def _on_config_file_changed(self, filename: str):
        """下拉菜单切换配置文件回调"""
        new_path = self._params_dir / filename
        if not new_path.exists():
            return
        self._active_config_path = new_path
        self._ui_config = self._load_signal_config_from_path(new_path)
        self._data_cache.clear()
        self.output_panel.log(f"Config switched to: {filename}", "success")

        # 更新模式指示器
        self.mode_indicator.set_active_config(filename)
        self._update_mode_indicator()

        # 如果有选中股票，刷新图表
        if self.current_symbol:
            stock_data = self._get_current_stock_data()
            if stock_data:
                self._on_stock_selected(self.current_symbol, stock_data)

    def _on_config_applied(self, config: dict):
        """配置应用回调"""
        self._ui_config = config
        self._data_cache.clear()  # 清除缓存，因为显示范围可能改变
        self.output_panel.log("Configuration applied (cache cleared)", "success")
        self.output_panel.set_visible(True)
        self._update_mode_indicator()

        # 如果在分析模式且有选中股票，刷新图表
        if self.param_panel.is_analysis_mode() and self.current_symbol:
            stock_data = self._get_current_stock_data()
            if stock_data:
                self._on_stock_selected(self.current_symbol, stock_data)

    def _on_config_saved_as(self, new_path: Path, config: dict):
        """Save As 回调: 更新状态并刷新下拉菜单"""
        self._active_config_path = new_path
        self._ui_config = config
        self._data_cache.clear()

        # 更新模式指示器
        self.mode_indicator.set_active_config(new_path.name)
        self._update_mode_indicator()

        # 刷新下拉菜单并选中新文件
        self.param_panel.refresh_config_files(
            self._params_dir, new_path.name
        )

        self.output_panel.log(f"Config saved as: {new_path.name}", "success")
        self.output_panel.set_visible(True)

    def _on_settings_clicked(self):
        """Settings 按钮点击"""
        ScanSettingsDialog(
            parent=self.root,
            on_save_callback=self._on_settings_saved,
            initial_scan_date=self._scan_date,
            initial_lookback_days=self._lookback_days,
            initial_filter_config=self._filter_config,
            initial_forward_return_config=self._forward_return_config,
        )

    def _on_settings_saved(self, settings: dict):
        """设置保存回调"""
        self._data_dir = Path(settings["data_dir"])
        self._output_dir = Path(settings["output_dir"])
        self._scan_date = settings.get("scan_date")
        self._lookback_days = settings.get("lookback_days", 42)
        self._filter_config = settings.get("filter_config", self._filter_config)
        self._forward_return_config = settings.get("forward_return_config", self._forward_return_config)
        self._data_cache.clear()  # 清除缓存，因为 lookback 可能改变

        # 同步 DisplayControlBar 中的 lookback_days（不触发回调）
        self.display_control_bar.set_lookback_days(self._lookback_days)

        # 持久化 scan_date 到配置
        if self._scan_date:
            self.config_loader.set_scan_date(
                self._scan_date.strftime("%Y-%m-%d")
            )
        else:
            self.config_loader.set_scan_date(None)

        # 持久化 filter_config 到配置
        self.config_loader.set_stock_filter_config(self._filter_config)

        # 持久化 forward_return_config 到配置
        self.config_loader.set_forward_return_config(self._forward_return_config)

        # 显示设置状态
        date_str = str(self._scan_date) if self._scan_date else "auto-infer"
        filter_status = "enabled" if self._filter_config.get("enabled") else "disabled"
        self.output_panel.log(
            f"Settings saved (lookback: {self._lookback_days}d, scan_date: {date_str}, filter: {filter_status})",
            "success",
        )
        self.output_panel.set_visible(True)

        # 如果有选中股票，刷新图表以反映新的 lookback_days
        if self.current_symbol:
            stock_data = self._get_current_stock_data()
            if stock_data:
                self._on_stock_selected(self.current_symbol, stock_data)

    def _on_mode_changed(self, is_analysis_mode: bool):
        """模式切换回调"""
        self._update_mode_indicator()

        # 切换到浏览模式时立即隐藏临时行
        if not is_analysis_mode:
            self.stock_list_panel.hide_temp_row()

        # 如果有选中股票，刷新图表
        if self.current_symbol:
            stock_data = self._get_current_stock_data()
            if stock_data:
                self._on_stock_selected(self.current_symbol, stock_data)

    def _on_display_changed(self, before_months: int, after_months: int):
        """显示范围变化回调"""
        self._before_months = before_months
        self._after_months = after_months

        # 清空数据缓存（因为需要重新加载不同范围的数据）
        self._data_cache.clear()

        # 保存到配置文件
        self.config_loader.set_display_config(before_months, after_months)

        # 刷新当前图表（如有选中股票）
        if self.current_symbol:
            stock_data = self._get_current_stock_data()
            if stock_data:
                self._on_stock_selected(self.current_symbol, stock_data)

    def _on_lookback_changed(self, lookback_days: int):
        """lookback_days 变化回调（触发信号重算，效果等同于配置应用）"""
        self._lookback_days = lookback_days

        # 清空数据缓存
        self._data_cache.clear()

        self.output_panel.log(f"Lookback changed to {lookback_days} days (cache cleared)", "success")
        self.output_panel.set_visible(True)

        # 更新模式指示器（因为 lookback_days 影响配置指纹）
        self._update_mode_indicator()

        # 如果在分析模式且有选中股票，刷新图表（重算信号）
        if self.param_panel.is_analysis_mode() and self.current_symbol:
            stock_data = self._get_current_stock_data()
            if stock_data:
                self._on_stock_selected(self.current_symbol, stock_data)

    def _on_symbol_filter_changed(self, filter_state: dict):
        """符号筛选变化回调"""
        self._symbol_filter_config = filter_state

        # 保存到配置文件
        self.config_loader.set_symbol_filter_config(filter_state)

        # 刷新当前图表（如有选中股票）
        if self.current_symbol:
            stock_data = self._get_current_stock_data()
            if stock_data:
                self._on_stock_selected(self.current_symbol, stock_data)

    def _update_mode_indicator(self):
        """更新模式指示器"""
        is_analysis = self.param_panel.is_analysis_mode()

        if is_analysis:
            self.mode_indicator.set_mode(ModeIndicator.MODE_ANALYSIS)
        else:
            # 检查配置是否匹配
            config_mismatch = False
            if self._json_config_fingerprint:
                # 创建副本，添加 aggregator 以匹配 JSON 结构
                # (扫描时会注入 aggregator.lookback_days 到配置中)
                config_for_compare = copy.deepcopy(self._ui_config)
                config_for_compare["aggregator"] = {"lookback_days": self._lookback_days}
                current_fp = compute_config_fingerprint(config_for_compare)
                config_mismatch = current_fp != self._json_config_fingerprint
            self.mode_indicator.set_mode(ModeIndicator.MODE_BROWSE, config_mismatch)

    def _get_current_stock_data(self) -> dict:
        """获取当前选中股票的数据"""
        if not self.scan_data or not self.current_symbol:
            return {}
        for result in self.scan_data.get("results", []):
            if result.get("symbol") == self.current_symbol:
                return {"signals": result.get("signals", [])}
        return {}

    def _on_scan_progress(self, message: str, level: str):
        """扫描进度回调"""
        self.root.after(0, lambda: self.output_panel.log(message, level))

    def _on_scan_complete(self, scan_data: dict):
        """扫描完成回调"""
        def update():
            self.param_panel.set_scan_enabled(True)
            self.param_panel.set_rescan_enabled(True)
            self.scan_data = scan_data

            # 更新 fingerprint
            metadata = scan_data.get("scan_metadata", {})
            self._json_config_fingerprint = metadata.get("config_fingerprint")

            self.stock_list_panel.load_data(scan_data)
            self._show_left_panel()
            self._update_mode_indicator()

            total = len(scan_data.get("results", []))
            self.param_panel.set_status(f"Scan complete: {total} stocks", "green")

            # 弹出消息框通知用户
            messagebox.showinfo("Scan Complete", f"Scan finished.\n{total} stocks found.")

        self.root.after(0, update)

    def _on_scan_error(self, error_message: str):
        """扫描错误回调"""
        def update():
            self.param_panel.set_scan_enabled(True)
            self.param_panel.set_rescan_enabled(True)
            self.param_panel.set_status("Scan failed", "red")
            messagebox.showerror("Scan Error", error_message)

        self.root.after(0, update)

    def _show_left_panel(self):
        """显示左侧股票列表面板"""
        if self._left_panel_visible:
            return

        self.paned.insert(0, self.left_frame, weight=1)
        self.paned.pane(self.right_frame, weight=3)
        self._left_panel_visible = True

        required_width = self.stock_list_panel.calculate_required_width()
        self.root.after(10, lambda: self._adjust_sash_position(required_width))

    def _on_panel_width_changed(self, required_width: int):
        """StockListPanel 宽度变化回调"""
        if not self._left_panel_visible:
            return
        self.root.after(10, lambda: self._adjust_sash_position(required_width))

    def _adjust_sash_position(self, required_width: int):
        """调整 PanedWindow 的分割线位置"""
        try:
            self.paned.sashpos(0, required_width)
            self.paned.update_idletasks()
        except Exception:
            pass
