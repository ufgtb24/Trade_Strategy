"""临时(impl_check):核 flow_critic F4——family 的核对范围从「首个 ▼～末个 ▼」延到「同起点那一行最后一个实例那天」后,
范围里会不会混进别的族(别的起点)的买点;以及前端点族时能不能只靠已有的 events 取到这个日期(同 node、同 start_idx
的 event 的最大 end_idx)。不入库。"""
from collections import defaultdict
from path2_web.config import load_config, view_dataset_dir
from path2_web.annotation.store import read_annotations
from path2_web.data import read_bars, slice_window, TRAIN_END
from path2_apps.new_step import dag_spec as mod

cfg = load_config()
syms = [c["symbol"] for c in read_annotations(cfg)["state"]["charts"]]
p = mod.load_params()
n_fam = n_contam = 0
for sym in syms:
    win = slice_window(read_bars(view_dataset_dir(cfg), sym), "1900-01-01", TRAIN_END)
    D = [str(x)[:10] for x in win["date"]]
    res = mod.analyze(win, p)
    buys = defaultdict(set)
    for h in res.hits:
        buys[h.start_idx].add(h.node_index["plateau"].child("today").start_idx)
    # 同 node(plateau)、同起点的全部实例(不论过没过 where)的最大终点 = 这一行最后一个实例那天
    last_inst = defaultdict(int)
    for e in res.events:
        if getattr(e, "node_id", None) == "plateau":
            last_inst[e.start_idx] = max(last_inst[e.start_idx], e.end_idx)
    for s, days in sorted(buys.items()):
        lo, hi_buy, hi_ext = min(days), max(days), last_inst.get(s)
        others = sorted(d for s2, ds in buys.items() if s2 != s for d in ds if lo <= d <= hi_ext)
        n_fam += 1
        n_contam += bool(others)
        print(f"{sym:5s} fam {D[s]} buys {D[lo]}..{D[hi_buy]} ext to {D[hi_ext] if hi_ext is not None else None}"
              + (f"  OTHER-family buys inside ext: {[D[d] for d in others]}" if others else ""))
print(f"families {n_fam}, contaminated after extension: {n_contam}")
