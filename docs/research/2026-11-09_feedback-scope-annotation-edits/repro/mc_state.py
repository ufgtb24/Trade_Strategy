"""method_critic: 读当前标注状态，列 new_step 的定义、特征、样本与成员框（只读，经 read_annotations）。"""
import json
from path2_web.config import load_config
from path2_web.annotation.store import read_annotations

r = read_annotations(load_config())
st = r["state"]
feat = {f["id"]: f for f in st["features"]}
print("features:")
for f in st["features"]:
    print("  ", f["id"], f["name"], "|", f.get("definition"))
print("patterns:")
for p in st["patterns"]:
    print("  ", p)
for ch in st["charts"]:
    boxes = {b["id"]: b for b in ch["boxes"]}
    if not ch["samples"] and not ch["boxes"]:
        continue
    print("==", ch["symbol"], "boxes", len(ch["boxes"]), "samples", len(ch["samples"]))
    for b in ch["boxes"]:
        an = {feat.get(k, {}).get("name", k): v for k, v in (b.get("attrs") or {}).items()}
        print("   box", b["id"], feat.get(b["feature"], {}).get("name"), b["start"], b["end"], an, b.get("note") or "")
    for s in ch["samples"]:
        print("   smp", s["id"], s["date"], s["pattern"], s["judgment"], s["members"], s.get("note") or "")
print("conflicts", len(r["conflicts"]), "violations", len(r["violations"]))

# 每个对象最后一次修改的时间（revs 里的引用 = 文件名#序号，文件名里带 UTC 时间戳；含已删对象）
print("\nlast-modified per object (UTC):")
live = set()
for ch in st["charts"]:
    live |= {b["id"] for b in ch["boxes"]} | {s["id"] for s in ch["samples"]}
live |= {f["id"] for f in st["features"]}
for kind in ("sample", "box", "feature", "pattern"):
    for oid, ref in sorted(r["revs"][kind].items(), key=lambda kv: kv[1]):
        ts = ref.split("-")[1]
        print(f"  {kind:7s} {oid:10s} {ts} {'live' if (oid in live or kind=='pattern') else 'DELETED'}")
