"""EDGAR 采集器测试（CIK + submissions 路线）

背景: 旧 EFTS 全文搜索 q='"TICKER"' 实测 13 只小票仅 1/13 命中(8-K 正文用公司全名),
entity 参数被服务端忽略。本测试锁定新路线行为: ticker→CIK 映射 + submissions 按
CIK 列 filing + 窗口/form 过滤。
"""

import json

from unittest.mock import MagicMock

import pytest

from BreakoutStrategy.news_sentiment.collectors.edgar_collector import (
    CIK_MAP_PATH, EdgarCollector,
)
from BreakoutStrategy.news_sentiment.config import EdgarConfig

# --- 固定测试数据 ---

TICKER_MAP = {
    "0": {"cik_str": 839470, "ticker": "WWR", "title": "Westwater Resources"},
    "1": {"cik_str": 18255, "ticker": "CATO", "title": "Cato Corp"},
}

SUBMISSIONS = {
    "name": "WESTWATER RESOURCES, INC.",
    "filings": {"recent": {
        "form": ["8-K", "8-K", "10-Q", "4", "8-K/A"],
        "filingDate": ["2025-10-01", "2025-09-20", "2025-10-03", "2025-10-02", "2025-10-05"],
        "accessionNumber": ["0001-25-001", "0001-25-002", "0001-25-003",
                            "0001-25-004", "0001-25-005"],
        "primaryDocument": ["wwr8k.htm", "wwr8k2.htm", "wwr10q.htm", "form4.xml", "adj.htm"],
        "primaryDocDescription": ["8-K", None, None, None, None],
        "items": ["Items 2.02, 9.01", "Items 3.02", None, None, None],
    }},
}


def _make_collector(map_json=None, submissions_json=None):
    """构造 collector 并 mock 掉 HTTP session（submissions 响应可重复消费）。"""
    col = EdgarCollector(EdgarConfig(user_agent="test@example.com", enable=True))
    sess = MagicMock()
    resp_map, resp_sub = MagicMock(), MagicMock()
    resp_map.json.return_value = map_json if map_json is not None else TICKER_MAP
    resp_sub.json.return_value = submissions_json if submissions_json is not None else SUBMISSIONS
    sess.get.side_effect = lambda url, **kw: resp_sub if "submissions" in url else resp_map
    col._session = sess
    return col, sess


def test_collect_filters_window_and_forms(tmp_path, monkeypatch):
    """窗口内只留 8-K/10-K/10-Q; form 4 被滤; 窗外 8-K 被滤。"""
    monkeypatch.setattr("BreakoutStrategy.news_sentiment.collectors.edgar_collector.CIK_MAP_PATH",
                        tmp_path / "ticker_cik.json")
    col, _ = _make_collector()
    items = col.collect("WWR", "2025-09-29", "2025-10-06")
    forms = [i.title.split(" - ")[1].split(" (")[0] for i in items]
    assert forms == ["8-K", "10-Q"]


def test_collect_item_semantics_in_summary(tmp_path, monkeypatch):
    """8-K items 编号展开为语义描述(3.02=稀释), 供 LLM 分析。"""
    monkeypatch.setattr("BreakoutStrategy.news_sentiment.collectors.edgar_collector.CIK_MAP_PATH",
                        tmp_path / "ticker_cik.json")
    col, _ = _make_collector()
    items = col.collect("WWR", "2025-09-29", "2025-10-06")
    dilution = [i for i in items if "3.02" in (i.summary or "")]
    # 窗内 8-K 是 2.02(业绩), 稀释 3.02 在窗外 → 空列表即正确; 换窗口验证语义展开
    items2 = col.collect("WWR", "2025-09-15", "2025-09-25")
    assert any("Unregistered Sales" in (i.summary or "") for i in items2)


def test_collect_fields(tmp_path, monkeypatch):
    """NewsItem 字段: category=filing, source=SEC EDGAR, URL 由 CIK+accession 拼接。"""
    monkeypatch.setattr("BreakoutStrategy.news_sentiment.collectors.edgar_collector.CIK_MAP_PATH",
                        tmp_path / "ticker_cik.json")
    col, _ = _make_collector()
    items = col.collect("WWR", "2025-09-29", "2025-10-06")
    eightk = items[0]
    assert eightk.category == "filing"
    assert eightk.source == "SEC EDGAR"
    assert eightk.ticker == "WWR"
    assert eightk.published_at == "2025-10-01T00:00:00Z"
    assert "WESTWATER" in eightk.title
    assert eightk.url == ("https://www.sec.gov/Archives/edgar/data/"
                          "839470/000125001/wwr8k.htm")


def test_unknown_ticker_returns_empty(tmp_path, monkeypatch):
    """映射表无此 ticker(OTC 无报告义务壳票) → 空列表不抛。"""
    monkeypatch.setattr("BreakoutStrategy.news_sentiment.collectors.edgar_collector.CIK_MAP_PATH",
                        tmp_path / "ticker_cik.json")
    col, _ = _make_collector()
    assert col.collect("ZZZZZ", "2025-09-29", "2025-10-06") == []


def test_cik_map_downloaded_once_then_reused(tmp_path, monkeypatch):
    """映射表下载后落盘, 第二个 collector 实例读文件不再下载。"""
    map_path = tmp_path / "ticker_cik.json"
    monkeypatch.setattr("BreakoutStrategy.news_sentiment.collectors.edgar_collector.CIK_MAP_PATH",
                        map_path)
    col, sess = _make_collector()
    col.collect("WWR", "2025-09-29", "2025-10-06")
    assert map_path.exists()
    assert json.loads(map_path.read_text()) == TICKER_MAP
    # 第二实例: 只需 1 次请求(submissions), 映射不再下载
    col2, sess2 = _make_collector()
    resp_sub2 = MagicMock()
    resp_sub2.json.return_value = SUBMISSIONS
    sess2.get.side_effect = [resp_sub2]
    col2.collect("WWR", "2025-09-29", "2025-10-06")
    assert sess2.get.call_count == 1


def test_cik_map_download_failure_degrades_empty(tmp_path, monkeypatch):
    """映射表下载失败 → 后续 ticker 全返回空(采集失败=空列表契约), 不抛。"""
    monkeypatch.setattr("BreakoutStrategy.news_sentiment.collectors.edgar_collector.CIK_MAP_PATH",
                        tmp_path / "ticker_cik.json")
    col = EdgarCollector(EdgarConfig(user_agent="t@e.com", enable=True))
    sess = MagicMock()
    sess.get.side_effect = OSError("network down")
    col._session = sess
    assert col.collect("WWR", "2025-09-29", "2025-10-06") == []


def test_cik_path_module_constant():
    """映射缓存路径约定在 cache/news_sentiment/ 下(gitignored)。"""
    assert CIK_MAP_PATH.name == "ticker_cik.json"
    assert "cache" in str(CIK_MAP_PATH)
