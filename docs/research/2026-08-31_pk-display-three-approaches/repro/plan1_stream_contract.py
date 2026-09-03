"""pk 流的协议可行性检查 + C1 最小合成复现。

A) 单调性:pk 流按登记顺序,peak bar 是否非降(决定 run() 的 end_idx 升序检查能否过、
   以及 PeakEvent 能否是"钉在峰那根"的点事件)。
B) 因果延迟:reg_idx - index 的分布(点事件把 confirm_idx 钉在 peak bar 会声称多少前瞻)。
C) C1 最小合成复现:构造一根跳空阴/阳线使 breakout_measure(high) > peak_measure(close),
   证明"同位重登记"必须 bm>pm 才可能发生。
"""
from __future__ import annotations

import pickle
import random
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[3]))

from plan1_prototype import CensusBO, PeakRegistrar   # noqa: E402
from path2_web.data import slice_window               # noqa: E402

PKL = Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls")
BASE = dict(total_window=20, min_side_bars=6, min_relative_height=0.2,
            exceed_threshold=0.003, peak_supersede_threshold=0.01,
            vol_baseline_period=63)


def part_ab(n=60):
    files = sorted(PKL.glob("*.pkl"))
    random.Random(7).shuffle(files)
    delays, nonmono, npk, done = [], 0, 0, 0
    for f in files:
        if done >= n:
            break
        try:
            with open(f, "rb") as fh:
                raw = pickle.load(fh)
            if not isinstance(raw, pd.DataFrame):
                continue
            w = slice_window(raw, "2021-01-01", "2026-03-08")
        except Exception:
            continue
        if len(w) < 400:
            continue
        done += 1
        for pm, bm in [("high", "close"), ("close", "high")]:
            kw = dict(BASE, peak_measure=pm, breakout_measure=bm)
            ref = CensusBO(**kw)
            list(ref.detect(w))
            idxs = [r[1] for r in ref.registered]     # 现状登记顺序的 peak bar
            npk += len(idxs)
            nonmono += sum(1 for a, b in zip(idxs, idxs[1:]) if b < a)
            delays += [r[0] - r[1] for r in ref.registered]
    d = np.array(delays)
    print(f"A) 现状登记序列共 {npk} 个 pk(60 股 × 2 象限);peak bar 逆序出现次数 = {nonmono}")
    print(f"B) 因果延迟 reg_idx - peak_idx:min={d.min()} p50={np.percentile(d,50):.0f} "
          f"p95={np.percentile(d,95):.0f} max={d.max()}  (min_side_bars=6 ⇒ 理论下界 7)")


def part_c():
    """构造:缓升造出 close 口径的峰(bar26,close=128),此后回落到 120 长期横盘 ——
    使 bar26 在 [34,40] 这几根上仍是窗口 argmax 且侧翼合格。
    再插两根 high 跳空长上影(bar36 / bar39):high 远超峰、close 仍在峰下。
      bar36:大幅突破 → 现状把 pk 移除 → bar37 同位重登记(纯 peak 域不会)
      bar39:再次突破那个"复活"的峰 → 现状多出一个 bo,方案① 没有。
    这就是 C1 的完整机制;把 breakout_measure 降到 ⪯ peak_measure 后立即消失。"""
    n = 60
    close = [100.0] * n
    for i in range(20, 27):
        close[i] = 100.0 + (i - 19) * 4.0     # bar26 = 128
    for i in range(27, n):
        close[i] = 120.0
    high = list(close)
    low = [c * 0.98 for c in close]
    open_ = [100.0] + close[:-1]
    for spike in (36, 39):
        high[spike] = 128.0 * 1.30            # 盘中冲高 30%,远超 supersede 阈值
        low[spike] = 118.0
        open_[spike] = 120.0
        close[spike] = 120.0                  # 收盘收回峰下 ⇒ close 口径不成新峰
    df = pd.DataFrame(dict(open=open_, high=high, low=low, close=close,
                           volume=[1e6] * n))
    for pm, bm in [("close", "high"), ("close", "close"), ("high", "high")]:
        kw = dict(BASE, peak_measure=pm, breakout_measure=bm, min_relative_height=0.10)
        ref = CensusBO(**kw)
        list(ref.detect(df))
        reg = [(r[1], r[0]) for r in ref.registered]
        pure = [(p.index, p.reg_idx) for p in PeakRegistrar(**kw).detect(df)]
        dup = len(reg) - len({i for i, _ in reg})
        print(f"C) peak={pm:6s} breakout={bm:6s}  现状登记(peak_bar,reg_bar)={reg}")
        print(f"            纯域登记={pure}  同位重登记={dup}  "
              f"现状bo={[b[0] for b in ref.bos]}")


if __name__ == "__main__":
    part_ab(int(sys.argv[1]) if len(sys.argv) > 1 else 60)
    part_c()
