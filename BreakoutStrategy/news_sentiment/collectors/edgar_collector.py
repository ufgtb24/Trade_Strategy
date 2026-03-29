"""
SEC EDGAR 采集器

使用 EDGAR EFTS (full-text search) API 搜索公司公告。
完全免费，无需 API key，仅需 User-Agent header。
限流: 10次/秒。
"""

import logging
import time

import requests

from BreakoutStrategy.news_sentiment.config import EdgarConfig
from BreakoutStrategy.news_sentiment.models import NewsItem

from .base import BaseCollector

logger = logging.getLogger(__name__)

EFTS_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
FILING_BASE_URL = "https://www.sec.gov/Archives/edgar/data"


class EdgarCollector(BaseCollector):
    """SEC EDGAR 公告采集器"""

    name = "edgar"

    def __init__(self, config: EdgarConfig, proxy: str = ''):
        self._config = config
        self._session = requests.Session()
        self._session.headers.update({
            'User-Agent': self._config.user_agent,
            'Accept': 'application/json',
        })
        if proxy:
            self._session.proxies = {'https': proxy, 'http': proxy}

    def is_available(self) -> bool:
        return True

    def collect(self, ticker: str, date_from: str, date_to: str) -> list[NewsItem]:
        """搜索 SEC EDGAR 公告（8-K 为主）"""
        items: list[NewsItem] = []

        for form_type in ['8-K', '10-K', '10-Q']:
            items.extend(self._search_filings(ticker, date_from, date_to, form_type))
            time.sleep(0.15)

        logger.info(f"[EDGAR] {ticker}: collected {len(items)} items")
        return items

    def _search_filings(
        self, ticker: str, date_from: str, date_to: str, form_type: str,
    ) -> list[NewsItem]:
        """通过 EFTS 搜索特定类型的公告"""
        params = {
            'q': f'"{ticker}"',
            'dateRange': 'custom',
            'startdt': date_from,
            'enddt': date_to,
            'forms': form_type,
        }

        try:
            resp = self._session.get(EFTS_SEARCH_URL, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"[EDGAR] Search failed for {ticker} {form_type}: {e}")
            return []

        hits = data.get('hits', {}).get('hits', [])
        items = []

        for hit in hits:
            try:
                source = hit.get('_source', {})
                filing_date = source.get('file_date', '')
                form = source.get('form_type', form_type)
                entity_name = source.get('entity_name', ticker)
                file_num = source.get('file_num', '')
                description = source.get('display_names', [''])[0] if source.get('display_names') else ''

                accession = source.get('accession_no', '').replace('-', '')
                filing_url = ''
                if accession:
                    cik = source.get('entity_id', '')
                    filing_url = f"{FILING_BASE_URL}/{cik}/{accession}"

                items.append(NewsItem(
                    title=f"{entity_name} - {form} Filing ({filing_date})",
                    summary=description or f"{form} filing by {entity_name}. File number: {file_num}",
                    source="SEC EDGAR",
                    published_at=f"{filing_date}T00:00:00Z" if filing_date else '',
                    url=filing_url,
                    ticker=ticker,
                    category='filing',
                    collector=self.name,
                ))
            except Exception as e:
                logger.warning(f"[EDGAR] Failed to parse filing: {e}")
                continue

        return items
