"""skeptic 临时脚本:只读打印当前标注(特征、框、样本),经 read_annotations。"""
import json
from path2_web.config import load_config
from path2_web.annotation.store import read_annotations

cfg = load_config()
r = read_annotations(cfg)
st = r["state"]
print("keys:", list(st.keys()))
for k, v in st.items():
    if isinstance(v, dict):
        print(k, len(v))
    elif isinstance(v, list):
        print(k, len(v))
print(json.dumps({k: st[k] for k in st if k in ("features", "patterns")}, ensure_ascii=False, indent=1)[:6000])
