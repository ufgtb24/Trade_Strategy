"""一次性:标注里各 pattern 有几只股票有样本 / 反馈,挑截图用的股票。只经 read_annotations 读,只读。"""
from collections import defaultdict
from path2_web.config import load_config
from path2_web.annotation.store import read_annotations
from path2_web.mapping import read_mappings

cfg = load_config()
st = read_annotations(cfg)["state"]
smp, fb, box_only = defaultdict(set), defaultdict(set), set()
for c in st["charts"]:
    for s in c["samples"]:
        smp[s["pattern"]].add(c["symbol"])
    for f in c.get("feedback", []):
        fb[f["pattern"]].add(c["symbol"])
    if c.get("boxes") and not c["samples"]:
        box_only.add(c["symbol"])
print("charts:", len(st["charts"]), "| patterns:", [p["name"] for p in st["patterns"]])
for p in sorted(set(smp) | set(fb), key=str):
    print(p, "| sample symbols:", len(smp[p]), "| feedback symbols:", len(fb[p]), sorted(fb[p])[:8])
print("charts with boxes but no samples:", len(box_only))
try:
    for m in read_mappings():
        print("mapping:", m.get("app"), m.get("pattern"), m.get("problem"))
except TypeError as e:
    print("read_mappings signature:", e)
