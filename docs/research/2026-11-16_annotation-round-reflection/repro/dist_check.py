"""一次性：公共派发 detector（path2/atoms/distribution.py，默认参数）在 i-pc-2 / i-pc-3 / f-pc-90 各处，
以及正样本阶跃到样本日之间，各报出几根。窗口：该处所在 hit 的阶跃起点到反馈止日（只看当天及以前）。"""
import pickle
import pandas as pd
from path2.atoms.distribution import DistributionDetector
import signals as S

def dist_days(sym):
    day, o, h, cl, _ = S.arrays(sym)
    b = S.C[sym]["bars"]
    df = pd.DataFrame(b, columns=["open", "high", "low", "close", "volume"])
    return {day[e.start_idx] for e in DistributionDetector().detect(df)}

PLACES = [("f-pc-94 i-pc-2", "IXHL", "2025-07-14", "2025-07-25"),
          ("f-pc-95 i-pc-2", "LUMN", "2024-07-16", "2024-10-02"),
          ("f-pc-104 i-pc-3", "CAPR", "2025-12-03", "2025-12-05"),
          ("f-pc-101 i-pc-3", "IZM", "2024-04-08", "2024-04-16"),
          ("f-pc-93 i-pc-3", "TNXP", "2024-12-16", "2024-12-30"),
          ("f-pc-90", "IXHL", "2025-07-14", "2025-09-26")]
for name, sym, a, b in PLACES:
    dd = sorted(d for d in dist_days(sym) if a <= d <= b)
    print(name, sym, a, b, "派发根:", dd)
print("== 正样本：阶跃起点前 5 根到样本日 ==")
for sym, d, ok, *_ in S.SAMPLES:
    day = S.arrays(sym)[0]
    i = day.index(d)
    dd = sorted(x for x in dist_days(sym) if day[max(0, i - 25)] <= x <= d)
    print(" ", sym, d, "前 25 根内派发根:", dd)
