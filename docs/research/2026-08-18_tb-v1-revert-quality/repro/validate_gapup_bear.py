# -*- coding: utf-8 -*-
"""全局验证「跳空高开+阴线+放量(次日恢复+短上影)=利好」假设。

形态 A(用户完整假设,event 日 i):
  跳空高开 gap=open[i]/close[i-1]-1 >= GAP_PCT;阴线 close<open;
  放量 vol[i]/median(vol[i-20:i]) >= VOL_RATIO;上影极短 (high-max(o,c))/(high-low) <= SHADOW;
  次日恢复 |close[i+1]/close[i-1]-1| <= RECOVER;孤立:i±1 不是跳空高开阴线。
对照:
  B = A 去放量(缩量 vol_ratio <= 1.5)   —— 量能组件的必要性
  C = A 去跳空(平开 |gap|<=0.5%)         —— 跳空组件的必要性
  D = 随机日基线(同池同口径,seed=ticker md5)
标签(无前瞻:形态含 i+1 恢复,故从 i+1 收盘起算):
  fr40 = max(high[i+2..i+41])/close[i+1]-1;FP 四态(k=5,M=rolling ATR% nanmedian(20),同 eval 口径)。
池:scan 同窗 2024-09-19..2026-03-08 + 近似 scan filters(中位 close∈[0.5,30] 且中位 vol>=1e4)。
"""
from __future__ import annotations

import hashlib
import os
import pickle
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from path2.calc.atr import rolling_atr_pct_nanmedian
from path2.eval import _first_passage_at

PKL_DIR = Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls")
OUT_DIR = Path(__file__).resolve().parent
WIN_START, WIN_END = "2024-09-19", "2026-03-08"
HORIZON, FP_K = 40, 5.0
GAP_PCT = float(os.environ.get("GAP_PCT", 0.03))
VOL_RATIO = float(os.environ.get("VOL_RATIO", 3.0))
SHADOW = float(os.environ.get("SHADOW", 0.10))
RECOVER = float(os.environ.get("RECOVER", 0.03))
TAG = os.environ.get("TAG", "base")
N_RANDOM_PER_STOCK = 3


def _is_gapup_bear(o, c, g, v_med, i, gap_pct, vol_ratio):
    return (g[i] >= gap_pct and c[i] < o[i] and v_med[i] >= vol_ratio)


def _scan_one(pkl_path: str):
    sym = Path(pkl_path).stem
    try:
        df = pd.read_pickle(pkl_path)
        if getattr(df.index, "tz", None) is not None:
            df.index = df.index.tz_localize(None)
        win = df.loc[WIN_START:WIN_END]
        if len(win) < 120:
            return sym, None
        win = win.reset_index()
        o = win["open"].to_numpy(float); h = win["high"].to_numpy(float)
        l = win["low"].to_numpy(float); c = win["close"].to_numpy(float)
        v = win["volume"].to_numpy(float)
        # 近似 scan filters(股票级)
        if not (0.5 <= np.median(c) <= 30.0) or np.median(v) < 1e4:
            return sym, None
        n = len(c)
        pc = np.concatenate([[c[0]], c[:-1]])
        gap = o / pc - 1.0
        v_med = pd.Series(v).rolling(20, min_periods=20).median().to_numpy()
        rng = np.maximum(h - l, 1e-9)
        upper = (h - np.maximum(o, c)) / rng
        M = rolling_atr_pct_nanmedian(win["high"], win["low"], win["close"], 20).values
        recov = np.abs(np.concatenate([c[1:], [np.nan]]) / pc - 1.0)  # recov[i]=|c[i+1]/c[i-1]-1|
        bear_gap = (gap >= 0.03) & (c < o) & (v_med >= 3.0)   # 孤立性判据用(粗)

        events = {"A": [], "B": [], "C": []}
        t0 = 21
        for i in range(t0, n - HORIZON - 2):
            if not np.isfinite(v_med[i]) or not np.isfinite(recov[i]):
                continue
            base_a = (c[i] < o[i] and upper[i] <= SHADOW and recov[i] <= RECOVER
                      and not bear_gap[i - 1] and not bear_gap[i + 1])
            if not base_a:
                continue
            t = i + 1   # 买入=i+1 收盘(形态含 i+1,无前瞻)
            if not np.isfinite(M[t]) or M[t] <= 0:
                continue
            tag = None
            if _is_gapup_bear(o, c, gap, v_med, i, GAP_PCT, VOL_RATIO):
                tag = "A"
            elif gap[i] >= GAP_PCT and v_med[i] <= 1.5:
                tag = "B"   # 跳空+阴线+短影+恢复,但缩量
            elif abs(gap[i]) <= 0.005 and v_med[i] >= VOL_RATIO:
                tag = "C"   # 平开+阴线+放量+短影+恢复
            if tag:
                fr = float(np.max(h[t + 1: t + HORIZON + 1])) / c[t] - 1.0
                st = _first_passage_at(h, l, c, M, t, HORIZON, FP_K)
                events[tag].append((i, fr, st))
        # D 随机日基线(同池同口径)
        rng_np = np.random.default_rng(
            (int(hashlib.md5(sym.encode()).hexdigest(), 16) % 2**32) ^ 20260818)
        cand = np.arange(t0, n - HORIZON - 2)
        rand = []
        if len(cand):
            for t in rng_np.choice(cand, size=min(N_RANDOM_PER_STOCK, len(cand)), replace=False):
                if np.isfinite(M[t]) and M[t] > 0:
                    fr = float(np.max(h[t + 1: t + HORIZON + 1])) / c[t] - 1.0
                    st = _first_passage_at(h, l, c, M, int(t), HORIZON, FP_K)
                    rand.append((int(t), fr, st))
        return sym, {"A": events["A"], "B": events["B"], "C": events["C"], "D": rand}
    except Exception as e:   # noqa: BLE001
        return sym, f"ERR {type(e).__name__}: {e}"


def _agg(evts):
    frs = [e[1] for e in evts]
    fp = {"up": 0, "down": 0, "both": 0, "none": 0}
    for e in evts:
        if e[2] is not None:
            fp[e[2]] += 1
    ratio = fp["up"] / (fp["up"] + fp["down"] + fp["both"]) \
        if fp["up"] + fp["down"] + fp["both"] else np.nan
    return frs, fp, ratio


def main() -> None:
    pkls = sorted(str(p) for p in PKL_DIR.glob("*.pkl"))
    print(f"universe: {len(pkls)} pkls")
    all_events = {"A": [], "B": [], "C": [], "D": []}
    errs = 0
    with ProcessPoolExecutor(max_workers=26) as ex:
        for sym, res in ex.map(_scan_one, pkls, chunksize=32):
            if isinstance(res, str):
                errs += 1
                continue
            if res is None:
                continue
            for k in all_events:
                all_events[k].extend((sym, i, fr, st) for i, fr, st in res[k])
    print(f"errors={errs}")
    names = {"A": "A 跳空+阴线+放量+短影+恢复(完整假设)",
             "B": "B 同上但缩量(<=1.5x)", "C": "C 同上但平开(|gap|<=0.5%)",
             "D": "D 随机日基线"}
    summary = {}
    for k in "ABCD":
        frs, fp, ratio = _agg([(i, fr, st) for _, i, fr, st in all_events[k]])
        summary[k] = dict(n=len(frs), fr_med=float(np.median(frs)) if frs else np.nan,
                          fr_mean=float(np.mean(frs)) if frs else np.nan,
                          fr_q25=float(np.quantile(frs, .25)) if frs else np.nan,
                          fp_up=fp["up"], fp_down=fp["down"], fp_none=fp["none"], ratio=ratio)
        print(f"{names[k]:<38} n={len(frs):5d} fr_med={summary[k]['fr_med']:.4f} "
              f"fr_mean={summary[k]['fr_mean']:.4f} FP={ratio:.4f} "
              f"(up/down/none={fp['up']}/{fp['down']}/{fp['none']})")
    pd.DataFrame(summary).T.to_csv(OUT_DIR / "gapup_bear_validation.csv")
    # 股票级去重版(每股只留首个事件,防单股刷屏)
    for k in "ABC":
        seen, dedup = set(), []
        for sym, i, fr, st in all_events[k]:
            if sym not in seen:
                seen.add(sym); dedup.append((sym, i, fr, st))
        frs, fp, ratio = _agg([(i, fr, st) for sym, i, fr, st in dedup])
        print(f"{k}(每股首事件去重)            n={len(frs):5d} fr_med={np.median(frs):.4f} FP={ratio:.4f}")
    with open(OUT_DIR / "gapup_bear_events.pkl", "wb") as f:
        pickle.dump(all_events, f)
    print("saved gapup_bear_validation.csv / gapup_bear_events.pkl")


if __name__ == "__main__":
    main()
