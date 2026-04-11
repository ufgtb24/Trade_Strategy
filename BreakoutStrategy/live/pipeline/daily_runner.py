"""每日扫描流水线：下载 → 扫描 → 匹配 → 情感。"""

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from BreakoutStrategy.live.pipeline.results import MatchedBreakout
from BreakoutStrategy.live.pipeline.trial_loader import TrialBundle

# Marker 文件：标记上一次 _step1_download_data 成功完成的日期。
# DataFreshnessChecker 优先读这个，避免"部分更新"时抽样误判为 fresh。
DOWNLOAD_MARKER_FILENAME = ".last_full_update"


@dataclass
class PipelineProgress:
    stage: str          # "downloading" | "scanning" | "matching" | "sentiment" | "done"
    current: int
    total: int

    @property
    def percent(self) -> float:
        return (self.current / self.total * 100) if self.total > 0 else 0.0


ProgressCallback = Callable[[PipelineProgress], None]


class DailyPipeline:
    """无 UI 依赖的业务流水线，可单元测试。"""

    def __init__(
        self,
        trial: TrialBundle,
        data_dir: Path,
        scan_window_days: int = 90,
        num_workers: int = 8,
        min_price: float = 1.0,
        max_price: float = 10.0,
        min_volume: int = 10000,
        progress_callback: ProgressCallback | None = None,
    ):
        self.trial = trial
        self.data_dir = Path(data_dir)
        self.scan_window_days = scan_window_days
        self.num_workers = num_workers
        self.min_price = min_price
        self.max_price = max_price
        self.min_volume = min_volume
        self._progress = progress_callback or (lambda p: None)

    def run(self) -> list[MatchedBreakout]:
        """完整流水线。按顺序执行 4 个 Step。"""
        self._progress(PipelineProgress("downloading", 0, 0))
        self._step1_download_data()

        self._progress(PipelineProgress("scanning", 0, 0))
        scan_results = self._step2_scan()

        self._progress(PipelineProgress("matching", 0, 0))
        candidates = self._step3_match_templates(scan_results)

        self._progress(PipelineProgress("sentiment", 0, len(candidates)))
        matched = self._step4_sentiment_analysis(candidates)

        self._progress(PipelineProgress("done", len(matched), len(matched)))
        return matched

    def _step1_download_data(self) -> None:
        """Step 1: 增量下载全市场 PKL 数据。

        下载完成后写 marker 文件 datasets/pkls/.last_full_update 记录当天日期，
        供 DataFreshnessChecker 判断"上次是不是整体更新成功了"。如果下载中途
        崩溃，marker 不会被写，下次启动会被判定为 stale，触发重试。

        下载是 I/O-bound，并发数独立于 scan 阶段，使用 cpu_count-2
        （留 2 核给系统，避免与 Tkinter 主线程争抢）。
        """
        from scripts.data.data_download import get_us_tickers_fast, multi_download_stock

        download_workers = max(1, (os.cpu_count() or 2) - 2)

        tickers = get_us_tickers_fast()
        multi_download_stock(
            tickers=tickers,
            save_root=str(self.data_dir),
            days_from_now=self.scan_window_days + 400,
            append_data=True,
            clear=False,  # 不清空现有数据，走增量追加
            num_workers=download_workers,
            file_format="pkl",
        )

        # 写 marker（只在所有 ticker 全部成功处理完毕后执行）
        marker = self.data_dir / DOWNLOAD_MARKER_FILENAME
        marker.write_text(datetime.now().date().isoformat(), encoding="utf-8")

    def _step2_scan(self) -> list[dict]:
        """Step 2: 用 trial 的扫描参数扫描近 N 天窗口。

        通过 UIParamLoader.from_dict 合并 trial.scan_params → 扫描参数。
        """
        from BreakoutStrategy.analysis.scanner import ScanManager
        from BreakoutStrategy.UI.config.param_loader import UIParamLoader

        loader = UIParamLoader.from_dict(self.trial.scan_params)
        feat = loader.get_feature_calculator_params()
        scorer = loader.get_scorer_params()

        det_raw = self.trial.scan_params.get("breakout_detector", {})
        det = {k: v for k, v in det_raw.items() if k not in ("cache_dir", "use_cache")}

        today = datetime.now().date()
        start = (today - timedelta(days=self.scan_window_days)).strftime("%Y-%m-%d")
        end = today.strftime("%Y-%m-%d")

        # label 计算对实盘无意义（没有未来数据），但 ScanManager 的 label_max_days 被用作
        # end_date 之后的缓冲区大小，不影响突破检测本身。接受 ScanManager 的默认值 20。
        mgr = ScanManager(
            output_dir="/tmp/live_scan",
            **det,
            start_date=start,
            end_date=end,
            feature_calc_config=feat,
            scorer_config=scorer,
            min_price=self.min_price,
            max_price=self.max_price,
            min_volume=self.min_volume,
        )

        symbols = sorted([f.stem for f in self.data_dir.glob("*.pkl")])
        return mgr.parallel_scan(
            symbols=symbols,
            data_dir=str(self.data_dir),
            num_workers=self.num_workers,
        )

    def _step3_match_templates(
        self, scan_results: list[dict]
    ) -> list[MatchedBreakout]:
        """Step 3: 用 Top-1 模板过滤扫描结果，只保留命中的突破。"""
        from BreakoutStrategy.mining.template_matcher import TemplateManager

        matcher = TemplateManager()
        # 手动注入状态（不经过 load_filter_yaml 文件加载）
        matcher.templates = [self.trial.template]
        matcher.thresholds = self.trial.thresholds
        matcher.negative_factors = self.trial.negative_factors
        matcher.sample_size = 1
        matcher._loaded = True

        candidates: list[MatchedBreakout] = []
        for stock_result in scan_results:
            if "error" in stock_result or "breakouts" not in stock_result:
                continue
            matched_indices = matcher.match_stock(stock_result, self.trial.template)
            for idx in matched_indices:
                bo = stock_result["breakouts"][idx]
                candidates.append(MatchedBreakout(
                    symbol=stock_result["symbol"],
                    breakout_date=bo["date"],
                    breakout_price=float(bo["price"]),
                    factors={f: bo[f] for f in self.trial.template["factors"] if f in bo},
                    sentiment_score=None,
                    sentiment_category="pending",
                    sentiment_summary=None,
                    raw_breakout=bo,
                    raw_peaks=stock_result.get("all_peaks", []),
                ))
        return candidates

    def _step4_sentiment_analysis(
        self, candidates: list[MatchedBreakout]
    ) -> list[MatchedBreakout]:
        """Step 4: 对每个候选调用情感分析。

        使用现有的 BreakoutStrategy.news_sentiment.api.analyze 接口。
        """
        from BreakoutStrategy.news_sentiment.api import analyze
        from BreakoutStrategy.news_sentiment.config import load_config as load_sentiment_config

        sent_cfg = load_sentiment_config()
        lookback_days = 7
        include_bo_day = True

        def _call_analyze(ticker: str, bo_date_str: str):
            """调用情感分析 API。

            注意：analyze() 按契约永不抛异常，失败情况通过返回值中的
            SummaryResult.total_count == 0 / fail_count 反映，所以这里
            不需要 try/except 或重试。
            """
            bo_date = datetime.strptime(bo_date_str, "%Y-%m-%d")
            end_date = bo_date if include_bo_day else bo_date - timedelta(days=1)
            date_from = (bo_date - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
            date_to = end_date.strftime("%Y-%m-%d")
            return analyze(ticker, date_from, date_to, config=sent_cfg, save=False)

        for i, cand in enumerate(candidates):
            self._progress(PipelineProgress("sentiment", i, len(candidates)))
            report = _call_analyze(cand.symbol, cand.breakout_date)

            if report is None:
                cand.sentiment_score = None
                cand.sentiment_category = "error"
                cand.sentiment_summary = None
                continue

            summary = report.summary
            if summary.total_count == 0:
                cand.sentiment_score = None
                cand.sentiment_category = "insufficient_data"
                cand.sentiment_summary = None
            else:
                cand.sentiment_score = float(summary.sentiment_score)
                cand.sentiment_category = "analyzed"
                cand.sentiment_summary = summary.reasoning[:120] if summary.reasoning else None

        return candidates
