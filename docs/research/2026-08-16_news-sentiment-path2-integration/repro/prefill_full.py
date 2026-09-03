# -*- coding: utf-8 -*-
"""② 区分度试验 · 全量回填: 窗口内全部 eval 行逐行评分(按行, 同 symbol 不同买点独立窗口)。

 preregistration.md 的样本定义。输出 full_scores_*.json 供 join。
"""
import json
import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

from BreakoutStrategy.news_sentiment.api import analyze  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prefill_sample import calibrate_min_buy_date  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent


def main():
    # === 参数配置 ===
    eval_json = "/home/yu/PycharmProjects/Trade_Strategy/outputs/path2_eval/bb_v1_eval_20260810-235006.json"
    lookback_days = 7
    include_buy_day = True
    # 预注册值: 与 prefill_sample 动态标定一致(2026-08-16 标定 2025-09-07);
    # 复验时重标定并更新此处与 preregistration
    min_buy_date = "2025-09-07"
    log_level = "INFO"

    logging.basicConfig(level=getattr(logging, log_level),
                        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
                        datefmt="%H:%M:%S")

    rows = [r for r in json.load(open(eval_json))["results"]
            if r["buy_date"] >= min_buy_date]
    print(f"窗口内 eval 行: {len(rows)} (min_buy_date={min_buy_date})")

    out = []
    t_start = time.time()
    for i, r in enumerate(rows, 1):
        sym, buy = r["symbol"], r["buy_date"]
        end = datetime.strptime(buy, "%Y-%m-%d")
        if not include_buy_day:
            end -= timedelta(days=1)
        d_from = (end - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        d_to = end.strftime("%Y-%m-%d")
        rep = analyze(sym, d_from, d_to, save=False)
        s = rep.summary
        rec = {
            "symbol": sym, "buy_date": buy, "fr40": r["returns"]["40"],
            "window": [d_from, d_to],
            "total_count": s.total_count, "fail_count": s.fail_count,
            "sentiment_score": round(s.sentiment_score, 4),
            "rho": round(s.rho, 4),
            "p/n/n": [s.positive_count, s.negative_count, s.neutral_count],
            "source_stats": rep.source_stats,
        }
        out.append(rec)
        if i % 10 == 0 or i == len(rows):
            print(f"[{i}/{len(rows)}] {sym} {buy} score={s.sentiment_score:+.3f} "
                  f"total={s.total_count} ({time.time()-t_start:.0f}s)", flush=True)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = OUT_DIR / f"full_scores_{stamp}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    cov = sum(1 for r in out if r["total_count"] > 0)
    print(f"saved: {path}")
    print(f"coverage: {cov}/{len(out)}")


if __name__ == "__main__":
    main()
