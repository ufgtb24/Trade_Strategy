"""
Alpha Vantage 采集器

使用 NEWS_SENTIMENT endpoint，返回带情感评分的新闻。
免费 tier: 25次/天，5次/分钟。
额度耗尽时返回 HTTP 200 + {"Note": "..."} 或 {"Information": "..."}。
"""

import logging

import requests

from BreakoutStrategy.news_sentiment.config import CollectorConfig
from BreakoutStrategy.news_sentiment.models import NewsItem

from .base import BaseCollector

logger = logging.getLogger(__name__)

BASE_URL = "https://www.alphavantage.co/query"


class AlphaVantageCollector(BaseCollector):
    """Alpha Vantage 新闻情感采集器"""

    name = "alphavantage"

    def __init__(self, config: CollectorConfig, proxy: str = ''):
        self._config = config
        self._proxies = {'https': proxy, 'http': proxy} if proxy else None

    def is_available(self) -> bool:
        return bool(self._config.api_key)

    def collect(self, ticker: str, date_from: str, date_to: str) -> list[NewsItem]:
        """采集带情感评分的新闻"""
        time_from = date_from.replace('-', '') + 'T0000'
        time_to = date_to.replace('-', '') + 'T2359'

        params = {
            'function': 'NEWS_SENTIMENT',
            'tickers': ticker,
            'time_from': time_from,
            'time_to': time_to,
            'limit': 50,
            'apikey': self._config.api_key,
        }

        try:
            resp = requests.get(BASE_URL, params=params, timeout=self._config.timeout, proxies=self._proxies)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"[AlphaVantage] Request failed for {ticker}: {e}")
            return []

        if 'Note' in data or 'Information' in data:
            msg = data.get('Note', data.get('Information', ''))
            logger.warning(f"[AlphaVantage] Rate limited: {msg}")
            return []

        feed = data.get('feed', [])
        items = []

        for article in feed:
            try:
                ticker_sentiment = self._extract_ticker_sentiment(article, ticker)
                raw_time = article.get('time_published', '')
                published = self._parse_time(raw_time)

                items.append(NewsItem(
                    title=article.get('title', ''),
                    summary=article.get('summary', ''),
                    source=article.get('source', ''),
                    published_at=published,
                    url=article.get('url', ''),
                    ticker=ticker,
                    category='news',
                    collector=self.name,
                    raw_sentiment=ticker_sentiment,
                ))
            except Exception as e:
                logger.warning(f"[AlphaVantage] Failed to parse article: {e}")
                continue

        logger.info(f"[AlphaVantage] {ticker}: collected {len(items)} items")
        return items

    def _extract_ticker_sentiment(self, article: dict, ticker: str) -> float | None:
        """从文章中提取指定 ticker 的情感评分"""
        for ts in article.get('ticker_sentiment', []):
            if ts.get('ticker', '').upper() == ticker.upper():
                try:
                    return float(ts.get('ticker_sentiment_score', 0))
                except (ValueError, TypeError):
                    pass
        try:
            return float(article.get('overall_sentiment_score', 0))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_time(raw_time: str) -> str:
        """转换 AlphaVantage 时间格式: 20260315T143000 -> 2026-03-15T14:30:00Z"""
        if not raw_time or len(raw_time) < 15:
            return raw_time
        return (
            f"{raw_time[0:4]}-{raw_time[4:6]}-{raw_time[6:8]}"
            f"T{raw_time[9:11]}:{raw_time[11:13]}:{raw_time[13:15]}Z"
        )
