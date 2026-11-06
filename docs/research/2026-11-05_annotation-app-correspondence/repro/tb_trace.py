"""企稳状态机逐根回放(研究用):逐字照 path2/atoms/throwback_v4.py::enumerate_segments_v4 的分支,
只多记每根的状态、峰、谷、支撑、当时波动和转换原因,用来讲「为什么这天买 / 不买」。
自检:回放出的企稳段必须与 detector 原版逐段相同(run_trace 里 assert)。
"""
from __future__ import annotations

import numpy as np

from path2.atoms.throwback_v4 import enumerate_segments_v4
from path2.calc.atr import calculate_tr_median


def run_trace(win, bo_idx: int, gbot0: float, *, max_rise_k=1.5, K=1, max_span=60, vol_window=14):
    closes = win["close"].values.astype(float)
    opens = win["open"].values.astype(float)
    vol = calculate_tr_median(win["high"], win["low"], win["close"], vol_window).values
    n = len(closes)
    end = min(bo_idx + max_span, n - 1)
    state, peak, trough, cnt, gbot, enter = "UP", float(closes[bo_idx]), float("inf"), 0, float(gbot0), -1
    segs, rows = [], []

    def vol_at(i):
        v = float(vol[i])
        return v if v == v else None

    outcome = "budget"
    for i in range(bo_idx + 1, end + 1):
        c = float(closes[i])
        before = state
        why = ""
        if c < gbot:
            why = f"收盘 {c:.3f} 跌破支撑 {gbot:.3f} → 机器结束"
            if state == "STABLE":
                segs.append((enter, i - 1, "break"))
            rows.append((i, before, "END", peak, trough, gbot, vol_at(i), why, False))
            outcome = "break"
            break
        if state == "UP":
            if c > peak:
                peak = c
            red = c < float(opens[i])
            if red or c < float(closes[i - 1]):
                state, trough, cnt = "DOWN", c, 0
                why = "阴线" if red else "收跌"
                why += " → 开始回落"
        elif state == "DOWN":
            v = vol_at(i)
            if c < trough:
                trough, cnt = c, 0
                why = "创回落新低"
            elif v is not None and c > trough + max_rise_k * v:
                state = "UP"
                why = f"比谷 {trough:.3f} 涨出 {(c - trough) / v:.2f} 倍波动 → 算追涨,回到上涨态"
            else:
                cnt += 1
                if cnt >= K:
                    state, enter = "STABLE", i
                    why = "不再创新低 → 企稳,开段"
        else:
            v = vol_at(i)
            if (v is not None and c > trough + max_rise_k * v) and (c > peak):
                gbot = trough
                segs.append((enter, i - 1, "rise"))
                why = f"涨出 {(c - trough) / v:.2f} 倍波动且过前峰 → 收段(追涨),支撑抬到 {trough:.3f}"
                state = "UP"
                if c > peak:
                    peak = c
            elif c < trough:
                segs.append((enter, i - 1, "weak"))
                why = f"跌破段底 {trough:.3f} → 收段,重新回落"
                state, trough, cnt = "DOWN", c, 0
        buy = state == "STABLE"
        rows.append((i, before, state, peak, trough, gbot, vol_at(i), why, buy))
    else:
        if state == "STABLE":
            segs.append((enter, end, "timeout"))
    ref = enumerate_segments_v4(closes, opens, bo_idx, gbot0, vol, max_rise_k=max_rise_k,
                                stop_confirm_bars=K, max_span=max_span, vol_window=vol_window,
                                real_closes=closes)
    assert [tuple(s) for s in ref.segments] == segs, (ref.segments, segs)
    return rows, segs, outcome
