"""
SEC EDGAR 采集器（CIK + submissions 路线）。

为何弃用 EFTS 全文搜索: 旧实现 q='"TICKER"' 实测 13 只小票仅 1/13 命中
（8-K 正文用公司全名, ticker 词几乎不出现）, EFTS 的 entity 参数被服务端
忽略（返回全市场 8-K 流）。2026-08-16 验证的替代路线: 官方
company_tickers.json 做 ticker→CIK 映射 → data.sec.gov/submissions 按 CIK
列 recent filings → 窗口 + form 过滤。零撞词、无 key。

研究档案: docs/research/2026-08-16_news-sentiment-path2-integration.md §八。
"""

import json
import logging
import time
from pathlib import Path

import requests

from BreakoutStrategy.news_sentiment.config import EdgarConfig
from BreakoutStrategy.news_sentiment.models import NewsItem

from .base import BaseCollector

logger = logging.getLogger(__name__)

TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"

PROJECT_ROOT = Path(__file__).resolve().parents[3]
# 映射表缓存: 与 SentimentCache 同目录但独立文件(gitignored); 删除文件即强制重下
CIK_MAP_PATH = PROJECT_ROOT / "cache" / "news_sentiment" / "ticker_cik.json"

# 8-K item 编号 → 语义(展开进 summary 供 LLM 分析; 3.02 稀释对 micro-cap 假阳过滤尤其关键)
ITEM_DESC = {
    "1.01": "Entry into a Material Definitive Agreement",
    "2.01": "Completion of Acquisition or Disposition of Assets",
    "2.02": "Results of Operations and Financial Condition",
    "3.01": "Notice of Delisting or Failure to Satisfy a Continued Listing Rule",
    "3.02": "Unregistered Sales of Equity Securities (dilution)",
    "3.03": "Material Modification to Rights of Security Holders",
    "4.02": "Non-Reliance on Previously Issued Financial Statements",
    "5.02": "Departure/Election of Directors or Officers",
    "5.03": "Amendments to Articles of Incorporation or Bylaws",
    "7.01": "Regulation FD Disclosure",
    "8.01": "Other Events",
    "9.01": "Financial Statements and Exhibits",
}

FORMS = ("8-K", "10-K", "10-Q")


class EdgarCollector(BaseCollector):
    """SEC EDGAR 法定公告采集器(8-K 为主)。无 key; SEC 限流 10 req/s, 请求后 sleep 0.15s。"""

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
        self._cik_map: dict[str, int] | None = None

    def is_available(self) -> bool:
        return True

    def _load_cik_map(self) -> dict[str, int]:
        """加载 ticker→CIK 映射(内存 → 文件 → 下载全量并落盘)。下载失败抛异常由调用方降级。"""
        if self._cik_map is not None:
            return self._cik_map
        if CIK_MAP_PATH.exists():
            data = json.loads(CIK_MAP_PATH.read_text())
        else:
            resp = self._session.get(TICKER_MAP_URL, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            CIK_MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
            CIK_MAP_PATH.write_text(json.dumps(data))
        self._cik_map = {str(e["ticker"]).upper(): int(e["cik_str"]) for e in data.values()}
        return self._cik_map

    def collect(self, ticker: str, date_from: str, date_to: str) -> list[NewsItem]:
        """按 CIK 拉取该票窗口内的 8-K/10-K/10-Q filing。"""
        try:
            cik = self._load_cik_map().get(ticker.upper())
        except Exception as e:
            logger.warning(f"[EDGAR] CIK map unavailable ({e}); skipping all")
            self._cik_map = {}
            cik = None
        if cik is None:
            logger.info(f"[EDGAR] {ticker}: no CIK mapping (non-reporting?), skip")
            return []

        try:
            resp = self._session.get(SUBMISSIONS_URL.format(cik=cik), timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"[EDGAR] submissions failed for {ticker}: {e}")
            return []
        time.sleep(0.15)

        recent = data.get("filings", {}).get("recent", {})
        rows = zip(
            recent.get("form", []),
            recent.get("filingDate", []),
            recent.get("accessionNumber", []),
            recent.get("primaryDocument", []),
            recent.get("primaryDocDescription", []),
            recent.get("items", []),
        )
        entity = data.get("name", ticker)
        items: list[NewsItem] = []
        for form, fdate, accession, doc, desc, items_field in rows:
            if form not in FORMS or not fdate:
                continue
            if not (date_from <= fdate <= date_to):
                continue
            summary = self._build_summary(items_field, desc, entity)
            url = ARCHIVES_URL.format(
                cik=cik, acc=(accession or "").replace("-", ""), doc=doc or "",
            ) if accession else ""
            items.append(NewsItem(
                title=f"{entity} - {form} ({fdate})",
                summary=summary,
                source="SEC EDGAR",
                published_at=f"{fdate}T00:00:00Z",
                url=url,
                ticker=ticker,
                category='filing',
                collector=self.name,
            ))

        logger.info(f"[EDGAR] {ticker}: collected {len(items)} filings in window")
        return items

    @staticmethod
    def _build_summary(items_field: str | None, desc: str | None, entity: str) -> str:
        """8-K items 编号展开为语义描述; 无 items(10-K/10-Q) 用文档描述兜底。"""
        if items_field:
            nums = [n.strip() for n in items_field.replace("Items", "").replace("Item", "").split(",") if n.strip()]
            expanded = "; ".join(ITEM_DESC.get(n, n) for n in nums)
            return f"{items_field}: {expanded}" if expanded else str(items_field)
        return desc or f"SEC filing by {entity}"
