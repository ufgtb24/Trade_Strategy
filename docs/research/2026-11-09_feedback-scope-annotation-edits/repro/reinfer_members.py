"""实验：如果为「另建新 pattern」在同一天重放样本，新样本按默认推断收的成员框，和旧样本现在存的成员框一样吗？

只经 read_annotations 读标注、只经 read_bars 读训练段副本；不写任何东西。
运行：uv run python docs/research/2026-11-09_feedback-scope-annotation-edits/repro/reinfer_members.py
"""
from path2_web.config import load_config, view_dataset_dir
from path2_web.data import read_bars
from path2_web.annotation.store import read_annotations
from path2_web.annotation.membership import sample_members

cfg = load_config()
state = read_annotations(cfg)["state"]
same = diff = 0
for ch in state["charts"]:
    days = [d.strftime("%Y-%m-%d") for d in read_bars(view_dataset_dir(cfg), ch["symbol"]).index]
    for s in ch["samples"]:
        fresh = sample_members(s["date"], ch["boxes"], days)
        ok = set(fresh) == set(s["members"])
        same += ok
        diff += not ok
        print(ch["symbol"], s["date"], "edited" if s.get("members_edited") else "auto  ",
              "same" if ok else f"DIFF stored={s['members']} reinfer={fresh}")
print(f"same={same} diff={diff}")
