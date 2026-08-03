"""补测 · 滞后波动率 —— 回答 feedback.md 疑问 1:波动率是混杂还是中介。

主口径 `rv63` 的测量窗口 = 买点前 63 个交易日,**包含突破那一段**。
若命中集的高波动是突破本身造成的(中介),把测量窗口整体前移之后偏斜应当消失;
若这些股票在突破之前就已经比全宇宙躁动(混杂),偏斜应当保持。

本脚本一次跑完:
  ① 每个 L ∈ LAGS 的波动率倍数 = median(rv63_lagL | 命中集) / median(同日全宇宙)
  ② 命中集的 pattern 跨度分布 —— 决定哪些 L 才算"完全排除突破段"的有效档
     (L 必须 > 跨度 p95,否则滞后窗口仍覆盖突破的一部分,检验自带污染且不报错)
  ③ 已知答案自检:L=0 必须复现 final_report A.1 的 2.46x

用完不删:这是该结论的可执行形式(同 repro/opt2_*.py)。
"""
from __future__ import annotations

import os
import pathlib
import sys
import time
from concurrent.futures import ProcessPoolExecutor

REPO = pathlib.Path(__file__).resolve().parents[4]
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

RV_WIN = 63
LAGS = (0, 40, 80, 120, 160, 200)
UNIV_SAMPLE = 12          # 每只股票在窗口内抽多少天进全宇宙面板(逐日中位数用)
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


def _rv_table(cl):
    """rv63[i] = [i-62, i] 段 log 收益率的标准差(只用 ≤i 的数据)。

    返回 shape=(len(cl), len(LAGS)) 的矩阵,第 j 列 = rv63 前移 LAGS[j] 个 bar。
    不足历史的位置为 nan。
    """
    lr = np.full(len(cl), np.nan)
    lr[1:] = np.log(cl[1:] / cl[:-1])
    rv = pd.Series(lr).rolling(RV_WIN).std().values
    out = np.full((len(cl), len(LAGS)), np.nan)
    for j, L in enumerate(LAGS):
        if L == 0:
            out[:, j] = rv
        else:
            out[L:, j] = rv[:-L]
    return out


def _one(args):
    pkl, start, end, head_days, tail_days, want_univ = args
    ticker = pathlib.Path(pkl).stem
    try:
        df = pd.read_pickle(pkl)
        s_ts, e_ts = pd.to_datetime(start), pd.to_datetime(end)
        win = slice_window(df, s_ts - pd.Timedelta(days=head_days),
                           e_ts + pd.Timedelta(days=tail_days))
        if win is None or len(win) < RV_WIN + max(LAGS) + 20:
            return [], []
        cl = win["close"].values.astype(float)
        if not np.all(np.isfinite(cl)) or np.any(cl <= 0):
            return [], []
        dts = win["date"].values
        rv = _rv_table(cl)
        in_win = [i for i in range(len(win)) if s_ts <= pd.Timestamp(dts[i]) <= e_ts]
        if not in_win:
            return [], []

        hits = []
        streams = run_streams(FULL, win, P0)
        for tag, sp, end_role in CFG:
            plan = compile_plan(sp)
            st = {n.node_id: streams[n.node_id] for n in sp.nodes}
            iso = ({n.node_id for n in sp.nodes}
                   - {ep for e in sp.edges for ep in (e.src, e.dst)}) & \
                  {n.consumes_stream for n in sp.nodes if n.consumes_stream}
            seen = set()
            for s in solve(plan, st):
                m = reify(s, st, plan)
                ni = m.node_index or {}
                if iso and set(ni.keys()).issubset(iso):
                    continue
                ev = ni.get(end_role)
                if ev is None or ev.event_id in seen:
                    continue
                t = ev.start_idx
                if not (s_ts <= pd.Timestamp(dts[t]) <= e_ts):
                    continue
                seen.add(ev.event_id)
                # pattern 完整跨度 = 买点 − 本次匹配里最早事件的起点
                first = min(e.start_idx for e in ni.values())
                hits.append((tag, ticker, dts[t], int(t - first), *rv[t].tolist()))

        univ = []
        if want_univ:
            rng = np.random.default_rng(abs(hash(ticker)) % (2**32))
            for t in rng.choice(in_win, min(UNIV_SAMPLE, len(in_win)), replace=False):
                univ.append((dts[int(t)], *rv[int(t)].tolist()))
        return hits, univ
    except Exception:
        return [], []


def main():
    # ---- 参数 ----
    years = [2025, 2024]
    data_dir = REPO / "datasets" / "pkls"
    out_dir = REPO / "docs" / "research" / "2026-07-25_path2-app-optimization-workflow" / "lag_vol_out"
    workers = min(26, (os.cpu_count() or 8))
    known_answer = 2.46            # final_report A.1 的主口径倍数,用作实现自检
    # --------------

    rv_cols = [f"rv_L{L}" for L in LAGS]
    head_days = round((RV_WIN + max(LAGS) + 15) * 1.65)
    tail_days = round(20 * 1.65)
    pkls = sorted(data_dir.glob("*.pkl"))
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"tickers={len(pkls)} workers={workers} head_days={head_days} lags={LAGS}\n")

    for year in years:
        start, end = f"{year}-01-01", f"{year+1}-01-01"
        tasks = [(str(p), start, end, head_days, tail_days, True) for p in pkls]
        t0 = time.perf_counter()
        hits, univ = [], []
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for h, u in ex.map(_one, tasks, chunksize=20):
                hits.extend(h)
                univ.extend(u)
        H = pd.DataFrame(hits, columns=["cfg", "ticker", "date", "span"] + rv_cols)
        U = pd.DataFrame(univ, columns=["date"] + rv_cols)
        H.to_pickle(out_dir / f"hits_{year}.pkl")
        U.to_pickle(out_dir / f"univ_{year}.pkl")
        print(f"=== {year} ===  {time.perf_counter()-t0:.0f}s  "
              f"hits={len(H)} univ_rows={len(U)}")

        # ---- pattern 跨度分布:决定哪些 L 是有效档 ----
        print("\n[跨度] 买点 − 本次匹配最早事件起点(交易日)")
        for tag, g in H.groupby("cfg"):
            q = g["span"].quantile([.5, .9, .95, .99]).round(1).tolist()
            print(f"  {tag:8s} n={len(g):6d}  p50={q[0]:6.1f} p90={q[1]:6.1f} "
                  f"p95={q[2]:6.1f} p99={q[3]:6.1f} max={g['span'].max():.0f}")

        # ---- 波动率倍数:逐日除以同日全宇宙中位数 ----
        med = U.groupby("date")[rv_cols].median()
        print(f"\n[倍数] median_over_hits( rv / 同日全宇宙中位 )   基准日数={len(med)}")
        print(f"  {'cfg':8s} " + " ".join(f"L={L:<3d}" for L in LAGS))
        rows = {}
        for tag, g in H.groupby("cfg"):
            j = g.join(med, on="date", rsuffix="_m")
            vals = []
            for c in rv_cols:
                r = (j[c] / j[f"{c}_m"]).replace([np.inf, -np.inf], np.nan).dropna()
                vals.append(float(r.median()) if len(r) else float("nan"))
            rows[tag] = vals
            print(f"  {tag:8s} " + " ".join(f"{v:5.2f}" for v in vals))

        if "pk4" in rows and LAGS[0] == 0:
            got = rows["pk4"][0]
            print(f"\n[自检] pk4 L=0 = {got:.2f}   已知答案 = {known_answer}   "
                  f"{'✅ 口径一致' if abs(got - known_answer) < 0.25 else '❌ 口径不一致,下面的数不可信'}")
        print()


if __name__ == "__main__":
    main()
