# -*- coding: utf-8 -*-
"""小样本回填：bb_v1 eval 买点 × 买点前 7 天新闻窗口，实测 Finnhub 免费档可得性。

用法（参数在 main() 头部改，不用 argparse）:
    uv run python docs/research/2026-08-16_news-sentiment-path2-integration/repro/prefill_sample.py

实测口径:
- 样本来源: 主目录 bb_v1 eval 输出（210 行 symbol+buy_date, 2025-03..12）
- 窗口: buy_date 前 7 天含当日（bs daily_runner 同口径）
- 覆盖率/历史深度: 按买点月份分组的 collected/analyzed 条数
"""
import json
import logging
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

from BreakoutStrategy.news_sentiment.api import analyze  # noqa: E402
from BreakoutStrategy.news_sentiment.collectors.finnhub_collector import FinnhubCollector  # noqa: E402
from BreakoutStrategy.news_sentiment.config import load_config as load_sentiment_config  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent


def calibrate_min_buy_date() -> str:
    """动态标定 Finnhub 免费档滚动边界 → 安全 min_buy_date。

    语义: 逐档(AAPL 单日探针, 从老到新)找「有数据的最老一天」d*;
    边界 ≤ d* ⟹ 买点 ≥ d*+7 时其 7 天窗口首日 ≥ d*, 全窗可采。
    全档无数据/网络失败 → 回退静态偏移 today-300d(保守)。
    成本: 1-3 个 company-news call。
    """
    cfg = load_sentiment_config()
    col = FinnhubCollector(cfg.finnhub, proxy=cfg.proxy)
    for offset_days in (365, 350, 335, 320):
        d = (date.today() - timedelta(days=offset_days)).isoformat()
        try:
            items = [i for i in col.collect("AAPL", d, d) if i.category == "news"]
        except Exception as e:
            logging.warning(f"calibrate probe failed at {d}: {e}")
            break
        logging.info(f"calibrate probe AAPL@{d}(-{offset_days}d): {len(items)} items")
        if items:
            oldest = date.fromisoformat(d) + timedelta(days=7)
            print(f"[calibrate] Finnhub 边界 ≤ {d} → min_buy_date = {oldest.isoformat()}")
            return oldest.isoformat()
        time.sleep(1.1)
    fallback = (date.today() - timedelta(days=300)).isoformat()
    print(f"[calibrate] 探针全无数据/失败, 回退静态偏移: {fallback}")
    return fallback


def pick_sample(rows: list[dict], n: int, min_buy_date: str = "") -> list[dict]:
    """按买点月份分层抽样, 每 symbol 取最早买点一行。min_buy_date 过滤滚动窗口内买点。"""
    by_sym: dict[str, dict] = {}
    for r in sorted(rows, key=lambda r: r["buy_date"]):
        if min_buy_date and r["buy_date"] < min_buy_date:
            continue
        by_sym.setdefault(r["symbol"], r)
    uniq = sorted(by_sym.values(), key=lambda r: r["buy_date"])
    months = sorted({r["buy_date"][:7] for r in uniq})
    per = max(1, n // len(months))
    picked: list[dict] = []
    pools: dict[str, list[dict]] = defaultdict(list)
    for r in uniq:
        pools[r["buy_date"][:7]].append(r)
    # 轮转补齐: 每月先取 per 只, 不够 n 再从富余月补
    for m in months:
        picked.extend(pools[m][:per])
    i = 0
    while len(picked) < n:
        m = months[i % len(months)]
        extra = pools[m][per:] if per else pools[m]
        if extra:
            picked.append(extra.pop(0))
        i += 1
        if i > 10 * n:  # 防御: 样本不足时退出
            break
    return picked[:n]


def main():
    # === 参数配置 ===
    eval_json = "/home/yu/PycharmProjects/Trade_Strategy/outputs/path2_eval/bb_v1_eval_20260810-235006.json"
    n_tickers = 30           # 链路试跑=2; 正式回填改 30
    lookback_days = 7
    include_buy_day = True
    log_level = "INFO"

    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Finnhub 滚动边界动态标定(AAPL 探针); 传 "YYYY-MM-DD" 字符串可手动固定(复现实验用)
    min_buy_date = calibrate_min_buy_date()

    rows = json.load(open(eval_json))["results"]
    sample = pick_sample(rows, n_tickers, min_buy_date)
    print(f"sample: {[(r['symbol'], r['buy_date']) for r in sample]}")

    out = []
    for i, r in enumerate(sample, 1):
        sym, buy = r["symbol"], r["buy_date"]
        end = datetime.strptime(buy, "%Y-%m-%d")
        end -= timedelta(days=0) if include_buy_day else timedelta(days=1)
        date_from = (end - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        date_to = end.strftime("%Y-%m-%d")

        t0 = time.time()
        rep = analyze(sym, date_from, date_to, save=False)
        elapsed = round(time.time() - t0, 1)
        s = rep.summary
        rec = {
            "symbol": sym, "buy_date": buy,
            "window": [date_from, date_to],
            "source_stats": rep.source_stats,
            "n_items": len(rep.items),
            "pos/neg/neu/fail": [s.positive_count, s.negative_count, s.neutral_count, s.fail_count],
            "total_count": s.total_count,
            "sentiment_score": round(s.sentiment_score, 4),
            "rho": round(s.rho, 4),
            "elapsed_s": elapsed,
        }
        out.append(rec)
        print(f"[{i}/{len(sample)}] {sym} {buy} w={date_from}..{date_to} "
              f"items={rec['n_items']} total={rec['total_count']} "
              f"score={rec['sentiment_score']:+.3f} {elapsed}s")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = OUT_DIR / f"prefill_n{n_tickers}_{stamp}.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"\nsaved: {out_path}")
    covered = sum(1 for r in out if r["total_count"] > 0)
    print(f"coverage: {covered}/{len(out)} tickers have analyzed sentiment")


if __name__ == "__main__":
    main()
