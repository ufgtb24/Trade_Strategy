"""critic 一次性复核 tracer 的「新平台最高价比阶跃顶高 10% 以上」与 keep_ratio>1、前缀成族的数字（旧版 app）。
同一天同一段阶跃（同起点）只留最长前缀；按买点日分正样本(±3)/反馈范围/其余。"""
import sys
from collections import defaultdict
import numpy as np
sys.path.insert(0, "docs/research/2026-11-16_annotation-round-reflection/repro")
import critic_seg_trigger as T
from critic_pkg.new_step_old import dag_spec as old
from path2_web.app_run import load_bars
from path2_web.config import load_config
from path2_web.data import TRAIN_END, slice_window

cfg = load_config(); params = old.load_params(); spec = old.build_pattern(params)
node = next(n for n in spec.nodes if n.node_id == "plateau"); det = node.detector
agg = defaultdict(lambda: [0, 0, 0]); days_multi = 0; days_total = 0; detail = []
for sym in T.SYMS:
    df = slice_window(load_bars(cfg, sym), "1900-01-01", TRAIN_END)
    day = [str(d)[:10] for d in df["date"]]
    hi = df["high"].to_numpy(float)
    pos_idx = [day.index(d) for d in T.POS.get(sym, []) if d in day]
    spots = [(day.index(a), day.index(b)) for a, b in T.SPOTS.get(sym, [])]
    best = {}; per_day = defaultdict(list)
    for ev in det.detect(df):
        if not all(fn(ev) for _, fn in node.where):
            continue
        t = ev.today.start_idx; s = ev.step.start_idx
        per_day[t].append(s)
        k = (t, s)
        if k not in best or ev.step.end_idx > best[k].step.end_idx:
            best[k] = ev
    for t, ss in per_day.items():
        days_total += 1
        if len(ss) > len(set(ss)):
            days_multi += 1
    for (t, s), ev in best.items():
        e = ev.step.end_idx; n0, n1 = ev.new.start_idx, ev.new.end_idx
        h10 = hi[n0:n1 + 1].max() >= 1.1 * hi[s:e + 1].max()
        kr = ev.keep_ratio > 1
        grp = "pos" if any(abs(t - p) <= 3 for p in pos_idx) else ("spot" if any(a <= t <= b for a, b in spots) else "other")
        a = agg[grp]; a[0] += 1; a[1] += h10; a[2] += kr
        if grp != "other" and h10:
            detail.append((grp, sym, day[t], day[s], day[e]))
print("组: [hit(最长前缀), 新平台高过阶跃顶10%, keep_ratio>1]")
for g in ("pos", "spot", "other"):
    print(g, agg[g])
print("合计 hit", sum(v[0] for v in agg.values()), "高10%", sum(v[1] for v in agg.values()), "keep>1", sum(v[2] for v in agg.values()))
print("买点日", days_total, "其中同一段阶跃≥2前缀同天买", days_multi)
for d in detail:
    print(*d)
