"""
采集 AAPL 新闻数据用于 benchmark

直接使用 collectors + filter，不调用 analyze() 避免触发 GLM 分析。
输出 CSV 文件作为所有模型的统一输入。
"""

import csv
import logging
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from BreakoutStrategy.news_sentiment.config import load_config
from BreakoutStrategy.news_sentiment.collectors.finnhub_collector import FinnhubCollector
from BreakoutStrategy.news_sentiment.collectors.alphavantage_collector import AlphaVantageCollector
from BreakoutStrategy.news_sentiment.collectors.edgar_collector import EdgarCollector
from BreakoutStrategy.news_sentiment.filter import filter_news
from BreakoutStrategy.news_sentiment.models import NewsItem


def main():
    # === 参数配置 ===
    ticker = "AAPL"
    date_from = "2026-02-15"
    date_to = "2026-03-15"
    max_items = 40
    output_path = PROJECT_ROOT / "experiments" / "news_sentiment_benchmark" / "results" / "benchmark_data.csv"

    # === 初始化日志 ===
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
        datefmt='%H:%M:%S',
    )
    logger = logging.getLogger(__name__)

    # === 加载配置 ===
    config = load_config()
    config.filter.max_items = max_items

    # === 初始化采集器 ===
    collectors = []
    if config.finnhub.enable:
        collectors.append(FinnhubCollector(config.finnhub, proxy=config.proxy))
    if config.alphavantage.enable:
        collectors.append(AlphaVantageCollector(config.alphavantage, proxy=config.proxy))
    if config.edgar.enable:
        collectors.append(EdgarCollector(config.edgar, proxy=config.proxy))

    # === 采集 ===
    all_items: list[NewsItem] = []
    source_stats: dict[str, int] = {}

    for collector in collectors:
        if not collector.is_available():
            logger.info(f"[{collector.name}] Not available, skipping")
            continue
        try:
            items = collector.collect(ticker, date_from, date_to)
            source_stats[collector.name] = len(items)
            all_items.extend(items)
            logger.info(f"[{collector.name}] Collected {len(items)} items")
        except Exception as e:
            logger.error(f"[{collector.name}] Error: {e}")
            source_stats[collector.name] = 0

    logger.info(f"Total collected: {len(all_items)} items from {source_stats}")

    # === 过滤（语义过滤 + 去重 + 采样，不做情感分析） ===
    filtered_items = filter_news(all_items, config.filter, ticker=ticker)
    logger.info(f"Filtered: {len(all_items)} -> {len(filtered_items)} items")

    # === 保存 CSV ===
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['id', 'title', 'summary', 'text', 'source', 'published_at', 'collector'])
        for i, item in enumerate(filtered_items):
            text = f"{item.title}: {item.summary}" if item.summary else item.title
            writer.writerow([i, item.title, item.summary, text, item.source, item.published_at, item.collector])

    logger.info(f"Saved {len(filtered_items)} items to {output_path}")


if __name__ == "__main__":
    main()
