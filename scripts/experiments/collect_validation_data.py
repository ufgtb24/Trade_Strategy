"""
真实数据验证脚本

采集多股票多时段新闻，用校准后参数聚合，验证 sentiment_score 分布合理性。
"""

import dataclasses
import json
import logging
from pathlib import Path

from BreakoutStrategy.news_sentiment.api import analyze


def main():
    # === 参数配置 ===
    tickers = ["AAPL", "TSLA", "NVDA", "META", "AMZN", "JPM", "JNJ", "XOM"]
    periods = [
        ("2025-04-01", "2025-04-14"),
        ("2025-07-01", "2025-07-14"),
        ("2025-10-01", "2025-10-14"),
    ]
    output_dir = Path("datasets/news_sentiment_validation")
    log_level = "INFO"

    # === 初始化 ===
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
        datefmt='%H:%M:%S',
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    # === 采集 + 分析 ===
    all_scores = []
    all_impacts = []
    total_fail = 0
    total_items = 0

    for ticker in tickers:
        for date_from, date_to in periods:
            print(f"\n--- {ticker} {date_from}~{date_to} ---")
            report = analyze(ticker, date_from, date_to)

            # 存储
            d_from = date_from.replace('-', '')
            d_to = date_to.replace('-', '')
            filepath = output_dir / f"{ticker}_{d_from}_{d_to}.json"
            data = dataclasses.asdict(report)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"  Saved to {filepath}")

            # 统计
            s = report.summary
            print(f"  Score: {s.sentiment_score:+.4f} ({s.sentiment})")
            print(f"  Items: {len(report.items)}, fail: {s.fail_count}")
            all_scores.append(s.sentiment_score)
            total_fail += s.fail_count
            total_items += s.total_count
            for item in report.items:
                if item.sentiment.impact:
                    all_impacts.append(item.sentiment.impact)

    # === 汇总验证 ===
    print(f"\n{'='*60}")
    print(f"VALIDATION SUMMARY")
    print(f"{'='*60}")
    print(f"Total reports: {len(tickers) * len(periods)}")
    if total_items > 0:
        print(f"Total items: {total_items}, fail: {total_fail} "
              f"({total_fail/total_items*100:.1f}%)")

    # sentiment_score 分布
    if all_scores:
        in_range = sum(1 for s in all_scores if -0.50 <= s <= 0.50)
        print(f"\nsentiment_score distribution:")
        print(f"  Range [-0.50, +0.50]: {in_range}/{len(all_scores)} "
              f"({in_range/len(all_scores)*100:.0f}%) — target >80%")
        print(f"  Min: {min(all_scores):+.4f}, Max: {max(all_scores):+.4f}")

    # impact 分布
    if all_impacts:
        from collections import Counter
        counts = Counter(all_impacts)
        total_imp = len(all_impacts)
        low_pct = (counts.get('negligible', 0) + counts.get('low', 0)) / total_imp
        print(f"\nimpact distribution:")
        for level in ['negligible', 'low', 'medium', 'high', 'extreme']:
            c = counts.get(level, 0)
            print(f"  {level:>10}: {c:3d} ({c/total_imp*100:5.1f}%)")
        print(f"  negligible+low: {low_pct*100:.0f}% — target >50%")

    # 失败率
    if total_items > 0:
        fail_rate = total_fail / total_items
        print(f"\nLLM fail rate: {fail_rate*100:.1f}% — target <5%")
        status = "PASS" if fail_rate < 0.05 else "FAIL"
        print(f"  Status: {status}")


if __name__ == "__main__":
    main()
