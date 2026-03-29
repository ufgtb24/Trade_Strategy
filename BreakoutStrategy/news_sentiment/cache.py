"""
新闻情感分析缓存

两层缓存:
  1. NewsItem 缓存 — 避免重复采集（按 ticker+collector+日期索引）
  2. SentimentResult 缓存 — 避免重复 LLM 分析（按 news_fingerprint+backend+model 索引）

使用 SQLite 持久化，支持回测场景的跨次复用。
"""

import hashlib
import json
import logging
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from BreakoutStrategy.news_sentiment.config import CacheConfig
from BreakoutStrategy.news_sentiment.models import NewsItem, SentimentResult

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def news_fingerprint(item: NewsItem) -> str:
    """生成新闻的唯一指纹（16字符 hex）"""
    if item.url:
        return hashlib.sha256(item.url.encode()).hexdigest()[:16]
    key = f"{item.title}|{item.published_at}|{item.source}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def compute_uncovered_ranges(
    requested: tuple[str, str],
    covered: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """
    计算请求范围中未被覆盖的子区间（区间差集）

    Args:
        requested: (date_from, date_to) YYYY-MM-DD
        covered: 已覆盖区间列表

    Returns:
        未覆盖的子区间列表
    """
    req_start = date.fromisoformat(requested[0])
    req_end = date.fromisoformat(requested[1])

    if not covered:
        return [requested]

    # 排序并合并已覆盖区间
    intervals = sorted(
        (date.fromisoformat(s), date.fromisoformat(e)) for s, e in covered
    )
    merged = [intervals[0]]
    for s, e in intervals[1:]:
        if s <= merged[-1][1] + timedelta(days=1):
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    # 从 requested 中减去 merged
    uncovered = []
    cursor = req_start
    for cs, ce in merged:
        if cursor > req_end:
            break
        if cs > cursor:
            uncovered.append((
                cursor.isoformat(),
                min(cs - timedelta(days=1), req_end).isoformat(),
            ))
        cursor = max(cursor, ce + timedelta(days=1))

    if cursor <= req_end:
        uncovered.append((cursor.isoformat(), req_end.isoformat()))

    return uncovered


class SentimentCache:
    """新闻情感分析缓存管理器"""

    def __init__(self, config: CacheConfig):
        self._enabled = config.enable
        self._news_ttl = config.news_ttl_days
        self._sentiment_ttl = config.sentiment_ttl_days

        if not self._enabled:
            self._conn = None
            return

        cache_dir = PROJECT_ROOT / config.cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)
        db_path = cache_dir / "cache.db"
        self._conn = sqlite3.connect(str(db_path))
        self._init_tables()

    def _init_tables(self):
        c = self._conn.cursor()
        # 迁移：检测旧 schema（confidence 列）→ 删除旧表
        c.execute("PRAGMA table_info(sentiments)")
        cols = {row[1] for row in c.fetchall()}
        if 'confidence' in cols and 'impact' not in cols:
            c.execute("DROP TABLE sentiments")
            self._conn.commit()
        c.executescript("""
            CREATE TABLE IF NOT EXISTS news (
                fingerprint TEXT NOT NULL,
                ticker TEXT NOT NULL,
                collector TEXT NOT NULL,
                published_date TEXT NOT NULL,
                data JSON NOT NULL,
                created_at TEXT DEFAULT (date('now')),
                PRIMARY KEY (fingerprint)
            );
            CREATE INDEX IF NOT EXISTS idx_news_lookup
                ON news(ticker, collector, published_date);

            CREATE TABLE IF NOT EXISTS sentiments (
                fingerprint TEXT NOT NULL,
                backend TEXT NOT NULL,
                model TEXT NOT NULL,
                sentiment TEXT NOT NULL,
                impact TEXT NOT NULL DEFAULT '',
                impact_value REAL NOT NULL DEFAULT 0.0,
                reasoning TEXT NOT NULL,
                created_at TEXT DEFAULT (date('now')),
                PRIMARY KEY (fingerprint, backend, model)
            );

            CREATE TABLE IF NOT EXISTS coverage (
                ticker TEXT NOT NULL,
                collector TEXT NOT NULL,
                date_from TEXT NOT NULL,
                date_to TEXT NOT NULL,
                PRIMARY KEY (ticker, collector, date_from, date_to)
            );
        """)
        self._conn.commit()

    def put_news(self, ticker: str, collector: str, items: list[NewsItem]) -> None:
        """存储新闻条目到缓存"""
        if not self._enabled or not items:
            return
        c = self._conn.cursor()
        for item in items:
            fp = news_fingerprint(item)
            pub_date = item.published_at[:10] if item.published_at else ''
            data = json.dumps({
                'title': item.title, 'summary': item.summary,
                'source': item.source, 'published_at': item.published_at,
                'url': item.url, 'ticker': item.ticker,
                'category': item.category, 'collector': item.collector,
                'raw_sentiment': item.raw_sentiment,
            }, ensure_ascii=False)
            c.execute(
                "INSERT OR REPLACE INTO news (fingerprint, ticker, collector, published_date, data) "
                "VALUES (?, ?, ?, ?, ?)",
                (fp, ticker, collector, pub_date, data),
            )
        self._conn.commit()

    def get_news(self, ticker: str, date_from: str, date_to: str,
                 collector: str) -> list[NewsItem]:
        """按 ticker、日期范围、采集器查询缓存的新闻"""
        if not self._enabled:
            return []
        c = self._conn.cursor()
        c.execute(
            "SELECT data FROM news WHERE ticker=? AND collector=? "
            "AND published_date >= ? AND published_date <= ?",
            (ticker, collector, date_from, date_to),
        )
        items = []
        for (data_json,) in c.fetchall():
            d = json.loads(data_json)
            items.append(NewsItem(**d))
        return items

    def put_sentiment(self, fingerprint: str, backend: str, model: str,
                      result: SentimentResult) -> None:
        """存储情感分析结果到缓存"""
        if not self._enabled:
            return
        c = self._conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO sentiments "
            "(fingerprint, backend, model, sentiment, impact, impact_value, reasoning) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (fingerprint, backend, model,
             result.sentiment, result.impact, result.impact_value, result.reasoning),
        )
        self._conn.commit()

    def get_sentiment(self, fingerprint: str, backend: str,
                      model: str) -> SentimentResult | None:
        """查询缓存的情感分析结果"""
        if not self._enabled:
            return None
        c = self._conn.cursor()
        c.execute(
            "SELECT sentiment, impact, impact_value, reasoning FROM sentiments "
            "WHERE fingerprint=? AND backend=? AND model=?",
            (fingerprint, backend, model),
        )
        row = c.fetchone()
        if row is None:
            return None
        return SentimentResult(sentiment=row[0], impact=row[1], impact_value=row[2], reasoning=row[3])

    def get_covered_ranges(self, ticker: str,
                           collector: str) -> list[tuple[str, str]]:
        """查询已采集的日期范围"""
        if not self._enabled:
            return []
        c = self._conn.cursor()
        c.execute(
            "SELECT date_from, date_to FROM coverage "
            "WHERE ticker=? AND collector=?",
            (ticker, collector),
        )
        return [(r[0], r[1]) for r in c.fetchall()]

    def update_coverage(self, ticker: str, collector: str,
                        date_from: str, date_to: str) -> None:
        """记录已采集的日期范围"""
        if not self._enabled:
            return
        c = self._conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO coverage (ticker, collector, date_from, date_to) "
            "VALUES (?, ?, ?, ?)",
            (ticker, collector, date_from, date_to),
        )
        self._conn.commit()

    def stats(self) -> dict:
        """返回缓存统计信息"""
        if not self._enabled:
            return {"enabled": False}
        c = self._conn.cursor()
        c.execute("SELECT COUNT(*) FROM news")
        news_count = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM sentiments")
        sentiment_count = c.fetchone()[0]
        return {"enabled": True, "news": news_count, "sentiments": sentiment_count}

    def clear(self, ticker: str | None = None) -> None:
        """清除缓存，可按 ticker 清除或全部清除"""
        if not self._enabled:
            return
        c = self._conn.cursor()
        if ticker:
            # 先删 sentiments（依赖 news 表做子查询），再删 news
            c.execute("DELETE FROM sentiments WHERE fingerprint IN "
                       "(SELECT fingerprint FROM news WHERE ticker=?)", (ticker,))
            c.execute("DELETE FROM news WHERE ticker=?", (ticker,))
            c.execute("DELETE FROM coverage WHERE ticker=?", (ticker,))
        else:
            c.execute("DELETE FROM news")
            c.execute("DELETE FROM sentiments")
            c.execute("DELETE FROM coverage")
        self._conn.commit()
