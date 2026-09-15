"""用 SSoT 参数(params.yaml)重跑 first_drought 语义修复的影响面。

此前用 Params.default()(dataclass 默认)测得「0 match 增量」,但 dataclass 默认与
yaml 全面分叉(bo.min_relative_height 0.05 vs 0.2、breakout_measure high vs close、
burst 阈值 20/4/8.0/125 vs 40/3/3/60),那个结论不适用于现役口径。
"""
import dataclasses, glob, random, sys
import pandas as pd

sys.path.insert(0, "/home/yu/PycharmProjects/Trade_Strategy")
import path2.atoms.breakout as B
import path2_apps.bb_v1 as app
from path2_apps.bb_v1.params import load_params

N = int(sys.argv[1]) if len(sys.argv) > 1 else 800
START, END = "2024-01-01", "2026-01-01"
RATIO = 365 / 252
p = load_params()
HB = max(p.bo.vol_baseline_period, p.burst.vol_baseline_period, p.tb.vol_window, p.bo.total_window)
buf_start = (pd.Timestamp(START) - pd.Timedelta(days=round(HB * RATIO))).date()

files = sorted(glob.glob("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls/*.pkl"))
random.Random(0).shuffle(files)
dfs = {}
for f in files[:N]:
    try:
        df = pd.read_pickle(f)
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
        df = df.loc[str(buf_start):END]
        df.columns = [c.lower() for c in df.columns]
        if len(df) > 60:
            dfs[f.rsplit("/", 1)[-1][:-4]] = df.reset_index(drop=True)
    except Exception:
        pass
print(f"SSoT 参数 first_drought>={p.burst.first_drought_min} head_buffer={HB} 可用股票 {len(dfs)}")

_orig = B.BurstDetector._make_burst
def _legacy(self, seg, vol):
    ev = _orig(self, seg, vol)
    return dataclasses.replace(ev, first_drought=(seg[0].drought if seg[0].drought is not None else 0))

def scan(tag):
    n, hit = 0, 0
    for sym, df in dfs.items():
        try:
            m = len(app.analyze(df, p).matches)
        except Exception:
            continue
        n += m; hit += (m > 0)
    print(f"{tag}: match={n} 命中股票={hit}/{len(dfs)}")
    return n, hit

B.BurstDetector._make_burst = _legacy
old = scan("旧口径(None→0)")
B.BurstDetector._make_burst = _orig
new = scan("新口径(drought_floor)")
print(f"\n增量: match {old[0]} → {new[0]} ({new[0]-old[0]:+d}), 命中股票 {old[1]} → {new[1]} ({new[1]-old[1]:+d})")
