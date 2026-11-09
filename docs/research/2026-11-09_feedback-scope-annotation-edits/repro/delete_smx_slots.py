"""实验：删掉 SMX 2025-11-24 那个样本后，原来只服务它的框会怎样提示？

只在内存里把样本拿掉（不写标注），用参照实现 empty_slots 算 SMX 2025-12-02 那个样本成员链上的空槽，比较删前删后。
运行：uv run python docs/research/2026-11-09_feedback-scope-annotation-edits/repro/delete_smx_slots.py
"""
import copy

from path2_web.config import load_config, view_dataset_dir
from path2_web.data import read_bars
from path2_web.annotation.store import read_annotations
from path2_web.annotation.membership import empty_slots

cfg = load_config()
state = read_annotations(cfg)["state"]
days = [d.strftime("%Y-%m-%d") for d in read_bars(view_dataset_dir(cfg), "SMX").index]
chart = next(c for c in state["charts"] if c["symbol"] == "SMX")
target = next(s for s in chart["samples"] if s["date"] == "2025-11-24")
keep = next(s for s in chart["samples"] if s["date"] == "2025-12-02")
print("删前", keep["id"], empty_slots(state["charts"], "SMX", keep["id"], days))
after = copy.deepcopy(state["charts"])
c2 = next(c for c in after if c["symbol"] == "SMX")
c2["samples"] = [s for s in c2["samples"] if s["id"] != target["id"]]
print("删后", keep["id"], empty_slots(after, "SMX", keep["id"], days))
