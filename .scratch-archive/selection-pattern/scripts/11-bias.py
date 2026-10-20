"""11 同日对照配对票 · 第四步：只偏爱某种水平的假 pattern 在每种配对、每把尺子上白得多少领先。

假 pattern（见 11-prereg.txt 第四节），三种形式：
  full   整类股票日全算（期望白得领先的最准估计）；附整只股票重抽 100 次的抽样误差（只在现行 M5 下算）
  disp   分散长相：同股 40 个交易日内不重复买，每年 1000 个买点（按年配额），40 次平均
  clust  照 bottom_burst 买点长相的扎堆型（只这一类），40 次平均：每只来源股的每段连买，换成池内当天
         平时波动同档的股票（同一来源股尽量沿用同一只替身，替身当天不在池内才换），只用当天及以前的信息挑替身
范围：all（2021-11..2025-11 全部决策日）、各年、ex2022（去掉 2022 年）
输出：scripts/11-bias.csv.gz（逐项）、scratchpad/11/bias_reps.csv.gz（逐次）
运行：uv run python .scratch/selection-pattern/scripts/11-bias.py
"""
from __future__ import annotations

import importlib.util
import sys
import time
import zlib
from multiprocessing import get_context
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("core11", HERE / "11-core.py")
core = importlib.util.module_from_spec(spec); sys.modules["core11"] = core; spec.loader.exec_module(core)
sys.path.insert(0, str(core.ROOT))
from path2.calc.atr import rolling_atr_pct_nanmedian  # noqa: E402

G: dict = {}
SCOPES = ["all", "2021", "2022", "2023", "2024", "2025", "ex2022"]
N_REP, B_SE = 40, 100
JUDGED = ["M_top2", "M_top10", "M_bot10", "M_bot2", "H_top10", "H_bot10",
          "Hhi_Mmid", "Mhi_Hmid", "Hlo_Mmid", "Mlo_Hmid"]
CHECKS = ["DV_bot10", "DV_top10", "PX_bot10", "PX_top10"]


def classes(P):
    rM = core.day_rank(P, P["M"]); rH = core.day_rank(P, P["Mh"])
    rD = core.day_rank(P, P["dv"]); rX = core.day_rank(P, P["px"])
    mid = lambda r: (r > 0.3) & (r <= 0.7)
    C = {"rand": np.ones(P["N"], bool),
         "M_top2": rM > 0.98, "M_top10": rM > 0.9, "M_bot10": rM <= 0.1, "M_bot2": rM <= 0.02,
         "H_top10": rH > 0.9, "H_bot10": rH <= 0.1,
         "Hhi_Mmid": (rH > 0.9) & mid(rM), "Mhi_Hmid": (rM > 0.9) & mid(rH),
         "Hlo_Mmid": (rH <= 0.1) & mid(rM), "Mlo_Hmid": (rM <= 0.1) & mid(rH),
         "DV_bot10": rD <= 0.1, "DV_top10": rD > 0.9, "PX_bot10": rX <= 0.1, "PX_top10": rX > 0.9}
    for k in range(10):
        C[f"Mdec{k + 1}"] = (rM > k / 10) & (rM <= (k + 1) / 10)
        C[f"Hdec{k + 1}"] = (rH > k / 10) & (rH <= (k + 1) / 10)
    for k in C:
        C[k] &= np.isfinite(rM)
    return C


def scope_mask(P, rows, scope):
    y = P["year"][rows]
    if scope == "all":
        return np.ones(len(rows), bool)
    if scope == "ex2022":
        return y != 2022
    return y == int(scope)


def eval_rows(rows, w=None, schemes=None):
    P, mts, S = G["P"], G["mts"], G["S"]
    out = []
    for sc in SCOPES:
        m = scope_mask(P, rows, sc)
        if m.sum() < 2:
            continue
        r = rows[m]; ww = None if w is None else w[m]
        for s in (schemes or G.get("eval_schemes") or list(mts)):
            res = core.leads(mts[s], S, r, ww)
            out.append({"scope": sc, "scheme": s, "n": int(m.sum()),
                        "n_stocks": int(len(np.unique(P["sym"][r]))), **res})
    return out


def task_full(name):
    P = G["P"]
    rows = np.flatnonzero(G["C"][name])
    res = eval_rows(rows)
    hm = {}
    for sc in SCOPES:
        m = scope_mask(P, rows, sc)
        if m.sum() >= 2:
            hm[sc] = core.hold_mean(G["hold"], rows[m])
    for r in res:
        r.update({"cls": name, "form": "full"})
        for rr, v in hm.get(r["scope"], {}).items():
            r[f"hold_{rr}"] = v
    if name in JUDGED + CHECKS + ["rand"] and not G.get("eval_schemes"):   # 抽样误差：整只股票重抽，现行 M5
        rng = np.random.default_rng(zlib.crc32(name.encode()))
        se = {}
        for sc in SCOPES:
            m = scope_mask(P, rows, sc)
            if m.sum() < 2:
                continue
            r = rows[m]
            bs = []
            for _ in range(B_SE):
                w = core.stock_boot_weights(P, r, rng); k = w > 0
                bs.append(core.leads(G["mts"]["M5"], G["S"], r[k], w[k]))
            se[sc] = {f"se_{mm}": float(np.std([b[mm] for b in bs], ddof=1)) for mm in core.METRICS}
        for r in res:
            r.update(se.get(r["scope"], {}))
    return res


def disp_sample(name, rng):
    """按年配额（每年 1000 个、按决策日数折算）的分散长相抽样，跨年也守 40 日间隔。"""
    P = G["P"]
    cand = np.flatnonzero(G["C"][name])
    perm = cand[rng.permutation(len(cand))]
    yrs = P["year"][perm]
    quota = {y: int(round(1000 * G["ndays"][y] / 252)) for y in G["ndays"]}
    got = {y: 0 for y in quota}
    last: dict = {}
    keep = []
    sym, d = P["sym"], P["d"]
    for r, y in zip(perm, yrs):
        if got[y] >= quota[y]:
            continue
        s = int(sym[r]); t = int(d[r])
        lst = last.get(s)
        if lst is None or all(abs(t - x) >= 40 for x in lst):
            keep.append(r); got[y] += 1
            last.setdefault(s, []).append(t)
            if all(got[k] >= quota[k] for k in quota):
                break
    return np.sort(np.array(keep, np.int64))


def task_disp(args):
    name, rep = args
    rng = np.random.default_rng(10_000 * (zlib.crc32(name.encode()) % 10_000) + rep)
    rows = disp_sample(name, rng)
    res = eval_rows(rows)
    for r in res:
        r.update({"cls": name, "form": "disp", "rep": rep})
    return res


def clust_rows(rng):
    P = G["P"]
    src_sym, src_d, src_dec, seg = G["bb"]
    rowidx = G["rowidx"]
    used = np.zeros(len(P["symbols"]), bool)
    target_of: dict = {}
    rows = []
    for g in rng.permutation(np.unique(seg)):
        idx = np.flatnonzero(seg == g)
        s0 = int(src_sym[idx[0]]); d0 = int(src_d[idx[0]]); dec = int(src_dec[idx[0]])
        t = target_of.get(s0)
        if t is None or rowidx[t, d0] < 0:
            cand = None
            for extra in (0, 1, 2, 3, 9):
                lo, hi = max(0, dec - extra), min(9, dec + extra)
                rr = G["day_rows_by_dec"](d0, lo, hi)
                rr = rr[~used[P["sym"][rr]]]
                if len(rr):
                    cand = rr
                    break
            if cand is None:
                continue
            t = int(P["sym"][rng.choice(cand)])
            used[t] = True
            target_of[s0] = t
        r = rowidx[t, src_d[idx]]
        rows.append(r[r >= 0])
    rows = np.unique(np.concatenate(rows)) if rows else np.array([], np.int64)
    return rows


def task_clust(rep):
    rng = np.random.default_rng(777_000 + rep)
    rows = clust_rows(rng)
    res = eval_rows(rows)
    for r in res:
        r.update({"cls": "bb_clust", "form": "clust", "rep": rep})
    return res


def prep_bb(P):
    """bottom_burst 买点位置 → (来源股, 决策日, 来源股当天平时波动在池内十档的档号, 连买段号)。"""
    b = pd.read_csv(core.SCR / "buys_bottom_burst.csv", keep_default_na=False, dtype={"symbol": str})
    b["date"] = pd.to_datetime(b["date"])
    cal = pd.DatetimeIndex(P["calendar"])
    b = b[b["date"].isin(cal)].copy()
    b["d"] = cal.get_indexer(b["date"])
    srcs = sorted(b["symbol"].unique())
    mh = {}
    for s in srcs:   # 来源股自己的平时波动（读截断副本；不在池内的日子也要）
        df = pd.read_pickle(core.ROOT / "datasets/pkls_until_20251231" / f"{s}.pkl").astype(float)
        df.index = pd.DatetimeIndex(df.index).normalize()
        M = rolling_atr_pct_nanmedian(df["high"], df["low"], df["close"], period=20)
        h = M.rolling(250, min_periods=120).median().fillna(M.rolling(250, min_periods=1).median())
        mh[s] = h.reindex(cal)
    b["mh"] = [mh[s].iat[d] for s, d in zip(b["symbol"], b["d"])]
    # 当天池内严格版平时波动的十分位切点
    Mh = P["Mh"]
    cuts = np.full((len(cal), 9), np.nan)
    for t in range(len(cal)):
        v = Mh[P["day_start"][t]:P["day_end"][t]]
        v = v[np.isfinite(v)]
        if len(v) >= 50:
            cuts[t] = np.quantile(v, np.linspace(0.1, 0.9, 9))
    ok = np.isfinite(b["mh"].to_numpy()) & np.isfinite(cuts[b["d"].to_numpy(), 0])
    b = b[ok].copy()
    b["dec"] = [int(np.searchsorted(cuts[d], v)) for d, v in zip(b["d"], b["mh"])]
    b = b.sort_values(["symbol", "d"])
    sym_code = {s: i for i, s in enumerate(srcs)}
    b["sc"] = b["symbol"].map(sym_code)
    new = np.ones(len(b), bool)
    new[1:] = (b["sc"].values[1:] != b["sc"].values[:-1]) | (b["d"].values[1:] != b["d"].values[:-1] + 1)
    b["seg"] = np.cumsum(new) - 1
    # 池内每行严格版平时波动的十档（与上面同一组切点）
    pdec = np.full(P["N"], -1)
    okr = np.isfinite(Mh) & np.isfinite(cuts[P["d"], 0])
    for t in np.unique(P["d"][okr]):
        s, e = P["day_start"][t], P["day_end"][t]
        v = Mh[s:e]; m = np.isfinite(v)
        pdec[s:e][m] = np.searchsorted(cuts[t], v[m])
    return b, pdec


def main():
    t0 = time.time()
    extra = sys.argv[1:]          # 只补算这几种配对（看过第一轮后加的，例如 K5），不重算抽样误差
    P, Y, hold, mts, S = core.load_all(["M5"] + extra if extra else core.SCHEMES)
    if extra:
        G["eval_schemes"] = extra
    C = classes(P)
    ndays = pd.Series(pd.DatetimeIndex(P["calendar"]).year).value_counts().to_dict()
    rowidx = np.full((len(P["symbols"]), len(P["calendar"])), -1, np.int64)
    rowidx[P["sym"], P["d"]] = np.arange(P["N"])
    b, pdec = prep_bb(P)

    def day_rows_by_dec(t, lo, hi):
        s, e = P["day_start"][t], P["day_end"][t]
        r = np.arange(s, e)
        return r[(pdec[s:e] >= lo) & (pdec[s:e] <= hi)]

    G.update(P=P, Y=Y, hold=hold, mts=mts, S=S, C=C, ndays=ndays, rowidx=rowidx,
             bb=(b["sc"].to_numpy(), b["d"].to_numpy(), b["dec"].to_numpy(), b["seg"].to_numpy()),
             day_rows_by_dec=day_rows_by_dec)
    info = [f"bottom_burst 买点落在决策日范围内且有平时波动的 {len(b):,} 个（{b['symbol'].nunique()} 只来源股，"
            f"{b['seg'].nunique()} 段）；来源股平时波动十档分布 {np.bincount(b['dec'], minlength=10).tolist()}"]
    info.append("各类整类股票日数：" + "，".join(f"{k} {int(v.sum()):,}" for k, v in C.items()))
    print("\n".join(info), f"ready {time.time() - t0:.0f}s", flush=True)
    full_names = list(C)
    disp_tasks = [(n, r) for n in ["rand"] + JUDGED + CHECKS for r in range(N_REP)]
    with get_context("fork").Pool(12) as mp:
        clust = mp.map_async(task_clust, range(N_REP), chunksize=1)
        disp = mp.map_async(task_disp, disp_tasks, chunksize=4)
        full = mp.map_async(task_full, full_names, chunksize=1)
        res_full = [r for ch in full.get() for r in ch]
        res_disp = [r for ch in disp.get() for r in ch]
        res_clust = [r for ch in clust.get() for r in ch]
    reps = pd.DataFrame(res_disp + res_clust)
    tag = "" if not extra else "-" + "-".join(extra)
    reps.to_csv(core.SCR / f"bias_reps{tag}.csv.gz", index=False)
    agg = reps.groupby(["cls", "form", "scope", "scheme"])
    mean = agg[core.METRICS + ["n", "n_stocks"]].mean().reset_index()
    sd = agg[core.METRICS].std(ddof=1).add_prefix("repsd_").reset_index(drop=True)
    summ = pd.concat([mean, sd], axis=1)
    out = pd.concat([pd.DataFrame(res_full), summ], ignore_index=True)
    out.to_csv(HERE / f"11-bias{tag}.csv.gz", index=False)
    (HERE / f"11-bias{tag}_out.txt").write_text("\n".join(info) + f"\n耗时 {time.time() - t0:.0f}s\n")
    print(f"done {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
