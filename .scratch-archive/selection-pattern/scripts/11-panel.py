"""11 同日对照配对票 · 第一步：池内股票日面板（只读截断副本 datasets/pkls_until_20251231）。

池子照 chart_workflow/config.py 的默认池（全部待验证）：
  证券类别 ∈ {common, adr, mlp}（分类函数 = chart_workflow.securities.classify，名称取自
  .scratch/selection-pattern/scripts/09-securities.csv，不联网、不读 outputs/chart_workflow/ 的缓存）；
  close[t] ≤ 20（复权价近似当时价格）；dv_t = median(close·volume, t-19..t) ∈ [200 万, 1 亿]；
  M_t 有限且 ≥ 0.01；open[t+1] > 0；标签有效（t+40 在数据里 ⇒ 不晚于 2025-12-31）。
口径照 chart_workflow：
  M_t   = path2.calc.atr.rolling_atr_pct_nanmedian(high, low, close, 20)
  dir、mag = chart_workflow.labels.compute_labels(k=5, H=40)：买入价 P = open[t+1]，观察日 t+1..t+40，
          收盘首次穿越（上下线 P×/÷(1+5M)）；mag = max(high[t+1..t+40]) / P − 1（前瞻收益）
另存：
  Mh    = 「平时波动」：过去 250 个交易日（含 t）M 的中位数，至少 120 个有效 M（严格版，缺则 NaN）
  Mh_fb = 同上但至少 1 个有效 M（严格版缺失时配对用的退路，只在配对里用、不进假 pattern）
  lp[j] = ln(close[t+j] / P)，j = 1..40（float32）：一切按收盘离场的买卖规则都由它算
  sL    = ln(min(low[t-19..t]) / P)、sH = ln(max(high[t-59..t]) / P)：结构位（第 6 题用）
  dvr   = dv_t、px = close_t（检查用的成交额、价格假 pattern）

输出：scratchpad/11/panel.npz（行按 (日期, 股票) 排序）
运行：uv run python .scratch/selection-pattern/scripts/11-panel.py
"""
from __future__ import annotations

import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from chart_workflow.labels import compute_labels  # noqa: E402
from chart_workflow.securities import classify, COMMON_CLASSES  # noqa: E402
from path2.calc.atr import rolling_atr_pct_nanmedian  # noqa: E402

DATA = ROOT / "datasets/pkls_until_20251231"
SECS = ROOT / ".scratch/selection-pattern/scripts/09-securities.csv"
SCR = Path("/tmp/claude-1000/-home-yu-PycharmProjects-Trade-Strategy/28767886-41d8-46a8-b368-50cdb61bd556/scratchpad/11")
HARD_END = pd.Timestamp("2025-12-31")
K, H = 5.0, 40
POOL = dict(price_max=20.0, dv_min=2e6, dv_max=1e8, m_min=0.01)


def one(sym):
    raw = pd.read_pickle(DATA / f"{sym}.pkl")
    df = raw[["open", "high", "low", "close", "volume"]].astype(float)
    df.index = pd.DatetimeIndex(pd.to_datetime(df.index)).normalize()
    df = df[df.index <= HARD_END]
    if len(df) <= H + 21:
        return sym, None
    o, h, l, c, v = (df[x] for x in ("open", "high", "low", "close", "volume"))
    M = rolling_atr_pct_nanmedian(h, l, c, period=20)
    Mh = M.rolling(250, min_periods=120).median()
    Mh_fb = M.rolling(250, min_periods=1).median()
    dv = (c * v).rolling(20, min_periods=20).median()
    lab = compute_labels(o.values, h.values, l.values, c.values, M.values, K, H)
    n = len(df)
    P = lab["P"]
    lp = np.full((n, H), np.nan, np.float32)
    m = n - H
    cl = c.values
    with np.errstate(divide="ignore", invalid="ignore"):
        for j in range(1, H + 1):
            lp[:m, j - 1] = np.log(cl[j:m + j] / P[:m])
        sL = np.log(l.rolling(20, min_periods=20).min().values / P)
        sH = np.log(h.rolling(60, min_periods=60).max().values / P)
        Mv = M.values
        ok = (lab["valid"] & (cl <= POOL["price_max"]) & (dv.values >= POOL["dv_min"])
              & (dv.values <= POOL["dv_max"]) & np.isfinite(Mv) & (Mv >= POOL["m_min"])
              & np.isfinite(P) & (P > 0))
    ok &= np.isfinite(lp).all(1)
    if not ok.any():
        return sym, None
    idx = np.flatnonzero(ok)
    out = dict(date=df.index.values[idx], M=Mv[idx], Mh=Mh.values[idx], Mh_fb=Mh_fb.values[idx],
               dv=dv.values[idx], px=cl[idx], P=P[idx], dir=lab["dir"][idx].astype(np.int8),
               mag=lab["mag"][idx], sL=sL[idx], sH=sH[idx], lp=lp[idx])
    return sym, out


def main():
    t0 = time.time()
    secs = pd.read_csv(SECS, keep_default_na=False)
    names = {r.symbol: (r.name if r.name else None) for r in secs.itertuples()}
    symbols = sorted(p.stem for p in DATA.glob("*.pkl"))
    cls = {s: classify(s, names.get(s)) for s in symbols}
    agree = np.mean([cls[s] == r for s, r in zip(secs["symbol"], secs["cls"]) if s in cls])
    common = [s for s in symbols if cls[s] in COMMON_CLASSES]
    print(f"symbols {len(symbols)}, common/adr/mlp {len(common)}, "
          f"agreement with 09 cls column {agree:.4f}", flush=True)
    parts = {}
    with Pool(12) as p:
        for sym, out in p.imap_unordered(one, common, chunksize=16):
            if out is not None:
                parts[sym] = out
    syms = np.array(sorted(parts))
    keys = ["date", "M", "Mh", "Mh_fb", "dv", "px", "P", "dir", "mag", "sL", "sH", "lp"]
    cat = {k: np.concatenate([parts[s][k] for s in syms]) for k in keys}
    sym_idx = np.concatenate([np.full(len(parts[s]["date"]), i, np.int32) for i, s in enumerate(syms)])
    calendar = np.unique(cat["date"])
    d = np.searchsorted(calendar, cat["date"]).astype(np.int32)
    order = np.lexsort((sym_idx, d))
    arrs = {k: cat[k][order] for k in keys if k != "date"}
    SCR.mkdir(parents=True, exist_ok=True)
    np.savez(SCR / "panel.npz", symbols=syms, calendar=calendar, sym=sym_idx[order], d=d[order], **arrs)
    yrs = pd.DatetimeIndex(calendar[d[order]]).year
    print(f"rows {len(d):,}, stocks {len(syms)}, dates {calendar[0]}..{calendar[-1]}; per year "
          f"{pd.Series(yrs).value_counts().sort_index().to_dict()}; Mh strict coverage "
          f"{np.isfinite(arrs['Mh']).mean():.3f}; {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
