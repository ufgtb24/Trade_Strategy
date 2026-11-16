"""一次性：把 signals.py 的各信号按「16 张样本 / 10 处反馈 / 全部 hit」三个视野汇总，并对「真问题」交叉。

用法：uv run python tabulate.py
样本：一致的取样本日 ±3 根内离得最近的买点 hit；相反的（没买到）取样本日当天全部候选，任一候选报出即算报出。
反馈：范围里（family 方式只取那一族）任一 hit 报出即算这一处报出。
真问题（近似，按用户谈定的新认法第 2、6 条；不含第 4 条「停顿后续上」）：
  end_mat  ＝新认法终点更晚，且多出来的几根把阶跃顶最高价抬高 10% 以上
  start_mat＝新认法起点更早，且挪进来的几根收盘累计涨 10% 以上
"""
import numpy as np
from collections import defaultdict
import signals as S

def extra(sym, ev):
    g = S.sig(sym, ev)
    day, o, h, cl, _ = S.arrays(sym)
    s, e = ev["s"], ev["e"]
    s2 = s
    while s2 - 1 >= 1 and h[s2 - 1] > h[s2 - 2]:
        s2 -= 1
    g["start_mat"] = s2 < s and cl[s - 1] / cl[s2 - 1] - 1 >= 0.10
    g["end_mat"] = g["true_end_material"]
    return g

SIGS = ["S1_top10", "S1_high", "S1_close", "keep_gt1", "S2_close", "S2_prev_up"]
TRUTH = {"S1_top10": "end_mat", "S1_high": "end_mat", "S1_close": "end_mat", "keep_gt1": "end_mat",
         "S2_close": "start_or_end", "S2_prev_up": "start_mat"}

def truth_of(g, k):
    t = TRUTH[k]
    if t == "start_or_end":
        return g["start_mat"] or g["end_mat"]
    return g[t]

def longest(sym, evl):
    """同一天同一段阶跃的几个前缀只留最长的那个（把「前缀成族」和「按收盘并入」两个问题分开量）。"""
    best = {}
    for ev in evl:
        k = (ev["t"], ev["s"])
        if k not in best or ev["e"] > best[k]["e"]:
            best[k] = ev
    return list(best.values())

def views(only_longest=True):
    samp = []
    for sym, d, ok, *_ in S.SAMPLES:
        day, o, h, cl, evs = S.arrays(sym)
        i = day.index(d)
        hs = sorted([ev for ev in S.hits_of(sym) if abs(ev["t"] - i) <= S.POS_TOL], key=lambda ev: abs(ev["t"] - i))
        if hs:
            t0 = hs[0]["t"]
            evl = [ev for ev in hs if ev["t"] == t0]
        else:
            evl = [ev for ev in evs if ev["t"] == i]
        if only_longest:
            evl = longest(sym, evl)
        samp.append((f"{sym} {d}", sym, evl))
    fb = []
    for fid, iss, sym, a, b, mode, fam in S.FEEDBACK:
        day, o, h, cl, evs = S.arrays(sym)
        hs = [ev for ev in S.hits_of(sym) if a <= day[ev["t"]] <= b]
        if mode == "family":
            hs = [ev for ev in hs if day[ev["old_s"]] == fam] or hs
        if only_longest:
            hs = longest(sym, hs)
        fb.append((f"{fid} {sym} {a}", sym, hs))
    allh = [(f"{sym} {S.arrays(sym)[0][ev['t']]}", sym, [ev]) for sym in S.C
            for ev in (longest(sym, S.hits_of(sym)) if only_longest else S.hits_of(sym))]
    return {"样本16": samp, "反馈10": fb, "全部hit": allh}

if __name__ == "__main__":
  for vname, items in views().items():
      print(f"== {vname}（{len(items)}）==")
      truth_cnt = defaultdict(int)
      for k in SIGS:
          fire, tp, names = 0, 0, []
          for name, sym, evl in items:
              gs = [extra(sym, ev) for ev in evl]
              if any(g[k] for g in gs):
                  fire += 1
                  if any(g[k] and truth_of(g, k) for g in gs):
                      tp += 1
                      names.append(name)
                  else:
                      names.append(name + "(误)")
          print(f"  {k}: 报出 {fire}，其中真问题 {tp}" + (f"  {names}" if vname != "全部hit" else ""))
      for t in ("end_mat", "start_mat"):
          n = sum(any(extra(sym, ev)[t] for ev in evl) for _, sym, evl in items)
          print(f"  [真问题总数] {t}: {n}")
