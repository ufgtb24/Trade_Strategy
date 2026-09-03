# -*- coding: utf-8 -*-
"""特征工程:对 samples.pkl 每 match 计算 revert 段负面特征(全部 confirm 时已知,无前瞻)。

段定义:
  上涨段 = burst span [burst_start, bo_idx](参照系);
  revert_idx = bo 后第一根「阴线或收跌」bar(用户定义,二者其一);
  下跌段 = [revert_idx, confirm](企稳确认即买点确认,此后特征冻结)。
产出 repro/features.csv(每 match 一行,含标签 fr/fp 与特征列)。
"""
from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
SAMPLES = HERE / "samples.pkl"
OUT_CSV = HERE / "features.csv"
TR_MED_WIN = 14   # 用户建议:单日跌幅分母用 TR 的 14 根中位数


def true_range(win: pd.DataFrame) -> np.ndarray:
    h, l, c = (win[k].to_numpy(dtype=float) for k in ("high", "low", "close"))
    pc = np.concatenate([[c[0]], c[:-1]])
    return np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))


def feats_of(row: dict) -> dict:
    win = row["win"]
    o = win["open"].to_numpy(dtype=float)
    h = win["high"].to_numpy(dtype=float)
    l = win["low"].to_numpy(dtype=float)
    c = win["close"].to_numpy(dtype=float)
    tr = true_range(win)
    bo, cf, tv = row["bo_idx"], row["confirm"], row["trough"]
    bs, be = row["burst_start"], row["burst_end"]

    # revert_idx:bo 后第一根 阴线(c<o) 或 收跌(c<c_prev)
    rev = bo + 1
    for i in range(bo + 1, cf + 1):
        if c[i] < o[i] or c[i] < c[i - 1]:
            rev = i
            break
    seg = range(rev, cf + 1)          # 下跌段(含 confirm 根)
    seg_bo = range(bo + 1, cf + 1)    # bo 后整个回踩段(备用口径)
    atr = float(np.mean(tr[bo - 14:bo]))           # bo-1 处 14 根 TR 均值(ATR 近似)
    tr_med = float(np.median(tr[max(rev - TR_MED_WIN, 0):rev + 1]))  # revert 前后 TR 中位数

    # ── 上涨段(参照系) ──
    up_days = be - bs + 1
    up_pct = c[bo] / c[bs - 1] - 1 if bs >= 1 else np.nan
    up_slope = up_pct / max(up_days, 1)

    # ── 1 超长阴线 ──
    bears = [i for i in seg if c[i] < o[i]]
    max_bear_body_atr = max((o[i] - c[i]) for i in bears) / atr if bears and atr > 0 else 0.0
    max_body_ratio = max((abs(c[i] - o[i]) / max(h[i] - l[i], 1e-9)) for i in seg)

    # ── 2 超长上影线 ──
    max_upper_atr = max((h[i] - max(o[i], c[i])) for i in seg) / atr if atr > 0 else 0.0
    max_upper_ratio = max((h[i] - max(o[i], c[i])) / max(h[i] - l[i], 1e-9) for i in seg)

    # ── 3 连续阴线 ──
    max_consec_bear = run = 0
    for i in seg_bo:
        run = run + 1 if c[i] < o[i] else 0
        max_consec_bear = max(max_consec_bear, run)
    bear_count = sum(1 for i in seg_bo if c[i] < o[i])
    max_consec_down = run = 0
    for i in seg_bo:
        run = run + 1 if c[i] < c[i - 1] else 0
        max_consec_down = max(max_consec_down, run)

    # ── 4 短期大幅回撤 ──
    dd_low = float(np.min(l[bo + 1:cf + 1])) / h[bo] - 1        # bo 高点起的最大回撤(low 口径)
    dd_close = float(np.min(c[bo + 1:cf + 1])) / c[bo] - 1       # close 口径
    anchor = float(np.min(l[row["burst_start"]:row["bo_idx"] + 1]))  # span_min 口径(judged=low)
    anchor_margin = float(np.min(l[bo + 1:cf + 1])) / anchor - 1     # 离破位线多近(负=已破,理论不产)
    rev_days = cf - rev + 1
    revert_pct = c[tv] / c[bo] - 1
    dd_vs_up = revert_pct / up_pct if up_pct and up_pct > 0 else np.nan   # 回撤/上涨 比例

    # ── 5 单日大跌幅 ──
    day_drop_pct = [(c[i - 1] - c[i]) / c[i - 1] for i in seg if c[i] < c[i - 1]]
    max_drop_pct = max(day_drop_pct) if day_drop_pct else 0.0
    max_drop_tr = max((c[i - 1] - c[i]) for i in seg if c[i] < c[i - 1]) / tr_med \
        if day_drop_pct and tr_med > 0 else 0.0
    max_drop_atr = max((c[i - 1] - c[i]) for i in seg if c[i] < c[i - 1]) / atr \
        if day_drop_pct and atr > 0 else 0.0

    # ── 6 涨跌斜率对比 ──
    down_days = max(tv - bo, 1)
    down_slope = (c[bo] - c[tv]) / c[bo] / down_days
    slope_ratio = down_slope / up_slope if up_slope and up_slope > 0 else np.nan

    return dict(
        symbol=row["symbol"], match_id=row["match_id"], outcome=row["outcome"],
        bo_idx=bo, revert_idx=rev, trough=tv, confirm=cf, end_idx=row["end_idx"],
        rev_days=rev_days, up_days=up_days, up_pct=up_pct, up_slope=up_slope,
        max_bear_body_atr=max_bear_body_atr, max_body_ratio=max_body_ratio,
        max_upper_atr=max_upper_atr, max_upper_ratio=max_upper_ratio,
        max_consec_bear=max_consec_bear, bear_count=bear_count,
        max_consec_down=max_consec_down,
        dd_low=dd_low, dd_close=dd_close, anchor_margin=anchor_margin,
        revert_pct=revert_pct, dd_vs_up=dd_vs_up,
        max_drop_pct=max_drop_pct, max_drop_tr=max_drop_tr, max_drop_atr=max_drop_atr,
        down_slope=down_slope, slope_ratio=slope_ratio,
        atr=atr, tr_med=tr_med,
        fr=row["fr"], fp_up=row["fp"]["up"], fp_down=row["fp"]["down"],
        fp_both=row["fp"]["both"], fp_none=row["fp"]["none"],
    )


def main() -> None:
    rows = pickle.loads(SAMPLES.read_bytes())
    df = pd.DataFrame([feats_of(r) for r in rows])
    df.to_csv(OUT_CSV, index=False)
    print(df[["fr", "dd_low", "max_drop_tr", "max_consec_bear", "slope_ratio"]].describe(
        percentiles=[0.25, 0.5, 0.75]).round(3).to_string())
    print(f"\nsaved {OUT_CSV}  rows={len(df)}")


if __name__ == "__main__":
    main()
