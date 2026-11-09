"""临时(impl_check):new_step 第二版的买点日里,前后 1 根内还有别的买点日的比例——
point 反馈按 NEG_TOL=1 判冲突时,只砍掉被点的那一天、邻日照买,记号仍是朱红的情形有多常见。不入库。"""
from path2_web.config import load_config, view_dataset_dir
from path2_web.annotation.store import read_annotations
from path2_web.data import read_bars, slice_window, TRAIN_END
from path2_apps.new_step import dag_spec as mod

cfg = load_config()
syms = [c["symbol"] for c in read_annotations(cfg)["state"]["charts"]]
p = mod.load_params()
n = k = 0
for sym in syms:
    win = slice_window(read_bars(view_dataset_dir(cfg), sym), "1900-01-01", TRAIN_END)
    res = mod.analyze(win, p)
    days = sorted({h.node_index["plateau"].child("today").start_idx for h in res.hits})
    s = set(days)
    for d in days:
        n += 1
        if (d - 1) in s or (d + 1) in s:
            k += 1
print(f"buy days {n}, with another buy day within ±1 bar: {k} ({k/n:.0%})")
