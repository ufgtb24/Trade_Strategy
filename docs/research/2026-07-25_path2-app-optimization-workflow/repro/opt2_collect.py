"""临时实验(opt · 第二轮):一次收集,同时服务三个问题。

  (a) 首次穿越(first-passage):±X% 谁先被触及 —— 判定 pattern 有无方向性优势
      (MFE/MAE 是幅度统计量、丢掉顺序;这一项把顺序补回来)
  (b) 市场超额 label:label_excess = label_stock − 同日横截面 index —— 看 σ 能降多少
  (c) 常规 label 对照:mh20 / cc20 / mae20

配置只要两个(pk4 现任 + bo_only 基线),外加「全宇宙随机日」无条件基准。
两年各跑一次。用完删。
"""
from __future__ import annotations

import pathlib
import sys
import time
from concurrent.futures import ProcessPoolExecutor

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from path2.dag.nodes import NodeSpec  # noqa: E402
from path2.dag.edges import TemporalEdge, Child  # noqa: E402
from path2.dag.spec import PatternSpec  # noqa: E402
from path2.dag import where as W  # noqa: E402
from path2.dag.engine import run_streams  # noqa: E402
from path2.dag._solve import compile_plan, solve  # noqa: E402
from path2.dag._reify import reify  # noqa: E402
from path2.atoms.breakout import BODetector, BurstDetector  # noqa: E402
from path2.atoms.throwback import ThrowbackDetector  # noqa: E402
from path2_apps.bottom_breakout_burst import load_params  # noqa: E402
from path2_web.data import slice_window  # noqa: E402

YEAR = int(sys.argv[1]) if len(sys.argv) > 1 else 2025
START, END = f"{YEAR}-01-01", f"{YEAR+1}-01-01"
H, HEAD_BUF, RATIO = 20, 63, 1.65
THRESH = (0.05, 0.08, 0.10, 0.15)
N_INDEX = 1500          # 造横截面 index 的抽样票数
SEED = 777
OUT = REPO / "temp_code" / "out2"
P0 = load_params()


def _spec(keep):
    b = P0.burst
    nodes = [NodeSpec("bo", BODetector(**P0.bo_kwargs()), render_grid="price")]
    if "burst" in keep:
        nodes.append(NodeSpec("burst", BurstDetector(**P0.burst_kwargs()),
                              where=(("first_drought", W.attr("first_drought", ">=", b.first_drought_min)),
                                     ("distinct_pk", W.attr("distinct_pk", ">=", b.distinct_pk_min)),
                                     ("vol_spike", W.attr("max_bar_vol_ratio", ">=", b.vol_spike_min))),
                              consumes_stream="bo"))
    if "tb" in keep:
        nodes.append(NodeSpec("tb", ThrowbackDetector(**P0.throwback_kwargs()),
                              consumes_stream="bo"))
    edges = ()
    if "burst" in keep and "tb" in keep:
        edges = (TemporalEdge(Child("burst", "last_bo"), "tb", min_gap=1,
                              max_gap=P0.tb.max_start_gap, anchor_field="anchor_bo_id"),)
    return PatternSpec(pattern_id="x", nodes=tuple(nodes), edges=edges)


FULL = _spec(("bo", "burst", "tb"))
CFG = [("pk4", _spec(("bo", "burst", "tb")), "tb"),
       ("bo_only", _spec(("bo",)), "bo")]


def _labels(hi, lo, cl, t, n):
    """返回 (mh20, cc20, mae20, {X: 'up'|'down'|'both'|'none'})。"""
    if t + n >= len(cl):
        return None
    c0 = cl[t]
    seg_h, seg_l = hi[t + 1:t + n + 1], lo[t + 1:t + n + 1]
    fp = {}
    for X in THRESH:
        up = np.nonzero(seg_h >= c0 * (1 + X))[0]
        dn = np.nonzero(seg_l <= c0 * (1 - X))[0]
        iu = up[0] if len(up) else 10**9
        idn = dn[0] if len(dn) else 10**9
        fp[X] = ("none" if iu == idn == 10**9 else
                 "both" if iu == idn else ("up" if iu < idn else "down"))
    return (float(seg_h.max() / c0 - 1.0), float(cl[t + n] / c0 - 1.0),
            float(seg_l.min() / c0 - 1.0), fp)


def _one(args):
    pkl, want_index, want_rand = args
    ticker = pathlib.Path(pkl).stem
    try:
        df = pd.read_pickle(pkl)
        s_ts, e_ts = pd.to_datetime(START), pd.to_datetime(END)
        win = slice_window(df, s_ts - pd.Timedelta(days=round(HEAD_BUF * RATIO)),
                           e_ts + pd.Timedelta(days=round(H * RATIO)))
        if win is None or len(win) < 80:
            return [], []
        hi, lo, cl = win["high"].values, win["low"].values, win["close"].values
        dts = win["date"].values
        in_win = [i for i in range(len(win))
                  if s_ts <= pd.Timestamp(dts[i]) <= e_ts]

        # --- 横截面 index:抽样票的每一天 ---
        idx_rows = []
        if want_index:
            for t in in_win:
                r = _labels(hi, lo, cl, t, H)
                if r:
                    idx_rows.append((dts[t], r[0], r[1]))

        rows = []
        streams = run_streams(FULL, win, P0)
        for tag, sp, end in CFG:
            plan = compile_plan(sp)
            st = {n.node_id: streams[n.node_id] for n in sp.nodes}
            iso = ({n.node_id for n in sp.nodes}
                   - {ep for e in sp.edges for ep in (e.src, e.dst)}) & \
                  {n.consumes_stream for n in sp.nodes if n.consumes_stream}
            seen = set()
            for s in solve(plan, st):
                m = reify(s, st, plan)
                if iso and set((m.node_index or {}).keys()).issubset(iso):
                    continue
                ev = (m.node_index or {}).get(end)
                if ev is None or ev.event_id in seen:
                    continue
                if not (s_ts <= pd.Timestamp(dts[ev.start_idx]) <= e_ts):
                    continue
                seen.add(ev.event_id)
                r = _labels(hi, lo, cl, ev.start_idx, H)
                if r:
                    rows.append((tag, ticker, dts[ev.start_idx], r[0], r[1], r[2],
                                 *[r[3][X] for X in THRESH]))
        if want_rand:
            rng = np.random.default_rng(abs(hash(ticker)) % (2**32) ^ SEED)
            for t in rng.choice(in_win, min(3, len(in_win)), replace=False):
                r = _labels(hi, lo, cl, int(t), H)
                if r:
                    rows.append(("RAND", ticker, dts[t], r[0], r[1], r[2],
                                 *[r[3][X] for X in THRESH]))
        return rows, idx_rows
    except Exception:
        return [], []


def main():
    pkls = sorted((REPO / "datasets" / "pkls").glob("*.pkl"))
    rng = np.random.default_rng(SEED)
    pick = set(rng.choice(len(pkls), min(N_INDEX, len(pkls)), replace=False).tolist())
    tasks = [(str(p), i in pick, i in pick) for i, p in enumerate(pkls)]
    print(f"{YEAR}: tickers={len(pkls)} index_sample={len(pick)}", flush=True)
    t0 = time.perf_counter()
    rows, idx = [], []
    with ProcessPoolExecutor(max_workers=26) as ex:
        for i, (r, ir) in enumerate(ex.map(_one, tasks, chunksize=20)):
            rows.extend(r)
            idx.extend(ir)
            if (i + 1) % 2000 == 0:
                print(f"  {i+1}/{len(pkls)} {time.perf_counter()-t0:.0f}s", flush=True)
    cols = ["cfg", "ticker", "date", "mh20", "cc20", "mae20"] + [f"fp{X:g}" for X in THRESH]
    D = pd.DataFrame(rows, columns=cols)
    I = pd.DataFrame(idx, columns=["date", "mh20", "cc20"])
    OUT.mkdir(parents=True, exist_ok=True)
    D.to_pickle(OUT / f"rows_{YEAR}.pkl")
    I.groupby("date").agg(mh_med=("mh20", "median"), cc_med=("cc20", "median"),
                          k=("mh20", "size")).to_pickle(OUT / f"index_{YEAR}.pkl")
    print(f"elapsed={time.perf_counter()-t0:.0f}s rows={len(D)} idx_days={I.date.nunique()}")
    print(D.groupby("cfg").agg(n=("mh20", "size"), mh=("mh20", "median"),
                               cc=("cc20", "median")).round(4).to_string())


if __name__ == "__main__":
    main()
