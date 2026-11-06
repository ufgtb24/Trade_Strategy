"""逐张图:用户框/样本 + new_step app 的 burst / tb / 企稳段 / hit / 买入日。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import load_state, load_win, d2i, i2d, EXCLUDED_SAMPLES  # noqa: E402

import path2_apps.new_step as app  # noqa: E402
from path2.eval import _resolve_end_events  # noqa: E402

s, fname = load_state()
p = app.load_params()
meta = app.eval_meta(p)

for c in s["charts"]:
    sym = c["symbol"]
    win = load_win(sym)
    print(f"\n===== {sym}  bars={len(win)} {i2d(win,0)}..{i2d(win,len(win)-1)}")
    lo = min(d2i(win, b["start"]) for b in c["boxes"]) - 60
    hi = max(d2i(win, x["date"]) for x in c["samples"]) + 40
    for b in c["boxes"]:
        print(f"  BOX {b['id']} {fname.get(b['feature'])} {b['start']}..{b['end']} "
              f"[{d2i(win,b['start'])}..{d2i(win,b['end'])}] attrs={ {fname[k]: v for k, v in (b.get('attrs') or {}).items()} }")
    for x in c["samples"]:
        ex = " (EXCLUDED)" if (sym, x["date"]) in EXCLUDED_SAMPLES else ""
        print(f"  SMP {x['id']} {x['date']} [{d2i(win,x['date'])}] members={x['members']}{ex}")
    res = app.analyze(win, p)
    by = {}
    for e in res.events:
        by.setdefault(e.node_id, []).append(e)
    for nid in ("bo", "burst", "tb"):
        for e in by.get(nid, []):
            if e.end_idx < lo or e.start_idx > hi:
                continue
            extra = ""
            if nid == "bo":
                extra = f"vr={e.vol_ratio} pk={e.pk_count} c={win['close'].iloc[e.end_idx]:.3f}"
            if nid == "burst":
                extra = f"count={e.count} dpk={e.distinct_pk} mvr={e.max_bar_vol_ratio:.1f}"
            if nid == "tb":
                extra = "segs=" + ", ".join(f"{i2d(win,g.start_idx)}..{i2d(win,g.end_idx)}({g.outcome})" for g in e.segments) + f" mo={e.machine_outcome} anchor={e.anchor_bo_id}"
            print(f"  {nid:5s} {e.instance_id:28s} {i2d(win,e.start_idx)}..{i2d(win,e.end_idx)} {extra}")
    for h in res.hits:
        if h.end_idx < lo or h.start_idx > hi:
            continue
        ends = _resolve_end_events(h, meta["end_node"])
        days = sorted({i for e in ends for i in range(e.start_idx, e.end_idx + 1)})
        print(f"  HIT {h.hit_id} {i2d(win,h.start_idx)}..{i2d(win,h.end_idx)} burst={h.node_index['burst'].instance_id} tb={h.node_index['tb'].instance_id}")
        print("     buy days:", ", ".join(i2d(win, i) for i in days))
