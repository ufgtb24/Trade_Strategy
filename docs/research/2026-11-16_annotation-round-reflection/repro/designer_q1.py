"""一次性（应 designer 要求）：「新平台里有比阶跃更猛的东西」的几种口径，在 16 张样本 / 10 处反馈 / 192 个 hit 上的报出数。
视野与 trace_numbers.py 相同（一致样本取最近买点日的最长前缀 hit；没买到的取会话诊断的候选；反馈取范围内最长前缀 hit）。
口径：
  A 新平台里有一根收盘涨幅 > 阶跃最大单根涨幅
  B1 新平台最高价 > 阶跃末根最高价 × 1.0
  B2 新平台最高价 > 阶跃末根最高价 × 1.2
  C1 新平台最高价 > 阶跃段最高价 × 1.0
  C2 新平台最高价 > 阶跃段最高价 × 1.2
"""
import io, contextlib
import numpy as np
with contextlib.redirect_stdout(io.StringIO()):
    import trace_numbers as T
import signals as S

def flags(sym, ev):
    day, o, h, cl, _ = S.arrays(sym)
    s, e, t = ev["s"], ev["e"], ev["t"]
    r = np.concatenate([[np.nan], np.log(cl[1:] / cl[:-1])])
    nw = range(e + 1, t)
    mh = max(h[i] for i in nw)
    return {"A": any(r[i] > ev["step_max_ret"] for i in nw),
            "B1": mh > h[e] * 1.0, "B2": mh > h[e] * 1.2,
            "C1": mh > h[s:e + 1].max() * 1.0, "C2": mh > h[s:e + 1].max() * 1.2}

NAMED_SHORT = {"QBTS 2024-11-29", "QBTS 2024-12-03", "KULR 2024-11-29", "KULR 2024-12-16"}
for vname in ("样本16", "反馈10", "全部hit(最长前缀)"):
    items = T.V[vname]
    print(f"== {vname} ==")
    for k in ("A", "B1", "B2", "C1", "C2"):
        fire = [(n, s, l) for n, s, l in items if l and any(flags(s, e)[k] for e in l)]
        names = [n for n, _, _ in fire]
        named = [n for n, s, l in fire if any(T.sig(s, e)["named"] for e in l)]
        diff = [n for n, s, l in fire if any(T.sig(s, e)["diff"] for e in l)]
        out = f"  {k}: 报出 {len(fire)}，其中用户点名 {len(named)}，与新认法不一致 {len(diff)}"
        if not vname.startswith("全部"):
            out += f"\n     报出 {names}\n     点名 {named}"
            if vname == "样本16":
                out += f"\n     漏掉的「阶跃切短了」点名样本 {sorted(NAMED_SHORT - set(names))}"
        print(out)
