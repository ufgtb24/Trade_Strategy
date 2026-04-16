"""LiveApp 主协调器。"""

import sys
import threading
import tkinter as tk
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import messagebox, ttk

import pandas as pd

from BreakoutStrategy.analysis.scanner import preprocess_dataframe
from BreakoutStrategy.live.chart_adapter import adapt_breakout, adapt_peaks
from BreakoutStrategy.UI.charts.range_utils import (
    ChartRangeSpec,
    trim_df_to_display,
    adjust_indices,
)
from BreakoutStrategy.live.config import LiveConfig
from BreakoutStrategy.live.dialogs.progress_dialog import ProgressDialog
from BreakoutStrategy.live.dialogs.update_confirm import confirm_update
from BreakoutStrategy.live.panels.detail_panel import DetailPanel
from BreakoutStrategy.live.panels.match_list import MatchList
from BreakoutStrategy.live.panels.toolbar import Toolbar
from BreakoutStrategy.live.pipeline.daily_runner import DailyPipeline, PipelineProgress
from BreakoutStrategy.live.pipeline.freshness import DataFreshnessChecker
from BreakoutStrategy.live.pipeline.results import (
    CachedResults,
    MatchedBreakout,
    load_cached_results,
    save_cached_results,
)
from BreakoutStrategy.live.pipeline.trial_loader import TrialBundle, TrialLoader
from BreakoutStrategy.live.state import AppState
from BreakoutStrategy.UI.charts.canvas_manager import ChartCanvasManager


class LiveApp:
    """实盘 UI 主应用类。"""

    def __init__(self, root: tk.Tk, config: LiveConfig):
        self.root = root
        self.config = config
        self.state = AppState()

        # Trial 加载（同步）
        self.trial: TrialBundle = TrialLoader(config.trial_dir).load()

        self._build_ui()

        # 设置初始 toolbar
        trial_label = "/".join(config.trial_dir.parts[-2:])
        self.toolbar.set_trial(trial_label)

        # 异步启动检查，避免阻塞窗口显示
        self.root.after(100, self._on_startup)

    # ---------- UI 构建 ----------

    def _build_ui(self) -> None:
        self.toolbar = Toolbar(self.root)
        self.toolbar.pack(side=tk.TOP, fill=tk.X)

        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True)

        # 左：MatchList
        #
        # weight=0 —— ttk.PanedWindow 会在每次 <Configure> 按 weight 比例
        # 重分配整个可用空间（不是"仅分配 delta"）。window 最大化/还原时
        # weight=1 的 child 会膨胀，Treeview stretch=False 的列不跟随扩张，
        # 右侧露出灰色死区。weight=0 让左 pane 拒绝吸收额外空间，全部归
        # 右 pane（图表）—— sash 位置就稳定在 _set_initial_sash 设的值，
        # 不被后续 resize 打扰。
        self.match_list = MatchList(
            main_paned,
            on_row_selected=self._on_row_selected,
            scan_window_days=self.config.scan_window_days,
            on_filter_changed=self._on_filter_changed,
        )
        main_paned.add(self.match_list, weight=0)

        # 右：图表 + 详情面板（垂直分栏）。只有它吸收 resize 额外空间。
        right_paned = ttk.PanedWindow(main_paned, orient=tk.VERTICAL)
        main_paned.add(right_paned, weight=1)

        # 初始 sash 位置：按 MatchList 列宽总和设定，让左面板 "用多少占多少"。
        #
        # 时序坑：<Configure> 事件在窗口逐步 realize 过程中会多次触发，其中
        # 前几次的 winfo_width() 可能是中间值（如 600），此时 sashpos 被 clamp
        # 到该值后就 unbind 了，之后窗口长到 1400 也不再修正。
        # 用 after(300) 等窗口几何稳定后再设——300ms 足够 WM 完成 map + resize。
        def _set_initial_sash():
            target = self.match_list.get_preferred_width()
            paned_w = main_paned.winfo_width()
            # 保证右侧图表至少有 400px
            target = min(target, max(0, paned_w - 400))
            try:
                main_paned.sashpos(0, target)
            except tk.TclError:
                pass
        self.root.after(300, _set_initial_sash)

        chart_frame = ttk.Frame(right_paned)
        right_paned.add(chart_frame, weight=10)
        self.chart = ChartCanvasManager(chart_frame)

        self.detail_panel = DetailPanel(right_paned)
        right_paned.add(self.detail_panel, weight=1)

    # ---------- 启动流程 ----------

    def _on_startup(self) -> None:
        """启动时检查数据新鲜度 + 缓存。"""
        try:
            checker = DataFreshnessChecker(self.config.data_dir, self.config.market_timezone)
            status = checker.check()
        except Exception as e:
            messagebox.showerror("Freshness check failed", f"{e}\n\n{traceback.format_exc()}")
            return

        cached = load_cached_results(self.config.cache_path)

        if status.is_fresh and cached is not None:
            self._render_cached(cached)
            self.toolbar.set_status(status.summary)
            return

        if not status.is_fresh:
            confirmed = confirm_update(self.root, status)
            if confirmed:
                self._run_pipeline_async()
                return

        # 降级：用旧缓存（即使过时）或空列表
        if cached is not None:
            self._render_cached(cached)
            self.toolbar.set_status("Stale (using cache)")
        else:
            self.toolbar.set_status(status.summary)

    def _render_cached(self, cached: CachedResults) -> None:
        self.state.items = cached.items
        self.state.last_scan_date = cached.scan_date
        self.state.last_scan_bar_date = cached.last_scan_bar_date
        self.match_list.set_items(cached.items)
        self.toolbar.set_last_scan(cached.scan_date)

    # ---------- 流水线（异步线程） ----------

    def _run_pipeline_async(self) -> None:
        self.progress_dialog = ProgressDialog(self.root)

        def _progress_callback(p: PipelineProgress) -> None:
            # 从 worker 线程切回主线程更新 UI
            self.root.after(0, lambda: self.progress_dialog.update_progress(p))

        def _worker():
            try:
                pipeline = DailyPipeline(
                    trial=self.trial,
                    data_dir=self.config.data_dir,
                    scan_window_days=self.config.scan_window_days,
                    num_workers=self.config.num_workers,
                    min_price=self.config.min_price,
                    max_price=self.config.max_price,
                    min_volume=self.config.min_volume,
                    progress_callback=_progress_callback,
                )
                matched = pipeline.run()
                self.root.after(0, lambda: self._on_pipeline_done(matched))
            except Exception as e:
                tb = traceback.format_exc()
                # Python 3 在 except 块退出时会 del e；lambda 通过 self.root.after
                # 延后到主线程执行，此时 e 已越作用域。用默认参数早期绑定避免 NameError。
                self.root.after(0, lambda e=e, tb=tb: self._on_pipeline_error(e, tb))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_pipeline_done(self, matched: list[MatchedBreakout]) -> None:
        self.progress_dialog.close()

        scan_date = datetime.now().isoformat(timespec="seconds")
        checker = DataFreshnessChecker(self.config.data_dir, self.config.market_timezone)
        status_after = checker.check()
        bar_date = status_after.newest_local_date or ""

        cached = CachedResults(
            items=matched,
            scan_date=scan_date,
            last_scan_bar_date=bar_date,
        )
        save_cached_results(cached, self.config.cache_path)
        self._render_cached(cached)
        self.toolbar.set_status(f"Scan complete ({len(matched)} matches)")

    def _on_pipeline_error(self, error: Exception, tb: str) -> None:
        self.progress_dialog.close()
        messagebox.showerror("Pipeline failed", f"{error}\n\n{tb}")

    # ---------- 选中状态转移 ----------

    def _update_selection(self, new: MatchedBreakout | None) -> None:
        """Core state transition. Call from list-click and chart-pick paths."""
        self.state.current_selected = new
        self._render_selection()

    def _render_selection(self) -> None:
        """把 state 变更推到两个 view：MatchList tag 高亮 + Chart 重绘 + Detail 面板。"""
        current = self.state.current_selected
        self.match_list.apply_selection_visual(current=current)
        self.detail_panel.update_item(current)
        self._rebuild_chart()

    # ---------- 交互回调 ----------

    def _on_row_selected(self, item: MatchedBreakout) -> None:
        """MatchList 回调：用户真点击某行。直接走状态转移。"""
        self._update_selection(item)

    def _on_chart_bo_picked(self, bo_chart_index: int) -> None:
        """图表 marker 被点击——把处理推迟到当前 pick_event 栈之外执行。

        避免在 matplotlib pick dispatch 栈里同步 destroy canvas（_rebuild_chart
        走到 update_chart._cleanup 会 destroy 当前 FigureCanvasTkAgg）。
        """
        self.root.after_idle(self._on_chart_bo_picked_deferred, bo_chart_index)

    def _on_chart_bo_picked_deferred(self, bo_chart_index: int) -> None:
        """原 _on_chart_bo_picked 的真正实现，在 after_idle 回调里执行。"""
        current = self.state.current_selected
        if current is None:
            # 防御性：chart 清空后 Tk 事件队列可能仍残留未消费的 pick；
            # 正常 UX 下 chart 在 current=None 时已 clear 掉 marker
            return
        # 注意：此处按 raw_breakout["index"] 匹配 chart_index 而非 breakout_date —
        # matplotlib pick_event 只提供整数 chart_index，无法用 M7 的 (symbol, date)
        # 2-tuple 身份键做反查。这是必要的例外，不是 M7 漏改。
        for it in self.match_list.get_visible_items():
            if it.symbol == current.symbol and it.raw_breakout["index"] == bo_chart_index:
                self.match_list.select_item(it)
                return
        self.toolbar.set_status(
            f"BO {bo_chart_index} is hidden by current filter; adjust Date/Score to see it"
        )

    def _rebuild_chart(self) -> None:
        """按 state 当前的 current_selected 重绘图表。无选中时清空图表。

        走 preprocess → trim_df_to_display → adjust_indices 统一流程。
        优先复用 current.range_spec（daily_runner 已构造）；缺失时现场重建。
        """
        current = self.state.current_selected
        if current is None:
            self.chart.clear()
            return

        pkl_path = self.config.data_dir / f"{current.symbol}.pkl"
        if not pkl_path.exists():
            self.chart.clear()
            return

        # 运行时构造 scan 窗口（Live 默认：最近 scan_window_days 天）
        today = datetime.now().date()
        scan_start = (today - timedelta(days=self.config.scan_window_days)).isoformat()
        scan_end = today.isoformat()

        # preprocess: 计算 MA/ATR + 写 df.attrs["range_meta"]
        try:
            raw_df = pd.read_pickle(pkl_path)
            df = preprocess_dataframe(raw_df, start_date=scan_start, end_date=scan_end)
        except Exception as e:
            print(f"[LiveApp] preprocess failed for {current.symbol}: {e}", file=sys.stderr)
            self.chart.clear()
            return

        # 构造 spec（优先复用已有）
        meta = df.attrs.get("range_meta", {})
        display_end = meta.get("label_buffer_end_actual") or df.index[-1].date()
        spec = current.range_spec
        if spec is None:
            # fallback：旧缓存或构造失败，现场重建
            try:
                spec = ChartRangeSpec.from_df_and_scan(
                    df,
                    scan_start=scan_start,
                    scan_end=scan_end,
                    display_end=display_end,
                    # Live UI 保持默认 DISPLAY_MIN_WINDOW（3 年）
                )
            except Exception as e:
                print(f"[LiveApp] spec construction failed for {current.symbol}: {e}", file=sys.stderr)
                spec = None

        # trim + adjust
        if spec is not None:
            display_df, offset = trim_df_to_display(df, spec)
        else:
            display_df, offset = df, 0

        chart_active_peaks, chart_superseded_peaks, peaks_by_id = adapt_peaks(current.raw_peaks)
        raw_bos = current.all_stock_breakouts or [current.raw_breakout]
        all_chart_bos = [adapt_breakout(raw_bo, peaks_by_id) for raw_bo in raw_bos]

        all_chart_bos = adjust_indices(all_chart_bos, offset)
        chart_active_peaks = adjust_indices(chart_active_peaks, offset)
        chart_superseded_peaks = adjust_indices(chart_superseded_peaks, offset)

        # 索引集合（按 offset 调整）
        visible_idx_raw = self.match_list.get_visible_bo_indices(current.symbol)
        visible_idx = {i - offset for i in visible_idx_raw if i >= offset}
        all_matched = {i - offset for i in current.all_matched_bo_chart_indices if i >= offset}
        filtered_out_idx = all_matched - visible_idx

        current_bo_index = current.raw_breakout["index"] - offset
        if current_bo_index < 0:
            current_bo_index = 0

        try:
            self.chart.update_chart(
                df=display_df,
                breakouts=all_chart_bos,
                active_peaks=chart_active_peaks,
                superseded_peaks=chart_superseded_peaks,
                symbol=current.symbol,
                display_options={
                    "live_mode": True,
                    "current_bo_index": current_bo_index,
                    "visible_matched_indices": visible_idx,
                    "filtered_out_matched_indices": filtered_out_idx,
                    "on_bo_picked": self._on_chart_bo_picked,
                    "show_superseded_peaks": True,
                },
                initial_window_days=180,
                filter_cutoff_date=self.match_list.get_date_cutoff(),
                spec=spec,
            )
        except Exception as e:
            print(f"[LiveApp] Chart render failed: {e}", file=sys.stderr)

    def _on_filter_changed(self) -> None:
        """MatchList 的 Date/Price/Score/sort 变化时调用。

        责任：
        1. 若 current_selected 被新 filter 过滤掉（不在 visible） → 清空 state
        2. 否则重绘视觉（iid 已重建，tag 需重打；图表 4 级分类也变了）
        3. 若没触发重绘，单独同步图表背景 filter range
        """
        current = self.state.current_selected
        if current is None:
            # 无选中 → 只需更新 filter range 背景
            self.chart.update_filter_range(self.match_list.get_date_cutoff())
            return

        visible = self.match_list.get_visible_items()
        # (symbol, breakout_date) 是 daily_runner 产出的天然唯一键
        # （每天每股票最多一个 matched BO），所有识别都统一用 2-tuple
        still_visible = any(
            it.symbol == current.symbol and it.breakout_date == current.breakout_date
            for it in visible
        )
        if not still_visible:
            # current 被过滤掉 → 清空状态，chart.clear() 在 _rebuild_chart 里调；
            # 还要单独调 update_filter_range 因为 clear 后没 artists 画背景
            self._update_selection(None)
            self.chart.update_filter_range(self.match_list.get_date_cutoff())
        else:
            # current 仍可见 → _render_selection 会 rebuild chart，
            # 内部 update_chart 已经重新画了 filter background，无需再调
            self._render_selection()
