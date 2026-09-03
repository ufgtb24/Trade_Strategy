"""直接调 enumerate_segments_v4 复刻 bo_257 机器,对照 scan 段。"""
import sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
import pandas as pd
from path2.atoms.throwback_v4 import enumerate_segments_v4
from path2.calc.atr import calculate_tr_median
from path2_web.data import slice_window

df_full = pd.read_pickle(REPO / "datasets/pkls/ABOS.pkl")
win = slice_window(df_full, "2024-09-19", "2026-03-08").reset_index(drop=True)
vol = calculate_tr_median(win["high"], win["low"], win["close"], 14).to_numpy(float)
gbot = float(win["close"].iloc[254:258].min())
print("gbot =", gbot)
print("vol[258..274] =", [round(float(v),4) for v in vol[258:275]])
res = enumerate_segments_v4(
    win["close"].to_numpy(float), win["open"].to_numpy(float),
    257, gbot, vol, max_rise_k=1.5, stop_confirm_bars=1, max_span=60,
    real_closes=win["close"].to_numpy(float))
print("segments:", res.segments)
print("machine_outcome:", res.machine_outcome)
