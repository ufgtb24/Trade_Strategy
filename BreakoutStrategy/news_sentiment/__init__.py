"""
新闻情感分析模块

通过多源采集股票新闻/公告/财报，结合 GLM-4.7-Flash 进行情感分析，辅助突破策略决策。

核心组件:
- models: 数据模型 (NewsItem, SentimentResult, AnalyzedItem, SummaryResult, AnalysisReport)
- collectors: 多源采集器 (Finnhub, AlphaVantage, EDGAR)
- analyzer: GLM-4.7-Flash 情感分析器
- reporter: JSON 报告生成
- api: 公共入口 analyze()

使用方式:
    from BreakoutStrategy.news_sentiment.api import analyze
    report = analyze("AAPL", "2026-03-01", "2026-03-15")

命令行入口:
    uv run -m BreakoutStrategy.news_sentiment
"""
