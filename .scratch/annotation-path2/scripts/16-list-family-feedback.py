"""票 16：列出全部整族反馈（只读，经 read_annotations）。"""
import sys
from path2_web.config import load_config
from path2_web.annotation.store import read_annotations

cfg = load_config()
st = read_annotations(cfg)["state"]
n_all = 0
for ch in st["charts"]:
    for fb in ch.get("feedback", []) or []:
        n_all += 1
        if fb.get("target") == "family":
            print(ch["symbol"], fb["id"], fb["pattern"], fb["app_id"], fb["app_ver"], fb["start"], fb["end"], fb.get("family_start"), fb.get("source"), (fb.get("note") or "")[:30])
print("feedback total", n_all)
