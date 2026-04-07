"""
Finnhub 采集器

采集公司新闻 (/company-news) 和财报日历 (/calendar/earnings)。
免费 tier: 60次/分钟，无日限。rate_limit 配置控制调用间隔（0=不限流）。
"""

import logging
import threading
import time
from datetime import datetime

import finnhub

from BreakoutStrategy.news_sentiment.config import CollectorConfig
from BreakoutStrategy.news_sentiment.models import NewsItem

from .base import BaseCollector

logger = logging.getLogger(__name__)


class _RateLimiter:
    """线程安全的最小间隔限流器，min_interval<=0 时不限流"""

    def __init__(self, min_interval: float):
        self._min_interval = min_interval
        self._last_call = 0.0
        self._lock = threading.Lock()

    def acquire(self):
        if self._min_interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_call
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
            self._last_call = time.monotonic()


class FinnhubCollector(BaseCollector):
    """Finnhub 新闻采集器"""

    name = "finnhub"

    def __init__(self, config: CollectorConfig, proxy: str = ''):
        self._config = config
        self._proxy = proxy
        self._client: finnhub.Client | None = None
        self._limiter = _RateLimiter(config.rate_limit)

    def is_available(self) -> bool:
        return bool(self._config.api_key)

    def _get_client(self) -> finnhub.Client:
        if self._client is None:
            proxies = {'https': self._proxy, 'http': self._proxy} if self._proxy else None
            self._client = finnhub.Client(api_key=self._config.api_key, proxies=proxies)
        return self._client

    def collect(self, ticker: str, date_from: str, date_to: str) -> list[NewsItem]:
        """采集公司新闻 + 财报日历"""
        items: list[NewsItem] = []
        client = self._get_client()

        items.extend(self._fetch_company_news(client, ticker, date_from, date_to))
        items.extend(self._fetch_earnings(client, ticker, date_from, date_to))

        logger.info(f"[Finnhub] {ticker}: collected {len(items)} items")
        return items

    def get_company_name(self, ticker: str) -> str:
        """查询公司名称（用于 relevance_filter 参考向量）"""
        self._limiter.acquire()
        try:
            profile = self._get_client().company_profile2(symbol=ticker)
            name = profile.get("name", "")
            logger.info(f"Company name: '{name}'")
            return name
        except finnhub.FinnhubAPIException as e:
            if e.status_code == 429:
                logger.warning(f"[Finnhub] Rate limited on company_profile2 for {ticker}")
            return ""
        except Exception:
            return ""

    def _fetch_company_news(
        self, client: finnhub.Client, ticker: str,
        date_from: str, date_to: str,
    ) -> list[NewsItem]:
        """采集公司新闻"""
        self._limiter.acquire()
        try:
            raw_news = client.company_news(ticker, _from=date_from, to=date_to)
        except finnhub.FinnhubAPIException as e:
            if e.status_code == 429:
                logger.warning(f"[Finnhub] Rate limited on company_news for {ticker}")
            else:
                logger.warning(f"[Finnhub] Failed to fetch news for {ticker}: {e}")
            return []
        except Exception as e:
            logger.warning(f"[Finnhub] Failed to fetch news for {ticker}: {e}")
            return []

        items = []
        for article in raw_news:
            try:
                ts = article.get('datetime', 0)
                published = datetime.utcfromtimestamp(ts).strftime('%Y-%m-%dT%H:%M:%SZ') if ts else ''

                items.append(NewsItem(
                    title=article.get('headline', ''),
                    summary=article.get('summary', ''),
                    source=article.get('source', ''),
                    published_at=published,
                    url=article.get('url', ''),
                    ticker=ticker,
                    category='news',
                    collector=self.name,
                ))
            except Exception as e:
                logger.warning(f"[Finnhub] Failed to parse article: {e}")
                continue

        return items

    def _fetch_earnings(
        self, client: finnhub.Client, ticker: str,
        date_from: str, date_to: str,
    ) -> list[NewsItem]:
        """采集财报日历"""
        self._limiter.acquire()
        try:
            data = client.earnings_calendar(_from=date_from, to=date_to, symbol=ticker)
            earnings_list = data.get('earningsCalendar', [])
        except finnhub.FinnhubAPIException as e:
            if e.status_code == 429:
                logger.warning(f"[Finnhub] Rate limited on earnings_calendar for {ticker}")
            else:
                logger.warning(f"[Finnhub] Failed to fetch earnings for {ticker}: {e}")
            return []
        except Exception as e:
            logger.warning(f"[Finnhub] Failed to fetch earnings for {ticker}: {e}")
            return []

        items = []
        for entry in earnings_list:
            report_date = entry.get('date', '')
            eps_actual = entry.get('epsActual')
            eps_estimate = entry.get('epsEstimate')
            revenue_actual = entry.get('revenueActual')

            parts = [f"Earnings report on {report_date}"]
            if eps_actual is not None:
                parts.append(f"EPS actual: {eps_actual}")
            if eps_estimate is not None:
                parts.append(f"EPS estimate: {eps_estimate}")
            if revenue_actual is not None:
                parts.append(f"Revenue: {revenue_actual:,.0f}")

            items.append(NewsItem(
                title=f"{ticker} Earnings Report - {report_date}",
                summary=". ".join(parts),
                source="Finnhub Earnings Calendar",
                published_at=f"{report_date}T00:00:00Z",
                url="",
                ticker=ticker,
                category='earnings',
                collector=self.name,
            ))

        return items
