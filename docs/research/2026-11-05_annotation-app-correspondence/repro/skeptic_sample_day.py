"""skeptic 临时脚本:每个正样本日的当天形态——当日涨幅、收阳否、收盘相对阶跃后最高价/新平台最低价的位置。只读。"""
import pandas as pd
from common import load_state, load_win, d2i, i2d, EXCLUDED_SAMPLES
st, fname = load_state()
STEP = {"CRNC": "2024-11-21", "GEVO": "2024-09-13", "INDO": "2022-01-18", "QBTS": "2024-11-07", "RGTI": "2024-11-25", "SMX": "2025-11-28"}
for c in st["charts"]:
    sym = c["symbol"]; w = load_win(sym)
    k = d2i(w, STEP[sym])
    for s in sorted(c["samples"], key=lambda s: s["date"]):
        if (sym, s["date"]) in EXCLUDED_SAMPLES: continue
        i = d2i(w, s["date"])
        o, h, l, cl = (w[x].iloc[i] for x in ("open", "high", "low", "close"))
        prev = w["close"].iloc[i - 1]
        post = w.iloc[k:i + 1]
        hi_after = post["high"].max(); lo_after = post["low"].min()
        pre_step_close = w["close"].iloc[k - 1]
        print(f"{sym} {s['date']} chg={cl/prev-1:+.1%} {'阳' if cl>o else '阴'} "
              f"close/阶跃后最高={cl/hi_after:.2f} close/阶跃后最低={cl/lo_after:.2f} close/阶跃前收={cl/pre_step_close:.2f} 距阶跃{i-k}根")

print("--- 基线:同一张图阶跃后第 1~20 根里,涨幅>=3% 的天、收阳的天各占多少 ---")
tot = up3 = yang = 0
for sym, sd in STEP.items():
    w = load_win(sym); k = d2i(w, sd)
    seg = w.iloc[k + 1:k + 21]
    chg = seg["close"].values / w["close"].iloc[k:k + 20].values - 1
    n = len(seg); a = int((chg >= 0.03).sum()); b = int((seg["close"] > seg["open"]).sum())
    tot += n; up3 += a; yang += b
    print(f"{sym}: n={n} 涨>=3%={a} 收阳={b}")
print(f"合计 n={tot} 涨>=3% 占 {up3/tot:.0%}  收阳占 {yang/tot:.0%}")
