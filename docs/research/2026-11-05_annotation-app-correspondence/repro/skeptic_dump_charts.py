"""skeptic 临时脚本:列出每张图的框(特征、起止、属性、父框)和样本(日期、判断、成员、note)。"""
import json
from path2_web.config import load_config
from path2_web.annotation.store import read_annotations

cfg = load_config()
st = read_annotations(cfg)["state"]
fname = {f["id"]: f["name"] for f in st["features"]}
ch = st["charts"]
print(type(ch))
items = ch.items() if isinstance(ch, dict) else enumerate(ch)
for key, c in items:
    print("=== chart", key, {k: v for k, v in c.items() if k not in ("boxes", "samples")} if isinstance(c, dict) else "")
    for b in c.get("boxes", []):
        bb = dict(b)
        bb["feature"] = fname.get(bb.get("feature"), bb.get("feature"))
        if "attrs" in bb:
            bb["attrs"] = {fname.get(k, k): v for k, v in bb["attrs"].items()}
        print("  box", json.dumps(bb, ensure_ascii=False))
    for s in c.get("samples", []):
        print("  sample", json.dumps(s, ensure_ascii=False))
