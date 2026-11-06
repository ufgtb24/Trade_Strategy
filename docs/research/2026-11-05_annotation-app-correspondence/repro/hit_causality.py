"""临时:核对 new_step 每个 hit 里绑定的 event 是否都在最早买点日之前确认;并列出 hit 绑了哪些 node、
hit 跨度比最后一个买点日多出几根(bracket 终点≠买入日的量)。只读。"""
import pandas as pd
from path2_web.config import load_config, view_dataset_dir
from path2_web.data import read_bars, slice_window
from path2.eval import _resolve_end_events
from path2_apps.new_step import dag_spec as app

cfg = load_config()
p = app.load_params()
end_node = app.eval_meta(p)["end_node"]
for sym, lo, hi in [("CRNC", "2024-03-01", "2025-03-01"), ("GEVO", "2024-03-01", "2024-12-31"),
                    ("QBTS", "2024-06-01", "2025-02-01"), ("INDO", "2021-08-01", "2022-05-01")]:
    win = slice_window(read_bars(view_dataset_dir(cfg), sym), lo, hi)
    res = app.analyze(win, p)
    for h in res.hits:
        buys = sorted(t for ev in _resolve_end_events(h, end_node) for t in ev.sample_bar_indices())
        late = {nid: (e.confirm_idx, buys[0]) for nid, e in h.node_index.items() if e.confirm_idx > buys[0]}
        print(sym, "nodes", sorted(h.node_index), "buy days", len(buys),
              "hit 终点比最后买点多", h.end_idx - buys[-1], "根", "确认晚于首个买点:", late or "无")
