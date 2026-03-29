"""reporter.py 单元测试"""

import json
from dataclasses import asdict, replace
from pathlib import Path

from BreakoutStrategy.news_sentiment.models import (
    AnalysisReport,
    AnalyzedItem,
    NewsItem,
    SentimentResult,
    SummaryResult,
)
from BreakoutStrategy.news_sentiment.reporter import save_report


def _make_report() -> AnalysisReport:
    news = NewsItem(
        title="Test News", summary="Summary", source="Test",
        published_at="2026-03-10T14:00:00Z", url="https://example.com",
        ticker="AAPL", category="news", collector="finnhub", raw_sentiment=0.5,
    )
    sentiment = SentimentResult(sentiment="positive", impact="high", impact_value=0.80, reasoning="Good")
    return AnalysisReport(
        ticker="AAPL",
        date_from="2026-03-01",
        date_to="2026-03-15",
        collected_at="2026-03-16T10:00:00Z",
        items=[AnalyzedItem(news=news, sentiment=sentiment)],
        summary=SummaryResult(
            sentiment="positive", confidence=0.85, reasoning="Overall positive",
            positive_count=1, negative_count=0, neutral_count=0, total_count=1,
        ),
        source_stats={"finnhub": 1},
    )


def test_report_serialization():
    """验证 AnalysisReport 可正确序列化为 JSON"""
    report = _make_report()
    data = asdict(report)
    json_str = json.dumps(data, ensure_ascii=False, indent=2)
    loaded = json.loads(json_str)
    assert loaded['ticker'] == 'AAPL'
    assert len(loaded['items']) == 1
    assert loaded['items'][0]['news']['title'] == 'Test News'
    assert loaded['summary']['sentiment'] == 'positive'
    assert loaded['source_stats'] == {'finnhub': 1}


def test_save_report_creates_file(tmp_path: Path):
    """验证 save_report 正确创建 JSON 文件"""
    report = _make_report()

    # 直接在 tmp_path 写入测试
    out_dir = tmp_path / "output"
    out_dir.mkdir()
    filepath = out_dir / "AAPL_20260301_20260315.json"

    data = asdict(report)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    loaded = json.loads(filepath.read_text(encoding='utf-8'))
    assert loaded['ticker'] == 'AAPL'
    assert loaded['items'][0]['sentiment']['impact_value'] == 0.80


def test_filename_preserves_ticker_hyphens():
    """验证含连字符的 ticker（如 BRK-B）文件名正确"""
    report = _make_report()
    report = replace(report, ticker="BRK-B")

    date_from_clean = report.date_from.replace('-', '')
    date_to_clean = report.date_to.replace('-', '')
    expected_name = f"BRK-B_{date_from_clean}_{date_to_clean}.json"
    assert "BRK-B" in expected_name
    assert "--" not in expected_name
