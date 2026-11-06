"""临时:打印 new_step 相关的标注(词表、pattern、各图的框与样本)。只读。"""
from path2_web.config import load_config
from path2_web.annotation.store import read_annotations

st = read_annotations(load_config())["state"]
feats = {f["id"]: f for f in st["features"]}
print("== features")
for f in st["features"]:
    print(f["id"], f["name"], "|", f.get("definition"))
print("== patterns")
for p in st["patterns"]:
    print(p)
print("== charts")
for c in st["charts"]:
    if not c["samples"] and not c["boxes"]:
        continue
    print("##", c["symbol"])
    for b in sorted(c["boxes"], key=lambda b: b["start"]):
        attrs = {feats.get(k, {}).get("name", k): v for k, v in (b.get("attrs") or {}).items()}
        print("  box", b["id"], feats.get(b["feature"], {}).get("name"), b["start"], b["end"], attrs,
              "note=" + str(b.get("note")) if b.get("note") else "", "detach" if b.get("detach") else "", "attach=" + str(b.get("attach")) if b.get("attach") else "")
    for s in sorted(c["samples"], key=lambda s: s["date"]):
        print("  sample", s["id"], s["date"], s["pattern"], s["judgment"], s["members"], "note=" + str(s.get("note")) if s.get("note") else "")
