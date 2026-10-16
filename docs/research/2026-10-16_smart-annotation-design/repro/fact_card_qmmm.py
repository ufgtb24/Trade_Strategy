"""原型:同一张图按「最高价 / 收盘价」两种口径跑突破 detector,看能否把用户备注里的歧义变成并排事实。

只读 QMMM 截到买点当天(2025-07-14)的数据;只用训练段。一次性核对用,不入库。
"""
import sys
import numpy as np
import pandas as pd
from chart_workflow.config import load_config
from chart_workflow.panel import read_stock
from path2.atoms.breakout import BODetector
from path2.atoms.distribution import DistributionDetector

SYM, R0, R1, BUY = "QMMM", "2025-02-28", "2025-07-14", "2025-07-14"
cfg = load_config()
df = read_stock(cfg, SYM)
df = df[df.index <= pd.Timestamp(BUY)].copy()
win = df.reset_index()
win.columns = [c.lower() for c in win.columns]
dates = pd.to_datetime(win["date"])
lo = int(dates.searchsorted(pd.Timestamp(R0)))
print("bars", len(win), "range idx from", lo)

for meas in ("high", "close"):
    det = BODetector(peak_measure=meas, breakout_measure=meas)
    pks, bos = {}, []
    for kind, ev in det.detect(win):
        if kind == "pk":
            pks[id(ev)] = ev
        else:
            bos.append(ev)
    print(f"\n== 口径 {meas}")
    for ev in pks.values():
        pi = getattr(ev, "peak_idx", ev.start_idx)
        if pi >= lo:
            print(f"  峰 {dates[pi].date()} price={ev.price:.3f} orig={getattr(ev,'original_price',None)}")
    for b in bos:
        if b.start_idx >= lo:
            broken = [f"{dates[getattr(p,'peak_idx',p.start_idx)].date()}@{p.price:.3f}" for p in b.broken_refs]
            print(f"  突破 {dates[b.start_idx].date()} 价={win[meas][b.start_idx]:.3f} 量比={b.vol_ratio:.1f} 突破的峰={broken}")

vol = win["volume"]
base = vol.rolling(63, min_periods=63).mean().shift(1)
vm = (vol / base)
print("\n买点前 15 天量倍数:")
for i in range(len(win) - 15, len(win)):
    print(f"  {dates[i].date()} close={win['close'][i]:.3f} 量倍数={vm[i]:.1f}")
