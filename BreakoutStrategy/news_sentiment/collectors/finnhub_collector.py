"""
Finnhub 采集器

采集公司新闻 (/company-news) 和财报日历 (/calendar/earnings)。
免费 tier: 60次/分钟，无日限。
"""

import logging
from datetime import datetime

import finnhub

from BreakoutStrategy.news_sentiment.config import CollectorConfig
from BreakoutStrategy.news_sentiment.models import NewsItem

from .base import BaseCollector

logger = logging.getLogger(__name__)


class FinnhubCollector(BaseCollector):
    """Finnhub 新闻采集器"""

    name = "finnhub"

    def __init__(self, config: CollectorConfig, proxy: str = ''):
        self._config = config
        self._proxy = proxy
        self._client: finnhub.Client | None = None

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

    def _fetch_company_news(
        self, client: finnhub.Client, ticker: str,
        date_from: str, date_to: str,
    ) -> list[NewsItem]:
        """采集公司新闻"""
        try:
            raw_news = client.company_news(ticker, _from=date_from, to=date_to)
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
        try:
            data = client.earnings_calendar(_from=date_from, to=date_to, symbol=ticker)
            earnings_list = data.get('earningsCalendar', [])
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
