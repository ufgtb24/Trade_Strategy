"""ABOS burst_254_257 机器逐根轨迹复刻(任务 0:机制归因)。

切窗对齐 scan 20260817T142145(win_start=2024-09-19, win_end=2026-03-08),
参数取 params_snapshot.tb:max_rise_k=1.5, stop_confirm_bars=1, vol_window=14,
anchor_mode=span_min, max_span=60, measure=close。
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

import numpy as np
import pandas as pd

from path2.calc.atr import calculate_tr_median
from path2_web.data import slice_window

WIN_START, WIN_END = "2024-09-19", "2026-03-08"
BO_IDX = 257                      # burst_254_257#0 的 last_bo=bo_257,end_idx=257
SPAN = (254, 257)                 # burst span(anchor_mode=span_min)
VOL_WINDOW, MAX_RISE_K, STOP_K, MAX_SPAN = 14, 1.5, 1, 60

df_full = pd.read_pickle(REPO / "datasets/pkls/ABOS.pkl")
win = slice_window(df_full, WIN_START, WIN_END).reset_index(drop=True)
closes = win["close"].to_numpy(float)
opens = win["open"].to_numpy(float)
vol = calculate_tr_median(win["high"], win["low"], win["close"], VOL_WINDOW).to_numpy(float)
gbot = float(closes[SPAN[0]:SPAN[1] + 1].min())
peak0 = float(closes[BO_IDX])

print(f"窗口行数={len(win)}  bo={BO_IDX}({win['date'][BO_IDX].date()})  "
      f"burst span {SPAN[0]}-{SPAN[1]}  burst span close min={gbot:.4f}  peak0={peak0:.4f}")
print(f"burst 涨幅(close 首尾): {closes[SPAN[0]]:.4f} -> {closes[SPAN[1]]:.4f} "
      f"= {(closes[SPAN[1]]/closes[SPAN[0]]-1)*100:.2f}%  "
      f"绝对幅度={closes[SPAN[1]]-closes[SPAN[0]]:.4f}")

state, peak, trough, cnt = "UP", peak0, float("inf"), 0
enter = -1
segs = []
print(f"\n{'i':>4} {'date':>10} {'state进':>7} {'open':>7} {'close':>7} {'vol(i)':>7} "
      f"{'trough':>7} {'反弹阈值':>8} {'(c-tr)/vol':>10} {'Δc':>7} {'事件':<46}")
for i in range(BO_IDX + 1, min(BO_IDX + MAX_SPAN, len(win) - 1) + 1):
    c = float(closes[i])
    st_in = state
    thr = trough + MAX_RISE_K * vol[i] if np.isfinite(trough) else float("nan")
    note = []

    if c < gbot:
        if state == "STABLE":
            segs.append((enter, i - 1, "break")); note.append("破 gbot → 末段 break 截断")
        state = "DEAD(break)"; note.append(f"close {c:.4f} < gbot {gbot:.4f} 机器终止")
        print(f"{i:>4} {str(win['date'][i].date()):>10} {st_in:>7} {opens[i]:>7.3f} {c:>7.3f} "
              f"{vol[i]:>7.4f} {trough:>7.3f} {thr:>8.3f} "
              f"{((c - trough)/vol[i]) if (np.isfinite(trough) and vol[i]==vol[i]) else float('nan'):>10.2f} "
              f"{c-float(closes[i-1]):>+7.3f} {'; '.join(note)}")
        break
    if state == "UP":
        if c > peak:
            peak = c; note.append(f"peak→{c:.3f}")
        red = float(win["close"].iloc[i]) < float(opens[i])
        if red or c < float(closes[i - 1]):
            state, trough, cnt = "DOWN", c, 0
            note.append("阴线或收跌 → 转 DOWN(trough=当根 close)")
        else:
            note.append("UP 持续(非阴线且未收跌)")
    elif state == "DOWN":
        if c < trough:
            trough, cnt = c, 0; note.append(f"严格新低刷新 trough→{c:.3f}(cnt清零)")
        elif vol[i] == vol[i] and c > trough + MAX_RISE_K * vol[i]:
            state = "UP"; note.append("close > trough+1.5*vol → rise 臂转 UP(不产段)")
        else:
            cnt += 1
            note.append(f"不刷新 cnt={cnt}")
            if cnt >= STOP_K:
                state, enter = "STABLE", i; note.append(f"cnt≥K → 入段 STABLE(enter={i})")
    else:  # STABLE
        if vol[i] == vol[i] and c > trough + MAX_RISE_K * vol[i] and c > peak:
            segs.append((enter, i - 1, "rise")); gbot_cur = trough
            state = "UP"; peak = max(peak, c)
            note.append(f"rise 收段({enter}-{i-1})→UP,gbot ratchet→{gbot_cur:.3f}")
        elif c < trough:
            segs.append((enter, i - 1, "weak"))
            state, trough, cnt = "DOWN", c, 0
            note.append(f"破段底 → weak 收段({enter}-{i-1})转 DOWN(trough→{c:.3f})")
        else:
            note.append("段内")
    print(f"{i:>4} {str(win['date'][i].date()):>10} {st_in:>7} {opens[i]:>7.3f} {c:>7.3f} "
          f"{vol[i]:>7.4f} {trough:>7.3f} {thr:>8.3f} "
          f"{((c - trough)/vol[i]) if (np.isfinite(trough) and vol[i]==vol[i]) else float('nan'):>10.2f} "
          f"{c-float(closes[i-1]):>+7.3f} {'; '.join(note)}")
    if i > BO_IDX + 16:
        break
if state == "STABLE":
    segs.append((enter, min(BO_IDX + MAX_SPAN, len(win) - 1), "timeout"))
print("\n产段:", segs, " (scan 对照: tb_seg_263 rise / tb_seg_267 rise, 机器 outcome=break)")
