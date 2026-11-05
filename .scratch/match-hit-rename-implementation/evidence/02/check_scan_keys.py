"""票 02 验收：检查一份新扫的 scan 文件只有新键（只读）。
用法：python check_scan_keys.py <scan 文件>；有旧键或缺新键时退出码 1。
输出只有键名与计数，不含行情或收益。"""
import json
import re
import sys
from collections import Counter

blob = json.load(open(sys.argv[1], encoding="utf-8"))
keys: Counter = Counter()


def walk(o):
    if isinstance(o, dict):
        for k, v in o.items():
            keys[k] += 1
            walk(v)
    elif isinstance(o, list):
        for v in o:
            walk(v)


walk(blob)
old = sorted(k for k in keys if re.search(r"match", k, re.I))
scan = blob["scan"]
pid = blob["pattern_ids"][0]
res = blob["results"]
ok_new = {
    "scan.hit_stocks": "hit_stocks" in scan,
    "scan 段没有 hits": "hits" not in scan,
    "summary.hits": all("hits" in r["per_pattern"][pid]["summary"] for r in res),
    "analysis.hits": all("hits" in r["per_pattern"][pid]["analysis"] for r in res),
    "analysis 没有 matches": all("matches" not in r["per_pattern"][pid]["analysis"] for r in res),
    "每条 hit 有 hit_id": all("hit_id" in h for r in res for h in r["per_pattern"][pid]["analysis"]["hits"]),
    "hit_fp_counts": all("hit_fp_counts" in r["per_pattern"][pid] for r in res),
    "per_leaf_hit_count_distribution": "per_leaf_hit_count_distribution" in blob["per_pattern"][pid]["stats"]["shared_leaf_stats"],
    "hit_stocks = 有 hit 的股票数": scan["hit_stocks"] == sum(r["per_pattern"][pid]["summary"]["hits"] > 0 for r in res),
    "data_until 不晚于训练段末日": scan.get("data_until") == "2025-12-31",
    "读的是训练段副本": scan["dataset_dir"].endswith("datasets/pkls_until_20251231"),
}
print("scanned", scan["scanned"], "hit_stocks", scan["hit_stocks"], "errors", scan["errors"],
      "Σ hits", sum(r["per_pattern"][pid]["summary"]["hits"] for r in res))
print("含 match 字样的键:", old)
print("含 hit 字样的键:", sorted(k for k in keys if "hit" in k))
for k, v in ok_new.items():
    print(("ok  " if v else "FAIL"), k)
sys.exit(0 if not old and all(ok_new.values()) else 1)
