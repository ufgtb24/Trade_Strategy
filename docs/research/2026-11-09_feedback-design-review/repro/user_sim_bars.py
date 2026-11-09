"""user_sim 临时:打印几段阶跃前后的日 K,帮模拟用户做判断。不入库。"""
import sys
from path2_web.data import read_bars
D = "datasets/pkls_until_20251231"
for sym, a, b in [("CRNC","2024-09-25","2024-10-25"),("CRNC","2024-11-15","2025-01-03"),("CRNC","2024-12-27","2025-02-10"),
                  ("INDO","2022-01-05","2022-02-25"),("INDO","2022-02-18","2022-05-05"),("GEVO","2024-09-05","2024-10-18"),
                  ("RGTI","2024-11-20","2024-12-10"),("SMX","2025-11-20","2025-12-05")]:
    df = read_bars(D, sym)
    df = df[(df.index >= a) & (df.index <= b)]
    print("=====", sym, a, b)
    for _, r in df.iterrows():
        print(f"{str(_)[:10]} o={r['open']:.3f} h={r['high']:.3f} l={r['low']:.3f} c={r['close']:.3f} v={r['volume']:.0f}")
