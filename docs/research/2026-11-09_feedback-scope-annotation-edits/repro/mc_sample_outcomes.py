"""method_critic: 第一轮正样本日之后 40 个交易日的最高涨幅与期末涨幅（只为说明第一轮标注本身就是看着后续走势挑的）。
行情只经 path2_web.data.read_bars 读训练段副本 datasets/pkls_until_20251231。"""
from path2_web.config import load_config
from path2_web.annotation.store import read_annotations
from path2_web.data import read_bars
import pandas as pd

st = read_annotations(load_config())["state"]
for ch in st["charts"]:
    if not ch["samples"]:
        continue
    df = read_bars("datasets/pkls_until_20251231", ch["symbol"])
    for s in ch["samples"]:
        d = pd.Timestamp(s["date"])
        i = df.index.searchsorted(d)
        c0 = df["close"].iloc[i]
        w = df.iloc[i + 1:i + 41]
        print(f'{ch["symbol"]:5s} {s["date"]} {s["judgment"]} bars_after={len(w):2d} '
              f'max_high/close0={w["high"].max()/c0:5.2f} close40/close0={w["close"].iloc[-1]/c0:5.2f}')
