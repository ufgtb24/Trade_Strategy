"""一次性：trace.md 用到的全部数字，一次出齐（旧版 app = 第 1 轮改之前）。

用法：uv run python numbers.py > numbers_old.txt
口径见 trace.md 附录。信号只用当天及以前的数据；「与新认法不一致」按 signals.new_def 粗算（新认法第 2、6 条，
不含第 4 条「停顿后续上」），只说明普遍度、不当真值；「用户点名」只认 next-round-step-definition.md 里
用户确认过的五次阶跃。
"""
import numpy as np
from collections import defaultdict
import signals as S

# 用户点名的阶跃（新认法下的整段，用户确认过）：hit 的旧版阶跃起点落在这段里就算点名
NAMED = {"QBTS": ("2024-11-20", "2024-11-25"), "IXHL": ("2025-07-14", "2025-07-24"),
         "KULR": [("2024-03-20", "2024-03-26"), ("2024-11-20", "2024-12-02")],
         "LUMN": ("2024-07-11", "2024-08-07")}

# 没买到的正样本：取会话实际诊断的那个候选（plan.md 第 3、4、10 条）
DIAG = {("KULR", "2024-04-01"): "2024-03-26", ("KULR", "2024-11-29"): "2024-11-25",
        ("KULR", "2024-12-16"): "2024-11-25", ("KULR", "2024-03-27"): None}


def named(sym, ev):
    day = S.arrays(sym)[0]
    ws = NAMED.get(sym)
    if ws is None:
        return False
    ws = ws if isinstance(ws, list) else [ws]
    return any(a <= day[ev["s"]] <= b for a, b in ws)


def longest(sym, evl):
    best = {}
    for ev in evl:
        k = (ev["t"], ev["s"])
        if k not in best or ev["e"] > best[k]["e"]:
            best[k] = ev
    return list(best.values())


def sig(sym, ev):
    g = S.sig(sym, ev)
    day, o, h, cl, _ = S.arrays(sym)
    s = ev["s"]
    s2 = s
    while s2 - 1 >= 1 and h[s2 - 1] > h[s2 - 2]:
        s2 -= 1
    g["start_mat"] = bool(s2 < s and cl[s - 1] / cl[s2 - 1] - 1 >= 0.10)
    g["diff"] = bool(g["true_end_material"] or g["start_mat"])
    g["named"] = named(sym, ev)
    return g


def views():
    samp = []
    for sym, d, ok, *_ in S.SAMPLES:
        day, o, h, cl, evs = S.arrays(sym)
        i = day.index(d)
        if (sym, d) in DIAG:
            sd = DIAG[(sym, d)]
            evl = [] if sd is None else [ev for ev in evs if ev["t"] == i and day[ev["s"]] == sd]
            evl = longest(sym, evl)
        else:
            hs = sorted([ev for ev in S.hits_of(sym) if abs(ev["t"] - i) <= S.POS_TOL], key=lambda ev: abs(ev["t"] - i))
            evl = longest(sym, [ev for ev in hs if ev["t"] == hs[0]["t"]])
        samp.append((f"{sym} {d}", sym, evl))
    fb = []
    for fid, iss, sym, a, b, mode, fam in S.FEEDBACK:
        day, o, h, cl, evs = S.arrays(sym)
        hs = [ev for ev in S.hits_of(sym) if a <= day[ev["t"]] <= b]
        if mode == "family":
            hs = [ev for ev in hs if day[ev["old_s"]] == fam] or hs
        fb.append((f"{fid} {sym} {a}", sym, longest(sym, hs)))
    allh = [(f"{sym} {S.arrays(sym)[0][ev['t']]}", sym, [ev]) for sym in S.C for ev in longest(sym, S.hits_of(sym))]
    return {"样本16": samp, "反馈10": fb, "全部hit(最长前缀)": allh}


SIGS = {"S1_close": "新平台里有一根收盘涨幅≥阶跃最猛一根",
        "S1_high": "新平台里有一根盘中涨幅≥阶跃最猛一根",
        "S1_top10": "新平台最高价比阶跃顶高10%以上",
        "keep_gt1": "keep_ratio>1（新平台最低收盘都在阶跃末根收盘之上）",
        "S2_close": "旧平台里有一根收盘涨幅≥阶跃最猛一根",
        "S2_prev_up": "阶跃前一根最高价抬高且收涨"}

V = views()
print("# 一、各信号在三个视野上的报出数")
for vname, items in V.items():
    print(f"\n## {vname}：{len(items)} 项；其中与新认法不一致 {sum(any(sig(s, e)['diff'] for e in l) for _, s, l in items)}，"
          f"用户点名 {sum(any(sig(s, e)['named'] for e in l) for _, s, l in items)}")
    for k, txt in SIGS.items():
        fire = [(n, s, l) for n, s, l in items if any(sig(s, e)[k] for e in l)]
        diff = [n for n, s, l in fire if any(sig(s, e)[k] and sig(s, e)["diff"] for e in l)]
        nm = [n for n, s, l in fire if any(sig(s, e)[k] and sig(s, e)["named"] for e in l)]
        miss_named = [n for n, s, l in items if any(sig(s, e)["named"] for e in l) and not any(sig(s, e)[k] for e in l)]
        line = f"- {k}（{txt}）：报出 {len(fire)}；其中与新认法不一致 {len(diff)}；用户点名 {len(nm)}；漏掉的用户点名 {len(miss_named)}"
        if not vname.startswith("全部"):
            line += f"\n    报出：{[n for n, _, _ in fire]}\n    漏掉的点名：{miss_named}"
        print(line)

print("\n# 二、前缀成族")
for sym in S.C:
    pass
tot_days = multi_days = tot_h = short_h = 0
per = defaultdict(lambda: [0, 0])
for sym in S.C:
    day, *_r, evs = S.arrays(sym)
    hs = S.hits_of(sym)
    seg_end = defaultdict(int)
    for ev in evs:
        seg_end[ev["s"]] = max(seg_end[ev["s"]], ev["e"])
    by = defaultdict(set)
    for ev in hs:
        by[(ev["t"], ev["s"])].add(ev["e"])
        tot_h += 1
        short_h += ev["e"] < seg_end[ev["s"]]
    days = defaultdict(int)
    for (t, s), es in by.items():
        days[t] = max(days[t], len(es))
    tot_days += len(days)
    m = sum(1 for k in days.values() if k >= 2)
    multi_days += m
    per[sym] = [len(days), m]
print(f"- 买点日 {tot_days}，同一段阶跃 ≥2 个前缀同天都买的 {multi_days}；hit {tot_h}，用的是短前缀的 {short_h}")
print("- 分股票（买点日, 多前缀同天）:", dict(per))
for vname in ("样本16", "反馈10"):
    out = []
    for n, sym, l in V[vname]:
        if not l:
            continue
        hs = S.hits_of(sym)
        k = max(len({h["e"] for h in hs if h["t"] == ev["t"] and h["s"] == ev["s"]}) for ev in l)
        if k >= 2:
            out.append(n)
    print(f"- {vname} 报出 {len(out)}：{out}")

print("\n# 三、框")
for sym, d, ok, box_s, bot_e in S.SAMPLES:
    day = S.arrays(sym)[0]
    l = [x for n, s, x in V["样本16"] if n == f"{sym} {d}"][0]
    if not l:
        print(f"- {sym} {d}：无候选"); continue
    ev = l[0]
    g = sig(sym, ev)
    a = f"站上新平台框起 {box_s} vs 旧平台起 {day[ev['old_s']]}（差 {S.i_gap(day, box_s, day[ev['old_s']])} 根）" if box_s else "无站上新平台框"
    b = (f"；底部平稳框止 {bot_e} vs 阶跃起 {day[ev['s']]}（差 {S.i_gap(day, bot_e, day[ev['s']])} 根），"
         f"新认法起 {g['s2e2'][0]}（差 {S.i_gap(day, bot_e, g['s2e2'][0])} 根）") if bot_e else ""
    print(f"- {sym} {d}：{a}{b}")
