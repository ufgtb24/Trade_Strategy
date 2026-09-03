# -*- coding: utf-8 -*-
"""对照测试: 分辨 Finnhub 免费档 0 条 = 历史深度受限 vs 小票无覆盖。

直接调 finnhub company_news（不走 analyze/LLM），大票×远近窗口对照。
"""
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

from BreakoutStrategy.news_sentiment.collectors.finnhub_collector import FinnhubCollector  # noqa: E402
from BreakoutStrategy.news_sentiment.config import load_config  # noqa: E402


def main():
    # === 参数配置 ===
    cases = [
        # (ticker, date_from, date_to, 说明)
        ("AAPL", "2026-08-09", "2026-08-16", "大票 最近一周"),
        ("AAPL", "2025-03-11", "2025-03-18", "大票 17个月前(=试跑窗口同期)"),
        ("TSLA", "2025-06-10", "2025-06-17", "大票 14个月前"),
        ("MAJI", "2026-08-09", "2026-08-16", "试跑小票 最近一周"),
    ]
    cfg = load_config()
    col = FinnhubCollector(cfg.finnhub, proxy=cfg.proxy)
    for sym, f, t, note in cases:
        t0 = time.time()
        items = col.collect(sym, f, t)
        news = [i for i in items if i.category == "news"]
        ern = [i for i in items if i.category != "news"]
        print(f"{sym} {f}..{t} [{note}]: news={len(news)} earnings={len(ern)} ({time.time()-t0:.1f}s)")
        for i in news[:2]:
            print(f"    e.g. {i.published_at} {i.title[:60]}")
        time.sleep(1.1)


if __name__ == "__main__":
    main()
