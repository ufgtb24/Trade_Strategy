"""
多源新闻采集器

提供 BaseCollector 抽象和三个实现:
- FinnhubCollector: 新闻 + 财报 + SEC filings
- AlphaVantageCollector: 情感增强的新闻
- EdgarCollector: SEC 8-K 公告
"""

from .base import BaseCollector
from .finnhub_collector import FinnhubCollector
from .alphavantage_collector import AlphaVantageCollector
from .edgar_collector import EdgarCollector

__all__ = ['BaseCollector', 'FinnhubCollector', 'AlphaVantageCollector', 'EdgarCollector']
