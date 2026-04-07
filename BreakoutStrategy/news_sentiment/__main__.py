"""
命令行入口

使用方式: uv run -m BreakoutStrategy.news_sentiment
"""

import logging
import math
from datetime import date

from BreakoutStrategy.news_sentiment.api import analyze


def main():
    # === 参数配置（不使用 argparse） ===
    ticker = "TSLA"
    date_from = "2026-03-01"
    date_to = "2026-03-15"
    log_level = "INFO"

    # === 初始化日志 ===
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
        datefmt='%H:%M:%S',
    )

    # === 执行分析 ===
    print(f"Analyzing {ticker} from {date_from} to {date_to}...")
    report = analyze(ticker, date_from, date_to)

    # === 输出结果 ===
    print(f"\n{'='*60}")
    print(f"Ticker: {report.ticker}")
    print(f"Period: {report.date_from} ~ {report.date_to}")
    print(f"Sources: {report.source_stats}")
    print(f"Total items: {len(report.items)}")
    s = report.summary
    print(f"\nSummary:")
    print(f"  Sentiment Score: {s.sentiment_score:+.4f}  ({s.sentiment})")
    print(f"  Reasoning: {s.reasoning}")
    print(f"  Breakdown: positive={s.positive_count} "
          f"negative={s.negative_count} "
          f"neutral={s.neutral_count}")
    print(f"  Internals: rho={s.rho:+.4f}, confidence={s.confidence:.4f}")
    if s.fail_count > 0:
        print(f"  Analysis failed: {s.fail_count}/{s.total_count}")
    print(f"{'='*60}")

    if report.items:
        # 时间衰减权重（与 _summarize 一致）
        half_life = 3.0
        decay_lambda = math.log(2) / half_life
        ref = date.fromisoformat(date_to)

        def _time_weight(item):
            pub = item.news.published_at[:10] if item.news.published_at else ''
            if not pub:
                return 1.0
            try:
                days = max(0, (ref - date.fromisoformat(pub)).days)
                return math.exp(-decay_lambda * days)
            except ValueError:
                return 1.0

        # 按 impact_value × time_weight 降序，non-neutral 优先
        ranked = sorted(
            report.items,
            key=lambda a: (
                a.sentiment.sentiment != 'neutral',
                a.sentiment.impact_value * _time_weight(a),
            ),
            reverse=True,
        )
        print(f"\nTop 5 influential items:")
        for item in ranked[:5]:
            tw = _time_weight(item)
            print(f"  [{item.sentiment.sentiment}|{item.sentiment.impact}|tw={tw:.2f}] "
                  f"{item.news.title[:60]}")


if __name__ == "__main__":
    main()
