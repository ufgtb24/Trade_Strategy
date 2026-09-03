"""S2: bo 级 label 对照 —— 多 measure 是「新信息」还是「等价于把门槛调松」?

三组对照(同一 union 内部分组,自动同期同池,免掉跨配置的样本构成混淆):
  shared      : peak_measure=high 与 close 都产出的 bo bar
  high_only   : 仅 high 口径产出
  close_only  : 仅 close 口径产出(= 多 measure 相对 high 基准的边际增量)

Occam 对照(关键):close_pk 价位系统性低于 high_pk(S1 实测均值 ~5%),所以
「加入 close_pk」在价位维度上等价于「把 high_pk 的门槛下调若干个百分点」。
故扫 peak_measure=high × exceed_threshold ∈ {0.003, 0, -0.01, ...},取 bo 计数
与 union 相当的那一档作 M_thresh(调松产生的边际 bo),与 M_measure(=close_only)
比 label。若两者不可区分 → 多 measure 不是新自由度,只是更贵的调松。

label 口径与 path2/eval.py 官方一致:
  mfr_N  = max(high[t+1..t+N])/close[t] - 1          (match_forward_returns 单点特例)
  FP     = _first_passage_at(几何对称 k, M=rolling_atr_pct_nanmedian(...,20))
基线 = 全宇宙随机日(同一 M、同一 k、同一 horizon)。
"""
from __future__ import annotations

import pickle
import random
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from path2.atoms.breakout import BODetector                      # noqa: E402
from path2.calc.atr import FP_ATR_WINDOW, rolling_atr_pct_nanmedian  # noqa: E402
from path2.eval import _first_passage_at, _ticker_seed           # noqa: E402
from path2_web.data import slice_window                          # noqa: E402

PKL_DIR = Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls")
START, END = "2021-01-01", "2026-03-08"
HORIZON = 40          # configs/path2_web.yaml label_horizon
FP_K = 5.0            # path2.eval.DEFAULT_FP_K
RANDOM_DAYS = 12      # 每股随机日基线抽样数

BO_BASE = dict(
    total_window=20, min_side_bars=6, min_relative_height=0.2,
    peak_supersede_threshold=0.01, vol_baseline_period=63,
    breakout_measure="close",
)

# (标签, peak_measure, exceed_threshold)
CONFIGS = [
    ("high",      "high",     0.003),
    ("close",     "close",    0.003),
    ("body_top",  "body_top", 0.003),
    ("high_e000", "high",     0.000),
    ("high_e-01", "high",    -0.010),
    ("high_e-02", "high",    -0.020),
    ("high_e-03", "high",    -0.030),
    ("high_e-05", "high",    -0.050),
]


def bo_bars(df, peak_measure, exceed):
    det = BODetector(peak_measure=peak_measure, exceed_threshold=exceed, **BO_BASE)
    return {e.start_idx for e in det.detect(df)}


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    files = sorted(PKL_DIR.glob("*.pkl"))
    random.Random(20260831).shuffle(files)

    rows = []          # 每个 bo bar 一行
    base_rows = []     # 随机日基线
    counts = defaultdict(int)
    done = 0
    for f in files:
        if done >= n:
            break
        try:
            with open(f, "rb") as fh:
                raw = pickle.load(fh)
            if not isinstance(raw, pd.DataFrame):
                continue
            win = slice_window(raw, START, END)
        except Exception:
            continue
        if len(win) < 300:
            continue
        sym = f.stem
        try:
            sets = {name: bo_bars(win, pm, ex) for name, pm, ex in CONFIGS}
        except Exception as e:
            print(f"skip {sym}: {e}", file=sys.stderr)
            continue
        done += 1

        hi = win["high"].values
        lo = win["low"].values
        cl = win["close"].values
        M = rolling_atr_pct_nanmedian(win["high"], win["low"], win["close"],
                                      FP_ATR_WINDOW).values
        n_bars = len(win)

        def label(t):
            if t + HORIZON >= n_bars:
                return None
            mfr = float(hi[t + 1: t + HORIZON + 1].max()) / float(cl[t]) - 1.0
            mdd = float(lo[t + 1: t + HORIZON + 1].min()) / float(cl[t]) - 1.0
            fp = _first_passage_at(hi, lo, cl, M, t, HORIZON, FP_K)
            return mfr, mdd, fp

        for name in sets:
            counts[name] += len(sets[name])

        union = sets["high"] | sets["close"]
        for t in sorted(union):
            in_h, in_c = t in sets["high"], t in sets["close"]
            grp = "shared" if (in_h and in_c) else ("high_only" if in_h else "close_only")
            L = label(t)
            if L is None:
                continue
            rows.append(dict(symbol=sym, bar=t, group=grp,
                             mfr=L[0], mdd=L[1], fp=L[2], M=float(M[t]),
                             in_e_m01=t in sets["high_e-01"],
                             in_e_m02=t in sets["high_e-02"],
                             in_e_m03=t in sets["high_e-03"],
                             in_e_m05=t in sets["high_e-05"],
                             in_body=t in sets["body_top"]))

        # 调松侧的边际 bo(相对 high 基准),供 M_thresh 组
        for name in ("high_e-01", "high_e-02", "high_e-03", "high_e-05"):
            for t in sorted(sets[name] - sets["high"]):
                L = label(t)
                if L is None:
                    continue
                rows.append(dict(symbol=sym, bar=t, group=f"marg_{name}",
                                 mfr=L[0], mdd=L[1], fp=L[2], M=float(M[t]),
                                 in_e_m01=False, in_e_m02=False, in_e_m03=False,
                                 in_e_m05=False, in_body=t in sets["body_top"]))
        # body_top 相对 high 的边际
        for t in sorted(sets["body_top"] - sets["high"]):
            L = label(t)
            if L is None:
                continue
            rows.append(dict(symbol=sym, bar=t, group="marg_body", mfr=L[0], mdd=L[1],
                             fp=L[2], M=float(M[t]), in_e_m01=False, in_e_m02=False,
                             in_e_m03=False, in_e_m05=False, in_body=True))

        # 随机日基线
        cand = [i for i in range(n_bars) if i + HORIZON < n_bars
                and np.isfinite(M[i]) and M[i] > 0]
        if cand:
            rng = np.random.default_rng(_ticker_seed(sym))
            for i in rng.choice(cand, size=min(RANDOM_DAYS, len(cand)), replace=False):
                L = label(int(i))
                if L is None:
                    continue
                base_rows.append(dict(symbol=sym, bar=int(i), group="random_day",
                                      mfr=L[0], mdd=L[1], fp=L[2], M=float(M[i])))

    df = pd.DataFrame(rows)
    bs = pd.DataFrame(base_rows)
    outdir = Path(__file__).parent
    df.to_csv(outdir / "s2_bo_label.csv", index=False)
    bs.to_csv(outdir / "s2_baseline.csv", index=False)

    print(f"样本股票数 = {done}  窗口 {START}~{END}  horizon={HORIZON} k={FP_K}")
    print("--- 各配置 bo 总数 ---")
    for name, _, ex in CONFIGS:
        print(f"  {name:10s} exceed={ex:+.3f}  bo={counts[name]}")
    print()
    report(df, bs)


def report(df, bs):
    def stat(sub, name):
        n = len(sub)
        if n == 0:
            print(f"  {name:14s} n=0")
            return
        med = sub["mfr"].median()
        # 中位数 bootstrap CI
        rs = np.random.default_rng(7)
        boot = [np.median(rs.choice(sub["mfr"].values, n, replace=True)) for _ in range(600)]
        lo_, hi_ = np.percentile(boot, [2.5, 97.5])
        fp = sub["fp"].value_counts()
        tot = fp.sum()
        up = fp.get("up", 0) / tot if tot else float("nan")
        dn = fp.get("down", 0) / tot if tot else float("nan")
        print(f"  {name:14s} n={n:6d}  mfr_med={med:+.4f} [{lo_:+.4f},{hi_:+.4f}]  "
              f"mdd_med={sub['mdd'].median():+.4f}  FP up={up:.3f} down={dn:.3f} "
              f"up-down={up-dn:+.3f}  M_med={sub['M'].median():.4f}")

    print("--- label 分组对照 (mfr = 未来40日最大涨幅; FP = 首次穿越, k=5) ---")
    stat(bs, "random_day")
    for g in ["shared", "high_only", "close_only", "marg_body",
              "marg_high_e-01", "marg_high_e-02", "marg_high_e-03", "marg_high_e-05"]:
        stat(df[df.group == g], g)


if __name__ == "__main__":
    main()
