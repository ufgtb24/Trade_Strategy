"""LiveApp 主协调器。"""

import sys
import threading
import tkinter as tk
import traceback
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

import pandas as pd

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
        self.toolbar = Toolbar(self.root, on_refresh=self._on_refresh_clicked)
        self.toolbar.pack(side=tk.TOP, fill=tk.X)

        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True)

        # 左：MatchList
        self.match_list = MatchList(main_paned, on_select=self._on_item_selected)
        main_paned.add(self.match_list, weight=1)

        # 右：图表 + 详情面板（垂直分栏）
        right_paned = ttk.PanedWindow(main_paned, orient=tk.VERTICAL)
        main_paned.add(right_paned, weight=4)

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
                self.root.after(0, lambda: self._on_pipeline_error(e, tb))

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

    # ---------- 交互回调 ----------

    def _on_refresh_clicked(self) -> None:
        self._run_pipeline_async()

    def _on_item_selected(self, item: MatchedBreakout | None) -> None:
        self.state.selected = item
        self.detail_panel.update_item(item)
        if item is None:
            return

        # 加载该股票的 DataFrame
        pkl_path = self.config.data_dir / f"{item.symbol}.pkl"
        if not pkl_path.exists():
            return

        try:
            df = pd.read_pickle(pkl_path)
        except Exception:
            return

        # 复用 ChartCanvasManager.update_chart 接口
        # 注意：raw_breakout 是 dict，ChartCanvasManager 原本期望 Breakout 对象；
        # 实施时若类型不兼容，需要在此处做 dict → Breakout 的转换（参考开发 UI
        # 是如何从 JSON 加载 breakouts 并传给 chart 的）
        try:
            self.chart.update_chart(
                df=df,
                breakouts=[item.raw_breakout],
                active_peaks=item.raw_peaks,
                superseded_peaks=[],
                symbol=item.symbol,
                display_options={},
                template_matched_indices=[0],
            )
        except Exception as e:
            # 实施时待验证 [6]: 可能需要 dict → Breakout 适配层
            print(f"[LiveApp] Chart render failed: {e}", file=sys.stderr)
