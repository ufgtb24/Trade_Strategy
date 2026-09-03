# -*- coding: utf-8 -*-
"""DeepSeek V4 Flash vs V4 Pro 在金融新闻情感标注上的准确率对比(生产后端逐条推理)。

背景: 2026-08-16 实测 deepseek-v3 已下线(API 只接受 v4 系列), deepseek-chat 已被
官方别名到 deepseek-v4-flash。V3 无法现场重测, 其 92.5%(v3 benchmark 报告, 同一份数据
+ 同生产后端) 作为历史对照引用。
GT: ground_truth_v2.csv(Opus 4.6 × 40 独立子代理标注) — 与历史 benchmark 同源, 直接可比。
"""
import csv
import json
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

import yaml

from BreakoutStrategy.news_sentiment.backends.deepseek_backend import DeepSeekBackend
from BreakoutStrategy.news_sentiment.config import AnalyzerConfig
from BreakoutStrategy.news_sentiment.models import NewsItem

BENCH = Path("/home/yu/PycharmProjects/Trade_Strategy/experiments/news_sentiment_benchmark/results")
OUT_DIR = Path(__file__).resolve().parent


def load_data():
    data = list(csv.DictReader(open(BENCH / "benchmark_data.csv", encoding="utf-8")))
    gt = {int(r["id"]): r["sentiment"]
          for r in csv.DictReader(open(BENCH / "ground_truth_v2.csv", encoding="utf-8"))}
    items = [NewsItem(title=r["title"], summary=r["summary"], source=r["source"],
                      published_at=r["published_at"], url="", ticker="AAPL",
                      category="news", collector=r["collector"]) for r in data]
    gt_labels = [gt[int(r["id"])] for r in data]
    return data, items, gt_labels


def run_model(model_id: str, items: list[NewsItem], api_key: str) -> dict:
    cfg = AnalyzerConfig(api_key=api_key, backend="deepseek", model=model_id,
                         temperature=0.1, max_concurrency=20, proxy="")  # proxy 已停,直连
    backend = DeepSeekBackend(cfg)
    t0 = time.time()
    results = backend.analyze_all(items, "AAPL")
    elapsed = time.time() - t0
    preds = [r.sentiment for r in results]
    fails = sum(1 for r in results if not r.impact)
    return {"model": model_id, "preds": preds, "elapsed_s": round(elapsed, 1),
            "fail_count": fails, "results": results}


def metrics(gt_labels, preds):
    acc = sum(g == p for g, p in zip(gt_labels, preds)) / len(gt_labels)
    per_class = {}
    for label in ("positive", "negative", "neutral"):
        tp = sum(g == p == label for g, p in zip(gt_labels, preds))
        fp = sum(g != label and p == label for g, p in zip(gt_labels, preds))
        fn = sum(g == label and p != label for g, p in zip(gt_labels, preds))
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        per_class[label] = {"precision": round(prec, 2), "recall": round(rec, 2)}
    return acc, per_class


def main():
    # === 参数配置 ===
    models = ["deepseek-v4-flash", "deepseek-v4-pro"]
    history_v3_acc = 0.925  # benchmark_report_v3(同数据/同后端/同温度), V3 已下线无法重测

    api_key = yaml.safe_load(open(REPO_ROOT / "configs" / "api_keys.yaml"))["deepseek"]
    data, items, gt_labels = load_data()
    print(f"loaded {len(items)} items, GT dist: {dict(Counter(gt_labels))}")

    out = {"meta": {"date": "2026-08-16", "n": len(items),
                    "gt_dist": dict(Counter(gt_labels)),
                    "history": {"DeepSeek-V3(deepseek-chat@2026-03)": history_v3_acc}},
           "models": []}
    for model_id in models:
        m = run_model(model_id, items, api_key)
        acc, per_class = metrics(gt_labels, m["preds"])
        m["accuracy"] = round(acc, 4)
        m["per_class"] = per_class
        disagree = [{"i": i, "gt": g, "pred": p,
                     "title": data[i]["title"][:60]}
                    for i, (g, p) in enumerate(zip(gt_labels, m["preds"])) if g != p]
        m["disagreements"] = disagree
        out["models"].append(m)
        print(f"{model_id}: acc={acc:.1%} fail={m['fail_count']} {m['elapsed_s']}s "
              f"disagree={len(disagree)}")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = OUT_DIR / f"benchmark_v4_{stamp}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    print(f"saved: {path}")
    print(f"\n对照: V3(历史)={history_v3_acc:.1%}", end="")
    for m in out["models"]:
        print(f" | {m['model']}={m['accuracy']:.1%}", end="")
    print()


if __name__ == "__main__":
    main()
