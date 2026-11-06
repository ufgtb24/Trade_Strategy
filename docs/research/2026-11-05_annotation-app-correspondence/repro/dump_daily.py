"""逐张图逐日表:K 线 + 量比 + 用户框/样本 + 各 detector 输出 + app 命中那台企稳状态机的逐根回放。
输出写到 repro/daily_<SYM>.txt。"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from common import load_state, load_win, d2i, i2d, EXCLUDED_SAMPLES  # noqa: E402
from tb_trace import run_trace  # noqa: E402

import path2_apps.new_step as app  # noqa: E402
from path2.atoms.platform import PlatformDetector  # noqa: E402
from path2.atoms.trend import TrendSegmentDetector  # noqa: E402
from path2.atoms.distribution import DistributionDetector  # noqa: E402
from path2.calc.volume import calculate_vol_ratio  # noqa: E402
from path2.calc.atr import calculate_tr_median  # noqa: E402

s, fname = load_state()
p = app.load_params()

for c in s["charts"]:
    sym = c["symbol"]
    win = load_win(sym)
    lo = max(0, min(d2i(win, b["start"]) for b in c["boxes"]) - 40)
    hi = min(len(win) - 1, max(d2i(win, x["date"]) for x in c["samples"]) + 25)
    vr = calculate_vol_ratio(win["volume"], 63)
    vol = calculate_tr_median(win["high"], win["low"], win["close"], 14)
    plats = list(PlatformDetector().detect(win))
    trends = list(TrendSegmentDetector().detect(win))
    dists = list(DistributionDetector().detect(win))
    res = app.analyze(win, p)
    bos = {e.end_idx: e for e in res.events if e.node_id == "bo"}
    # 命中里的 tb 容器 → 回放
    traces = {}
    for h in res.hits:
        tb = h.node_index["tb"]
        burst = h.node_index["burst"]
        bo_idx = burst.members[-1].end_idx
        if bo_idx in traces or bo_idx < lo - 60 or bo_idx > hi:
            continue
        gbot0 = float(win["close"].iloc[bo_idx - 1])
        rows, segs, outc = run_trace(win, bo_idx, gbot0, max_rise_k=p.tb.max_rise_k,
                                     K=p.tb.stop_confirm_bars, max_span=p.tb.max_span, vol_window=p.tb.vol_window)
        traces[bo_idx] = {r[0]: r for r in rows}
    out = []
    out.append(f"{sym}  boxes: " + "; ".join(f"{b['id']}={fname.get(b['feature'])} {b['start']}..{b['end']}" for b in c["boxes"]))
    out.append("platform(默认 window=10 range_thr=5%): " + "; ".join(f"{i2d(win,e.start_idx)}..{i2d(win,e.end_idx)} rng={e.range_pct:.3f}" for e in plats if e.end_idx >= lo and e.start_idx <= hi))
    out.append("trend(默认 ma20): " + "; ".join(f"{e.regime} {i2d(win,e.start_idx)}..{i2d(win,e.end_idx)} dd={e.drawdown:.2f}" for e in trends if e.end_idx >= lo and e.start_idx <= hi))
    out.append("dist: " + "; ".join(i2d(win, e.start_idx) for e in dists if lo <= e.start_idx <= hi))
    out.append(f"{'date':10s} {'open':>8s} {'high':>8s} {'low':>8s} {'close':>8s} {'chg%':>6s} {'vr':>6s} {'vol':>6s} boxes      smp  bo   trend     plat  | tb回放(按阶跃根)")
    for i in range(lo, hi + 1):
        d = i2d(win, i)
        o, h_, l_, cl = (float(win[k].iloc[i]) for k in ("open", "high", "low", "close"))
        chg = (cl / float(win["close"].iloc[i - 1]) - 1) * 100 if i > 0 else 0
        inb = "".join(("F" if fname.get(b["feature"]) == "站上新平台" else "D") if b["start"] <= d <= b["end"] else "." for b in c["boxes"])
        smp = ""
        for x in c["samples"]:
            if x["date"] == d:
                smp = "X" if (sym, d) in EXCLUDED_SAMPLES else "S"
        bo = ""
        if i in bos:
            bo = f"bo{bos[i].pk_count}"
        tr = next((e.regime for e in trends if e.start_idx <= i <= e.end_idx), "")
        pl = "P" if any(e.start_idx <= i <= e.end_idx for e in plats) else ""
        tbs = []
        for b0, rows in traces.items():
            if i in rows:
                r = rows[i]
                tbs.append(f"[{i2d(win,b0)[5:]}] {r[1][:2]}→{r[2][:2]}{' BUY' if r[8] else ''} sup={r[5]:.3f} tr={r[4]:.3f} {r[7]}")
        vv = vr.iloc[i]
        out.append(f"{d} {o:8.3f} {h_:8.3f} {l_:8.3f} {cl:8.3f} {chg:6.1f} {vv:6.1f} {vol.iloc[i]:6.3f} {inb:10s} {smp:4s} {bo:4s} {tr:9s} {pl:4s} | " + " || ".join(tbs))
    (HERE / f"daily_{sym}.txt").write_text("\n".join(out) + "\n")
    print(sym, "ok", len(out))
