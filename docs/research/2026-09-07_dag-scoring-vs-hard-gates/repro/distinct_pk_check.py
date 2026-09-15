"""distinct_pk 登记前的两道检查:
  ① 三档 k(4/5/6)首次穿越率是否同向 —— 副产品登记簿的最低及格线;
  ② 是否只是 burst_count(簇内 bo 根数)的代理 —— 在 count 分层内看还剩多少。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from path2.calc.atr import FP_ATR_WINDOW, rolling_atr_pct_nanmedian   # noqa: E402
from path2.eval import _first_passage_at, _ticker_seed                # noqa: E402
from path2.dag.engine import analyze as dag_analyze                   # noqa: E402
from path2_web.data import slice_window                               # noqa: E402
from path2_web.serialize import _resolve_end_events                   # noqa: E402
from extract_wide import _params_wide, LABEL_HORIZON, DATA_DIR, RATIO, HEAD_BUFFER  # noqa: E402
from path2_apps.bb_v1.dag_spec import build_pattern                   # noqa: E402
from analyze import atr_layers, layer_of, load                        # noqa: E402

KS = [4.0, 5.0, 6.0]
RNG = np.random.default_rng(20260907)
NBOOT = 2000
WIN = {"w2025": ("2025-01-01", "2026-01-01"), "w2024": ("2024-01-01", "2025-01-01")}


def _one(args):
    """重跑一只票,按 k=4/5/6 各出一套 match 级首穿计数 + 随机日基线计数。"""
    sym, sd, ed = args
    import pandas as pd
    from path2.eval import match_first_passage
    try:
        s, e = pd.Timestamp(sd), pd.Timestamp(ed)
        win = slice_window(pd.read_pickle(DATA_DIR / f"{sym}.pkl"),
                           (s - pd.Timedelta(days=round(HEAD_BUFFER * RATIO))).date(),
                           (e + pd.Timedelta(days=round(LABEL_HORIZON * RATIO))).date())
        if len(win) == 0:
            return sym, [], []
        sw = win[(win["date"] >= s) & (win["date"] <= e)]
        if len(sw) == 0 or sw["volume"].mean() <= 10000.0:
            return sym, [], []
        p = _params_wide()
        res = dag_analyze(build_pattern(p), win, p)
        lo = int(win["date"].searchsorted(s, "left"))
        hi = int(win["date"].searchsorted(e, "right")) - 1
        M = rolling_atr_pct_nanmedian(win["high"], win["low"], win["close"],
                                      FP_ATR_WINDOW).values
        rows, seen = [], set()
        for m in res.matches:
            evs = _resolve_end_events(m, "tb")
            if not any(s <= win["date"].iat[ev.start_idx] <= e for ev in evs):
                continue
            if not any(0.5 <= float(win["close"].iat[ev.start_idx]) <= 30.0 for ev in evs):
                continue
            tb, bu = m.node_index["tb"], m.node_index["burst"]
            key = (sym, tb.instance_id, tb.anchor_bo_id)
            if key in seen:
                continue
            seen.add(key)
            r = dict(symbol=sym, distinct_pk=int(bu.distinct_pk),
                     burst_count=int(bu.count), vol_spike=float(bu.max_bar_vol_ratio),
                     atr_pct=float(M[tb.start_idx]) if np.isfinite(M[tb.start_idx]) else np.nan)
            for k in KS:
                fp = match_first_passage(m, "tb", win, LABEL_HORIZON, k=k,
                                         sample_window=(lo, hi), M=M)
                r[f"up{k}"], r[f"dn{k}"] = fp["up"], fp["down"]
            rows.append(r)
        # 基线:同 20 日
        hi_a, lo_a, cl_a = (win["high"].to_numpy(float), win["low"].to_numpy(float),
                            win["close"].to_numpy(float))
        dts = win["date"].values
        cand = [i for i in range(len(win))
                if s <= pd.Timestamp(dts[i]) <= e and i + LABEL_HORIZON < len(win)]
        base = []
        if cand:
            rng = np.random.default_rng(_ticker_seed(sym))
            for t in rng.choice(cand, size=min(20, len(cand)), replace=False):
                t = int(t)
                d = dict(atr_pct=float(M[t]))
                for k in KS:
                    d[f"s{k}"] = _first_passage_at(hi_a, lo_a, cl_a, M, t, LABEL_HORIZON, k)
                base.append(d)
        return sym, rows, base
    except Exception:                                        # noqa: BLE001
        return sym, [], []


def base_fpr(bl, k):
    """{layer: 基线 FPR},丢弃 ATR% 缺失(layer=-1)的行。"""
    out = {}
    for l, g in bl[bl.layer >= 0].groupby("layer"):
        uu, dd = (g[f"s{k}"] == "up").sum(), (g[f"s{k}"] == "down").sum()
        if uu + dd:
            out[int(l)] = uu / (uu + dd)
    return out


def dfpr_arr(up, dn, lay, bf):
    u, d = up.sum(), dn.sum()
    if u + d == 0:
        return np.nan
    n = len(lay)
    b = sum((lay == l).sum() / n * v for l, v in bf.items())
    return u / (u + d) - b


def pack(sub, k):
    return (sub[f"up{k}"].values, sub[f"dn{k}"].values, sub.layer.values,
            sub.symbol.values)


def dfpr_with_ci(sub, bf, k):
    up, dn, lay, syms = pack(sub, k)
    obs = dfpr_arr(up, dn, lay, bf)
    uniq = np.unique(syms)
    if len(uniq) < 5:
        return obs, (np.nan, np.nan)
    idx = {g: np.where(syms == g)[0] for g in uniq}
    out = []
    for _ in range(NBOOT):
        sel = np.concatenate([idx[g] for g in RNG.choice(uniq, size=len(uniq), replace=True)])
        v = dfpr_arr(up[sel], dn[sel], lay[sel], bf)
        if np.isfinite(v):
            out.append(v)
    if not out:
        return obs, (np.nan, np.nan)
    return obs, (np.percentile(out, 2.5), np.percentile(out, 97.5))


def main():
    from multiprocessing import Pool
    syms = sorted(p.stem for p in DATA_DIR.glob("*.pkl"))
    for tag, (sd, ed) in WIN.items():
        rows, base = [], []
        with Pool(24) as pool:
            for _, r, b in pool.imap_unordered(_one, [(s, sd, ed) for s in syms],
                                               chunksize=16):
                rows.extend(r)
                base.extend(b)
        d, bl = pd.DataFrame(rows), pd.DataFrame(base)
        cuts = [float(bl.atr_pct.quantile(1/3)), float(bl.atr_pct.quantile(2/3))]
        d["layer"] = layer_of(d.atr_pct.values, cuts)
        bl["layer"] = layer_of(bl.atr_pct.values, cuts)
        d = d[d.layer >= 0].copy()          # ATR% 缺失的买点无法层匹配,剔除
        BF = {k: base_fpr(bl, k) for k in KS}
        print(f"\n════ {tag} · n={len(d)} sym={d.symbol.nunique()} 基线日={len(bl)} ════")
        print("① 三档 k 的 ΔFPR(vs 波动率层匹配基线,整簇自助 95%CI)")
        for name, sub in [("全体宽进", d), ("distinct_pk>=3", d[d.distinct_pk >= 3]),
                          ("distinct_pk>=4", d[d.distinct_pk >= 4])]:
            line = f"   {name:<16} n={len(sub):>5}"
            for k in KS:
                v, ci = dfpr_with_ci(sub, BF[k], k)
                line += f" | k={k:.0f}: {v:+.4f} [{ci[0]:+.4f},{ci[1]:+.4f}]"
            print(line)
        print("② 是不是 burst_count 的代理:在 count 分层内看 distinct_pk(k=5)")
        for c, g in d.groupby("burst_count"):
            if len(g) < 60 or g.distinct_pk.nunique() < 2:
                continue
            thr = 3 if c >= 3 else 2
            hi_, lo_ = g[g.distinct_pk >= thr], g[g.distinct_pk < thr]
            if len(hi_) < 30 or len(lo_) < 30:
                continue
            vh, cih = dfpr_with_ci(hi_, BF[5.0], 5.0)
            vl, cil = dfpr_with_ci(lo_, BF[5.0], 5.0)
            print(f"   count={c}: pk>={thr} n={len(hi_):>4} ΔFPR={vh:+.4f} "
                  f"[{cih[0]:+.4f},{cih[1]:+.4f}]  vs  pk<{thr} n={len(lo_):>4} "
                  f"ΔFPR={vl:+.4f} [{cil[0]:+.4f},{cil[1]:+.4f}]")
        print("   对照 · burst_count 自身(不分 pk):")
        for c in sorted(d.burst_count.unique()):
            g = d[d.burst_count == c]
            if len(g) < 60:
                continue
            print(f"     count={c} n={len(g):>5} ΔFPR={dfpr_arr(*pack(g, 5.0)[:3], BF[5.0]):+.4f}")


if __name__ == "__main__":
    main()
