"""一次性：打印某只股票某段日期里旧版（或新版）app 的 hit 各段起止与 K 线。

用法：uv run python show.py old|new SYM 起 止 [--cands]
"""
import pickle
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent


def main():
    which, sym, a, b = sys.argv[1:5]
    cands = "--cands" in sys.argv
    c = pickle.load(open(HERE / f"cache_{which}.pkl", "rb"))[sym]
    day, bars, evs = c["day"], c["bars"], c["events"]
    rows = [e for e in evs if a <= day[e["t"]] <= b and (cands or e["hit"])]
    rows.sort(key=lambda e: (e["t"], e["s"], e["e"]))
    for e in rows:
        s, ee, t = e["s"], e["e"], e["t"]
        print(f"t={day[t]} hit={int(e['hit'])} old={day[e['old_s']]}..{day[s-1]} step={day[s]}..{day[ee]}"
              f" ({e['step_bars']}根 rise={e['step_rise']:.2f} maxr={e['step_max_ret']:.3f})"
              f" new={day[ee+1]}..{day[t-1]} keep={e.get('keep_ratio', float('nan')):.2f}"
              f" calm={e.get('calm_ratio', float('nan')):.2f} vs_high={e.get('vs_high', float('nan')):.3f}")
    if "--bars" in sys.argv:
        i0 = max(0, day.index(next(d for d in day if d >= a)) - 5)
        i1 = max(i for i, d in enumerate(day) if d <= b)
        cl = bars[:, 3]
        for i in range(i0, i1 + 1):
            o, h, l, cc, v = bars[i]
            r = np.log(cc / cl[i - 1]) if i > 0 else np.nan
            rh = np.log(h / cl[i - 1]) if i > 0 else np.nan
            print(f"  {day[i]} o={o:.3f} h={h:.3f} l={l:.3f} c={cc:.3f} r={r:+.3f} r_high={rh:+.3f} v={v:.0f}")


if __name__ == "__main__":
    main()
