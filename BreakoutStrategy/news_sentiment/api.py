"""
公共 API 入口

提供 analyze() 函数，编排采集→过滤→分析→报告的完整流程。
"""

import dataclasses
import logging
import math
from datetime import date, datetime, timezone

from BreakoutStrategy.news_sentiment.analyzer import SentimentAnalyzer
from BreakoutStrategy.news_sentiment.cache import SentimentCache, compute_uncovered_ranges
from BreakoutStrategy.news_sentiment.collectors.alphavantage_collector import AlphaVantageCollector
from BreakoutStrategy.news_sentiment.collectors.base import BaseCollector
from BreakoutStrategy.news_sentiment.collectors.edgar_collector import EdgarCollector
from BreakoutStrategy.news_sentiment.collectors.finnhub_collector import FinnhubCollector
from BreakoutStrategy.news_sentiment.config import NewsSentimentConfig, load_config
from BreakoutStrategy.news_sentiment.models import AnalysisReport, NewsItem, SummaryResult
from BreakoutStrategy.news_sentiment.filter import filter_news
from BreakoutStrategy.news_sentiment.reporter import save_report

logger = logging.getLogger(__name__)


def _compute_dynamic_max_items(num_days: int, base: float = 10.0,
                                min_items: int = 15, max_cap: int = 100) -> int:
    """根据时间跨度动态计算 max_items = clamp(base * sqrt(num_days), min, max)"""
    raw = base * math.sqrt(max(1, num_days))
    return int(min(max_cap, max(min_items, raw)))


def analyze(
    ticker: str,
    date_from: str,
    date_to: str,
    config: NewsSentimentConfig | None = None,
    save: bool = True,
) -> AnalysisReport:
    """
    收集指定股票在时间段内的新闻/公告/财报，执行情感分析。

    结果同时保存为 JSON 文件并返回 AnalysisReport。
    永不抛异常，始终返回 AnalysisReport。

    Args:
        ticker: 股票代码，如 "AAPL"
        date_from: 起始日期 YYYY-MM-DD
        date_to: 结束日期 YYYY-MM-DD
        config: 可选配置，默认从 YAML + 环境变量加载
    """
    if config is None:
        config = load_config()

    cache = SentimentCache(config.cache)
    collected_at = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    # 1. 初始化采集器（按 enable 配置）
    collectors: list[BaseCollector] = []
    if config.finnhub.enable:
        collectors.append(FinnhubCollector(config.finnhub, proxy=config.proxy))
    if config.alphavantage.enable:
        collectors.append(AlphaVantageCollector(config.alphavantage, proxy=config.proxy))
    if config.edgar.enable:
        collectors.append(EdgarCollector(config.edgar, proxy=config.proxy))

    # 2. 增量采集（缓存感知）
    # 覆盖标记延迟到分析完成后统一写入，防止 Ctrl+C 中断导致缓存污染
    all_items: list[NewsItem] = []
    source_stats: dict[str, int] = {}
    pending_coverage: list[tuple[str, str, str, str]] = []

    for collector in collectors:
        if not collector.is_available():
            logger.info(f"[{collector.name}] Not available, skipping")
            continue

        try:
            # 查询已覆盖区间
            covered = cache.get_covered_ranges(ticker, collector.name)
            uncovered = compute_uncovered_ranges((date_from, date_to), covered)

            # 从缓存获取已有新闻
            cached_items = cache.get_news(ticker, date_from, date_to, collector.name)

            # 仅采集未覆盖范围（覆盖标记延迟提交）
            # 只在成功获取到新闻时标记 coverage，空结果保留重试机会
            new_items: list[NewsItem] = []
            for uc_from, uc_to in uncovered:
                fetched = collector.collect(ticker, uc_from, uc_to)
                new_items.extend(fetched)
                if fetched:
                    pending_coverage.append((ticker, collector.name, uc_from, uc_to))

            # 写入缓存
            if new_items:
                cache.put_news(ticker, collector.name, new_items)

            combined = cached_items + new_items
            source_stats[collector.name] = len(combined)
            all_items.extend(combined)
            logger.info(
                f"[{collector.name}] {len(cached_items)} cached + "
                f"{len(new_items)} new = {len(combined)} items"
            )
        except Exception as e:
            logger.error(f"[{collector.name}] Unexpected error: {e}")
            source_stats[collector.name] = 0

    # 2.5 查找公司名（用于 relevance_filter 参考向量，缓存避免重复 API 调用）
    company_name = cache.get_company_name(ticker) or ""
    if not company_name:
        for collector in collectors:
            if isinstance(collector, FinnhubCollector) and collector.is_available():
                company_name = collector.get_company_name(ticker)
                if company_name:
                    cache.put_company_name(ticker, company_name)
                break

    # 2.8 动态调整 max_items（使用副本，不修改传入的 config）
    try:
        d_from = date.fromisoformat(date_from)
        d_to = date.fromisoformat(date_to)
        num_days = max(1, (d_to - d_from).days)
        dmc = config.filter.dynamic_max_items
        dynamic_max = _compute_dynamic_max_items(num_days, dmc.base, dmc.min_items, dmc.max_items)
        config = dataclasses.replace(
            config,
            filter=dataclasses.replace(config.filter, max_items=dynamic_max),
        )
        logger.info(f"Dynamic max_items: {dynamic_max} (num_days={num_days})")
    except ValueError:
        pass  # 日期格式错误时保持原值

    # 3. 过滤（语义过滤 + 相关性过滤 + 语义去重 + 多样性采样）
    filtered_items = filter_news(
        all_items, config.filter,
        ticker=ticker, company_name=company_name,
        reference_date=date_to,
    )
    logger.info(f"Filtered: {len(all_items)} -> {len(filtered_items)} items")

    # 4. 情感分析
    try:
        analyzer = SentimentAnalyzer(config.analyzer, cache=cache)
        analyzed_items, summary = analyzer.analyze(
            filtered_items, ticker, date_from, date_to,
            time_decay=config.filter.time_decay,
        )
    except Exception as e:
        logger.error(f"Analyzer failed: {e}")
        analyzed_items = []
        summary = SummaryResult(
            sentiment="neutral", confidence=0.0,
            reasoning=f"Analysis failed: {e}",
            positive_count=0, negative_count=0, neutral_count=0, total_count=0,
            fail_count=0,
        )

    # 5. 提交覆盖标记（分析完成后才标记，Ctrl+C 中断时不会留下虚假覆盖）
    for cov_ticker, cov_collector, cov_from, cov_to in pending_coverage:
        cache.update_coverage(cov_ticker, cov_collector, cov_from, cov_to)

    # 6. 生成报告
    report = AnalysisReport(
        ticker=ticker,
        date_from=date_from,
        date_to=date_to,
        collected_at=collected_at,
        items=analyzed_items,
        summary=summary,
        source_stats=source_stats,
    )

    if save:
        try:
            filepath = save_report(report, config.output_dir)
            logger.info(f"Report saved to {filepath}")
        except Exception as e:
            logger.error(f"Failed to save report: {e}")

    return report
