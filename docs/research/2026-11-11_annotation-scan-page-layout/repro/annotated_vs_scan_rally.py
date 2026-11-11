"""一次性:标注过的股票(经 read_annotations)与扫描文件里有 hit 的股票、大涨段清单(GET /rally,只读)的重合。只读。"""
import json, sys, urllib.request
from pathlib import Path
from path2_web.config import load_config
from path2_web.annotation.store import read_annotations

st = read_annotations(load_config())["state"]
ann = {}
for c in st["charts"]:
    days = sorted(s["date"] for s in c["samples"]) if c["samples"] else []
    ann[c["symbol"]] = days
print("annotated:", ann)

for f in sorted(Path("outputs/path2_web/scans").glob("*.json")):
    d = json.loads(f.read_text())
    hit = set()
    for r in d["results"]:
        for pid, pr in (r.get("per_pattern") or {}).items():
            sm = (pr or {}).get("summary") or {}
            if (sm.get("hits") or sm.get("matches") or 0) > 0:
                hit.add(r["symbol"])
    allsym = {r["symbol"] for r in d["results"]}
    print(f.name, d.get("pattern_ids"), "| hit stocks:", len(hit), "| annotated ∩ hit:", sorted(set(ann) & hit),
          "| annotated ∩ listed:", sorted(set(ann) & allsym))

rally = json.load(urllib.request.urlopen("http://localhost:8001/rally"))
by = {}
for it in rally:
    by.setdefault(it["symbol"], []).append(it["date"])
print("rally rows:", len(rally), "| annotated ∩ rally:", {s: by[s] for s in ann if s in by},
      "| annotated not in rally:", [s for s in ann if s not in by])
