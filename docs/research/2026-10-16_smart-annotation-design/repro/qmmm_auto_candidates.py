"""一次性核对:QMMM 第一张标注里,哪些信息现有 detector 能自动算出来给用户确认。

只读训练段(截到用户点的买点 2025-07-14 收盘,即「当时能知道的」),不读 2026 年。
用法:uv run python docs/research/2026-10-16_smart-annotation-design/repro/qmmm_auto_candidates.py
"""
import pandas as pd

from chart_workflow.config import load_config
from chart_workflow.panel import read_stock
from path2.atoms.breakout import BODetector
from path2.atoms.distribution import DistributionDetector
from path2.atoms.trend import TrendSegmentDetector
from path2.calc.volume import calculate_vol_ratio

SYM, R0, BUY = "QMMM", "2025-02-28", "2025-07-14"
cfg = load_config()
df = read_stock(cfg, SYM)
df = df[df.index <= pd.Timestamp(BUY)]
assert df.index.max() <= pd.Timestamp("2025-12-31")
d = lambda i: df.index[i].strftime("%Y-%m-%d")
lo = df.index.get_indexer([pd.Timestamp(R0)], method="bfill")[0]

for pm, bm in [("high", "high"), ("close", "close"), ("high", "close")]:
    det = BODetector(peak_measure=pm, breakout_measure=bm)
    pks, bos = [], []
    for item in det.detect(df):
        kind, ev = item if isinstance(item, tuple) else (type(item).__name__, item)
        (pks if kind == "pk" else bos).append(ev)
    print(f"\n== 峰按 {pm} / 突破按 {bm} ==")
    for p in pks:
        if p.peak_idx >= lo - 30:
            print(f"  峰 pk{p.pk_id}: 峰日 {d(p.peak_idx)} 登记日 {d(p.start_idx)} 峰价 {p.price:.3f}")
    for b in bos:
        if b.start_idx >= lo:
            ids = [p.pk_id for p in b.broken_refs]
            print(f"  突破 {d(b.start_idx)}: 突破峰 {ids} 量比 {b.vol_ratio and round(b.vol_ratio,1)}")

print("\n== 派发(默认参数) ==")
for ev in DistributionDetector().detect(df):
    if ev.start_idx >= lo:
        print(f"  {d(ev.start_idx)} 量比 {ev.vol_ratio:.1f} 上影占比 {ev.upper_shadow_ratio:.2f}")

print("\n== 走势区段(默认参数) ==")
for ev in TrendSegmentDetector().detect(df):
    if ev.end_idx >= lo:
        print(f"  {d(ev.start_idx)}..{d(ev.end_idx)} {ev.regime} 确认日 {d(ev.confirm_idx)}")

vr = calculate_vol_ratio(df["volume"], 63) if True else None
print("\n== 买点前 25 天量比(当日量 / 前 63 日均量) ==")
print(pd.Series(vr.values if hasattr(vr, 'values') else vr, index=df.index).iloc[-25:].round(1).to_string())
print("\n== 买点前 10 天 OHLC ==")
print(df[["open", "high", "low", "close", "volume"]].iloc[-10:].round(3).to_string())

# 7/14 这根买点在现有 detector 里算什么:突破后回踩企稳段(tb)能不能认出来
from path2.atoms.throwback import ThrowbackDetector
for pm, bm in [("close", "close"), ("high", "high")]:
    det = BODetector(peak_measure=pm, breakout_measure=bm)
    bos = [ev for k, ev in det.detect(df) if k == "bo"]
    print(f"\n== 回踩企稳段(默认参数,突破按 {bm}) ==")
    for stop_bars in (2, 0):
        tbd = ThrowbackDetector(stop_confirm_bars=stop_bars)
        for tb in tbd.detect([b for b in bos if b.start_idx >= lo], df):
            for s in tb.segments:
                print(f"  stop_confirm_bars={stop_bars} 源突破 {tb.anchor_bo_id or '?'} 企稳段 {d(s.start_idx)}..{d(s.end_idx)} 退出 {s.outcome}")
