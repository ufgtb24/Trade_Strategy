"""skeptic 临时脚本:全段口径(同 compare)下,每个正样本按 spec 6.2 的 match 判法(买点在样本日前后 3 根内,
或样本日落在买点 node 那段事件里)算 matched / unmatched;另数每只股票训练段里 app 的买入日总数。只读。"""
from common import load_state, load_win, d2i, i2d, EXCLUDED_SAMPLES
from path2_apps.new_step import dag_spec as app
p = app.load_params()
st, fname = load_state()
POS_TOL = 3
tot = m = 0
for c in st["charts"]:
    sym = c["symbol"]; w = load_win(sym)
    res = app.analyze(w, p)
    buys = set(); segs = set()
    for h in res.hits:
        for s in h.node_index["tb"].segments:
            segs.add((s.start_idx, s.end_idx))
            buys.update(range(s.start_idx, s.end_idx + 1))
    for s in sorted(c["samples"], key=lambda s: s["date"]):
        if (sym, s["date"]) in EXCLUDED_SAMPLES: continue
        i = d2i(w, s["date"])
        near = sorted(b - i for b in buys if abs(b - i) <= POS_TOL)
        ok = bool(near)
        tot += 1; m += ok
        print(f"{sym} {s['date']} {'matched' if ok else 'unmatched'} 最近买点偏移={near[:3]}")
    print(f"   {sym}: 训练段 app 买入日共 {len(buys)} 天,企稳段 {len(segs)} 段,hit {len(res.hits)} 个")
print(f"正样本 matched {m}/{tot}")

print("--- 基线:随便挑一天也算 matched 的比例(该天前后 3 根内有 app 买点) ---")
STEP = {"CRNC": "2024-11-21", "GEVO": "2024-09-13", "INDO": "2022-01-18", "QBTS": "2024-11-07", "RGTI": "2024-11-25", "SMX": "2025-11-28"}
head = app.eval_meta(p)["head_buffer_trading_days"]
ga = gn = pa = pn = 0
for sym, sd in STEP.items():
    w = load_win(sym); res = app.analyze(w, p)
    buys = set()
    for h in res.hits:
        for s in h.node_index["tb"].segments:
            buys.update(range(s.start_idx, s.end_idx + 1))
    cov = lambda i: any(abs(b - i) <= POS_TOL for b in buys)
    allidx = range(head, len(w))
    g = sum(cov(i) for i in allidx); ga += g; gn += len(allidx)
    k = d2i(w, sd); post = range(k + 1, min(k + 21, len(w)))
    pp = sum(cov(i) for i in post); pa += pp; pn += len(post)
    print(f"{sym}: 全段 {g}/{len(allidx)}={g/len(allidx):.0%}  阶跃后 1~20 根 {pp}/{len(post)}={pp/len(post):.0%}")
print(f"合计 全段 {ga/gn:.0%}  阶跃后 1~20 根 {pa/pn:.0%}")

print("--- 当天就买(偏移 0)的口径 ---")
ex = 0; pd0 = pn0 = 0
for c in st["charts"]:
    sym = c["symbol"]; w = load_win(sym); res = app.analyze(w, p)
    buys = set()
    for h in res.hits:
        for s in h.node_index["tb"].segments:
            buys.update(range(s.start_idx, s.end_idx + 1))
    for s in c["samples"]:
        if (sym, s["date"]) in EXCLUDED_SAMPLES: continue
        ex += d2i(w, s["date"]) in buys
    k = d2i(w, STEP[sym]); post = range(k + 1, min(k + 21, len(w)))
    pd0 += sum(i in buys for i in post); pn0 += len(post)
print(f"正样本当天就买 {ex}/10;阶跃后 1~20 根里买入日占 {pd0}/{pn0}={pd0/pn0:.0%}")
