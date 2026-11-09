"""临时(impl_check):new_step 第二版在 6 只有标注的股票上,hits 行按起点折出的各族,
① 同一天被几个族同时买的天数;② 每族 [首个买点, 末个买点] 里混进别的族买点的情况(family 反馈的状态会被别的族「染红」)。不入库。"""
from collections import defaultdict
from path2_web.config import load_config, view_dataset_dir
from path2_web.annotation.store import read_annotations
from path2_web.data import read_bars, slice_window, TRAIN_END
from path2_apps.new_step import dag_spec as mod

cfg = load_config()
syms = [c["symbol"] for c in read_annotations(cfg)["state"]["charts"]]
p = mod.load_params()
tot_fam = tot_contam = tot_multi_days = 0
for sym in syms:
    win = slice_window(read_bars(view_dataset_dir(cfg), sym), "1900-01-01", TRAIN_END)
    D = [str(x)[:10] for x in win["date"]]
    res = mod.analyze(win, p)
    fams = defaultdict(set)    # hit.start_idx -> buy days
    hit_n = defaultdict(int)
    for h in res.hits:
        pl = h.node_index["plateau"]
        today = pl.child("today")
        fams[h.start_idx].add(today.start_idx)
        hit_n[h.start_idx] += 1
    day_fams = defaultdict(set)
    for s, days in fams.items():
        for d in days:
            day_fams[d].add(s)
    multi = sorted(d for d, f in day_fams.items() if len(f) > 1)
    tot_multi_days += len(multi)
    print(f"== {sym}: families={len(fams)} hits={len(res.hits)} days bought by >1 family: {[D[d] for d in multi]}")
    for s, days in sorted(fams.items()):
        lo, hi = min(days), max(days)
        others = sorted(d for s2, ds in fams.items() if s2 != s for d in ds if lo <= d <= hi)
        tot_fam += 1
        if others:
            tot_contam += 1
        print(f"   fam start {D[s]} hits={hit_n[s]:3d} buys={len(days):3d} range {D[lo]}..{D[hi]}"
              + (f"  other-family buys inside: {[D[d] for d in others]}" if others else ""))
print(f"total families {tot_fam}, families whose range contains another family's buy: {tot_contam}, multi-family days {tot_multi_days}")
