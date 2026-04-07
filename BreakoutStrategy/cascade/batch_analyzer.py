"""
级联分析核心编排

提取 top-K 模板命中样本 → 按 (ticker, breakout_date) 去重 → 批量情感分析 → 合并结果。
每个突破日期独立调用 analyze()，确保 time_decay 的 reference_date 正确。
news_sentiment 的缓存机制保证同 ticker 重叠窗口不会重复采集。
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Callable

import numpy as np
import pandas as pd

from BreakoutStrategy.cascade.filter import (
    classify_sample,
    is_positive_boost,
    load_cascade_config,
)
from BreakoutStrategy.cascade.models import (
    BreakoutSample,
    CascadeReport,
    CascadeResult,
)
from BreakoutStrategy.factor_registry import LABEL_COL
from BreakoutStrategy.news_sentiment.api import analyze
from BreakoutStrategy.news_sentiment.config import NewsSentimentConfig, load_config as load_sentiment_config
from BreakoutStrategy.news_sentiment.models import AnalysisReport

logger = logging.getLogger(__name__)


def extract_top_k_samples(
    df_test: pd.DataFrame,
    keys_test: np.ndarray,
    top_k_keys: set[int],
    top_k_names: dict[int, str],
    label_col: str = LABEL_COL,
) -> list[BreakoutSample]:
    """从测试集中提取被 top-K 模板命中的突破样本。

    Args:
        df_test: 测试集 DataFrame（需包含 symbol, date, label_col 列）
        keys_test: 每行的 template key (bit-packed int array)
        top_k_keys: top-K 模板的 key 集合
        top_k_names: key → template_name 映射

    Returns:
        BreakoutSample 列表
    """
    mask = np.isin(keys_test, list(top_k_keys))
    indices = np.where(mask)[0]

    samples = []
    for idx in indices:
        row = df_test.iloc[idx]
        key = int(keys_test[idx])
        samples.append(BreakoutSample(
            symbol=row["symbol"],
            date=row["date"],
            label=float(row[label_col]),
            template_name=top_k_names.get(key, f"key_{key}"),
            template_key=key,
        ))
    return samples


def deduplicate_analysis_tasks(
    samples: list[BreakoutSample],
    lookback_days: int = 7,
) -> dict[tuple[str, str], dict]:
    """按 (ticker, breakout_date) 去重，生成分析任务列表。

    每个突破日期独立分析，确保 time_decay 的 reference_date 正确。
    同一 ticker 不同日期的窗口可能重叠，news_sentiment 缓存自动处理。

    Returns:
        {(ticker, breakout_date): {"date_from": str, "date_to": str}}
    """
    tasks: dict[tuple[str, str], dict] = {}
    for s in samples:
        key = (s.symbol, s.date)
        if key not in tasks:
            bo_date = datetime.strptime(s.date, "%Y-%m-%d")
            tasks[key] = {
                "date_from": (bo_date - timedelta(days=lookback_days)).strftime("%Y-%m-%d"),
                "date_to": s.date,
            }
    return tasks


def _analyze_single(
    ticker: str,
    date_from: str,
    date_to: str,
    sentiment_config: NewsSentimentConfig,
    save: bool,
    max_retries: int,
    retry_delay: float,
) -> AnalysisReport | None:
    """对单个 (ticker, date_range) 执行情感分析，含重试逻辑。

    analyze() 保证永不抛异常（返回 neutral + confidence=0），
    此处的 try/except 仅处理极端情况（如网络完全中断）。
    """
    for attempt in range(max_retries + 1):
        try:
            return analyze(ticker, date_from, date_to,
                           config=sentiment_config, save=save)
        except Exception as e:
            if attempt < max_retries:
                logger.warning("[%s] Attempt %d failed: %s, retrying in %.0fs",
                               ticker, attempt + 1, e, retry_delay)
                time.sleep(retry_delay)
            else:
                logger.error("[%s] All %d attempts failed: %s",
                             ticker, max_retries + 1, e)
                return None


def build_cascade_report(
    results: list[CascadeResult],
    thresholds: dict,
) -> CascadeReport:
    """从 CascadeResult 列表构建 CascadeReport。

    计算筛前/筛后统计量，按 sentiment_score 降序排列结果。
    """
    pass_count = sum(1 for r in results if r.category == "pass")
    reject_count = sum(1 for r in results if r.category == "reject")
    strong_reject_count = sum(1 for r in results if r.category == "strong_reject")
    insufficient_count = sum(1 for r in results if r.category == "insufficient_data")
    error_count = sum(1 for r in results if r.category == "error")
    positive_boost_count = sum(
        1 for r in results
        if r.category == "pass" and is_positive_boost(r.sentiment_score, thresholds)
    )

    all_labels = np.array([r.sample.label for r in results])
    passed_labels = np.array([
        r.sample.label for r in results
        if r.category in ("pass", "insufficient_data", "error")
    ])

    pre_median = float(np.median(all_labels)) if len(all_labels) > 0 else 0.0
    post_median = float(np.median(passed_labels)) if len(passed_labels) > 0 else 0.0

    unique_tickers = len(set(r.sample.symbol for r in results))

    sorted_results = sorted(results, key=lambda r: r.sentiment_score, reverse=True)

    return CascadeReport(
        total_samples=len(results),
        unique_tickers=unique_tickers,
        analyzed_count=len(results) - error_count,
        error_count=error_count,
        pass_count=pass_count,
        reject_count=reject_count,
        strong_reject_count=strong_reject_count,
        insufficient_data_count=insufficient_count,
        positive_boost_count=positive_boost_count,
        pre_filter_median=pre_median,
        post_filter_median=post_median,
        cascade_lift=post_median - pre_median,
        results=sorted_results,
    )


def run_cascade(
    df_test: pd.DataFrame,
    keys_test: np.ndarray,
    top_k_keys: set[int],
    top_k_names: dict[int, str],
    cascade_config: dict | None = None,
    sentiment_config: NewsSentimentConfig | None = None,
    on_progress: Callable | None = None,
) -> CascadeReport:
    """级联分析主入口。

    从 template_validator 的输出中提取 top-K 模板命中样本，
    批量执行情感分析，筛选后产出级联报告。

    Args:
        df_test: 测试集 DataFrame（需包含 symbol, date, label 列）
        keys_test: 每行的 template key (bit-packed int array)
        top_k_keys: top-K 模板的 key 集合
        top_k_names: key → template_name 映射
        cascade_config: 级联配置（默认从 cascade.yaml 加载）
        sentiment_config: 情感分析配置（默认从 news_sentiment.yaml 加载）
        on_progress: 进度回调 (completed, total, ticker, result) → None

    Returns:
        CascadeReport 包含完整统计和逐样本结果
    """
    cfg = cascade_config or load_cascade_config()
    sent_cfg = sentiment_config or load_sentiment_config()

    thresholds = cfg["thresholds"]
    lookback = cfg["lookback_days"]
    max_concurrent = cfg["max_concurrent_tickers"]
    max_retries = cfg["max_retries"]
    retry_delay = cfg["retry_delay"]
    save_reports = cfg["save_individual_reports"]
    min_total_count = cfg["min_total_count"]
    max_fail_ratio = cfg["max_fail_ratio"]

    # Step 1: 提取 top-K 模板命中样本
    samples = extract_top_k_samples(df_test, keys_test, top_k_keys, top_k_names)
    if not samples:
        logger.warning("No top-K matched samples found")
        return CascadeReport(
            total_samples=0, unique_tickers=0,
            analyzed_count=0, error_count=0,
            pass_count=0, reject_count=0, strong_reject_count=0,
            insufficient_data_count=0, positive_boost_count=0,
            pre_filter_median=0.0, post_filter_median=0.0,
            cascade_lift=0.0,
        )

    logger.info("Extracted %d top-K matched samples", len(samples))

    # Step 2: 按 (ticker, breakout_date) 去重生成分析任务
    # 每个突破日期独立分析，确保 time_decay reference_date 正确
    tasks = deduplicate_analysis_tasks(samples, lookback)
    unique_tickers = len(set(k[0] for k in tasks))
    logger.info("Deduplicated into %d analysis tasks (%d unique tickers)",
                len(tasks), unique_tickers)

    # Step 3: 批量情感分析（per breakout date）
    # news_sentiment 缓存自动处理同 ticker 重叠窗口的新闻复用
    task_reports: dict[tuple[str, str], AnalysisReport | None] = {}

    def _analyze_task(task_key: tuple[str, str]) -> tuple[tuple[str, str], AnalysisReport | None]:
        ticker, bo_date = task_key
        window = tasks[task_key]
        report = _analyze_single(
            ticker, window["date_from"], window["date_to"],
            sent_cfg, save=save_reports,
            max_retries=max_retries, retry_delay=retry_delay,
        )
        return task_key, report

    completed_count = 0
    total_tasks = len(tasks)

    with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        futures = {
            executor.submit(_analyze_task, key): key
            for key in tasks
        }
        for future in as_completed(futures):
            task_key, report = future.result()
            task_reports[task_key] = report
            completed_count += 1
            ticker, bo_date = task_key
            logger.info("[%d/%d] %s (%s): %s",
                        completed_count, total_tasks, ticker, bo_date,
                        "OK" if report else "FAILED")

    # Step 4: 关联回每个突破样本 + 筛选分类
    results: list[CascadeResult] = []
    for sample in samples:
        task_key = (sample.symbol, sample.date)
        report = task_reports.get(task_key)
        if report is None:
            results.append(CascadeResult(
                sample=sample, sentiment_score=0.0,
                sentiment="neutral", confidence=0.0,
                category="error", total_count=0,
            ))
        else:
            summary = report.summary
            category = classify_sample(
                summary.sentiment_score,
                summary.total_count,
                summary.fail_count,
                thresholds,
                min_total_count,
                max_fail_ratio,
            )
            results.append(CascadeResult(
                sample=sample,
                sentiment_score=summary.sentiment_score,
                sentiment=summary.sentiment,
                confidence=summary.confidence,
                category=category,
                total_count=summary.total_count,
            ))

        if on_progress:
            on_progress(len(results), len(samples), sample.symbol, results[-1])

    # Step 5: 构建报告
    return build_cascade_report(results, thresholds)
