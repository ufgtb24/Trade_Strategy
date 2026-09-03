"""OR 版(HEAD=scan 运行口径)ABOS 逐根轨迹 —— 复刻 scan 的 tb_263_267#0。"""
import sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
import numpy as np
import pandas as pd
from path2.calc.atr import calculate_tr_median
from path2_web.data import slice_window

WIN_START, WIN_END = "2024-09-19", "2026-03-08"
BO, SPAN = 257, (254, 257)
K, STOP_K, MAX_SPAN = 1.5, 1, 60

df_full = pd.read_pickle(REPO / "datasets/pkls/ABOS.pkl")
win = slice_window(df_full, WIN_START, WIN_END).reset_index(drop=True)
closes = win["close"].to_numpy(float); opens = win["open"].to_numpy(float)
vol = calculate_tr_median(win["high"], win["low"], win["close"], 14).to_numpy(float)
gbot = float(closes[SPAN[0]:SPAN[1]+1].min())
burst_rise = closes[SPAN[1]] - closes[SPAN[0]]
state, peak, trough, cnt = "UP", float(closes[BO]), float("inf"), 0
enter = -1; segs = []
hdr = f"{'i':>4} {'date':>10} {'st进':>6} {'open':>6} {'close':>6} {'vol':>6} {'trough':>6} {'阈值':>6} {'(c-tr)/v':>8} {'|Δc|/v':>6} {'|Δc|/涨幅':>9}"
print(hdr)
for i in range(BO+1, min(BO+MAX_SPAN, len(win)-1)+1):
    c = float(closes[i]); st = state; thr = trough + K*vol[i] if np.isfinite(trough) else float('nan')
    dv = abs(c-closes[i-1])/vol[i] if vol[i]==vol[i] else float('nan')
    db = abs(c-closes[i-1])/burst_rise if burst_rise else float('nan')
    note = []
    if c < gbot:
        if state == "STABLE": segs.append((enter, i-1, "break")); note.append("末段 break 截断")
        elif not segs: note.append("break_no_stable")
        else: note.append("段外破线已有段,机器完成")
        print(f"{i:>4} {str(win['date'][i].date()):>10} {st:>6} {opens[i]:>6.3f} {c:>6.3f} {vol[i]:>6.4f} {trough:>6.3f} {thr:>6.3f} "
              f"{((c-trough)/vol[i] if np.isfinite(trough) and vol[i]==vol[i] else float('nan')):>8.2f} {dv:>6.2f} {db:>9.1%}  {'; '.join(note)}")
        state = "DEAD"; break
    if state == "UP":
        if c > peak: peak = c
        red = c < opens[i]
        if red or c < closes[i-1]:
            state, trough, cnt = "DOWN", c, 0
            note.append(f"UP→DOWN(触发幅度 |Δc|/vol={dv:.2f}, /burst涨幅={db:.1%})")
        else: note.append("UP 持续")
    elif state == "DOWN":
        if c < trough: trough, cnt = c, 0; note.append(f"刷新 trough→{c:.3f}")
        elif vol[i]==vol[i] and c > trough + K*vol[i]:
            state = "UP"; note.append(f"rise 臂转 UP((c-tr)/vol={(c-trough)/vol[i]:.2f}>1.5,不产段)")
        else:
            cnt += 1
            if cnt >= STOP_K: state, enter = "STABLE", i; note.append(f"不刷新 cnt={cnt}≥K → 入段 enter={i}")
            else: note.append(f"不刷新 cnt={cnt}")
    else:
        if (vol[i]==vol[i] and c > trough + K*vol[i]) or (c > peak):
            segs.append((enter, i-1, "rise")); gbot = trough; state = "UP"
            note.append(f"OR-rise 收段({enter}-{i-1}),gbot→{gbot:.3f}"); peak = max(peak, c)
        elif c < trough:
            segs.append((enter, i-1, "weak")); state, trough, cnt = "DOWN", c, 0
            note.append(f"weak 收段({enter}-{i-1})转 DOWN")
        else: note.append("段内")
    print(f"{i:>4} {str(win['date'][i].date()):>10} {st:>6} {opens[i]:>6.3f} {c:>6.3f} {vol[i]:>6.4f} {trough:>6.3f} {thr:>6.3f} "
          f"{((c-trough)/vol[i] if np.isfinite(trough) and vol[i]==vol[i] else float('nan')):>8.2f} {dv:>6.2f} {db:>9.1%}  {'; '.join(note)}")
if state == "STABLE": segs.append((enter, min(BO+MAX_SPAN, len(win)-1), "timeout"))
print("\n产段:", segs, "→ scan 对照 tb_263_267#0 = [263-263 rise, 267-267 rise], machine=break")
