"""临时(flow_critic):经 read_annotations 读标注,数 new_step 正样本里各特征(成员框的特征,含子框)出现在几个正样本里,
算出再加几个「没有成员框的正样本」就会让它跌到「不到一半」。只读,不写标注。不入库。"""
from collections import Counter
from path2_web.config import load_config
from path2_web.annotation.store import read_annotations

st = read_annotations(load_config())["state"]
names = {f["id"]: f["name"] for f in st["features"]}
pos, cnt, empty = 0, Counter(), 0
for ch in st["charts"]:
    boxes = {b["id"]: b for b in ch["boxes"]}
    for s in ch["samples"]:
        if s["pattern"] != "new_step" or s["judgment"] != "pos":
            continue
        pos += 1
        feats = {boxes[m]["feature"] for m in s["members"] if m in boxes}
        empty += not feats
        cnt.update(feats)
print("positive samples:", pos, " with empty members:", empty)
for f, k in cnt.most_common():
    need = max(0, 2 * k - pos + 1)   # 加 x 个空样本后 k < (pos+x)/2 的最小 x
    print(f"{names.get(f, f)}: {k}/{pos}  -> {need} 个空成员正样本后跌到不到一半")
