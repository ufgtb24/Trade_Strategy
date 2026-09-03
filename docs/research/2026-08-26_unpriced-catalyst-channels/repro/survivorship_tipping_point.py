"""
幸存者偏差「临界点分析」的可执行模板（§4-2 强制项）。
问题：退市票按构造缺失。若缺失质量全部落在 treated 组、fr = 退市典型值，
      需要多大的缺失比例才能把「CI 不跨 0」翻成「跨 0」？
本脚本用 §4-4c 的 pos 分组（Δ=+0.420, CI[+0.125,+0.900]）做 worked example，
各支流照抄此函数，把 (a, b) 换成自己的两组 fr 即可。
"""
import json, pickle, sys, numpy as np, pandas as pd
sys.path.insert(0, ".")
PKL = "/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls/{}.pkl"
rows = [r for r in json.load(open(
  "docs/research/2026-08-16_news-sentiment-path2-integration/repro/full_metrics_20260816-193657.json"))
  if r.get("fr_recalc") is not None]
rec = []
for r in rows:
    with open(PKL.format(r["symbol"]), "rb") as f: d = pickle.load(f)
    t = pd.Timestamp(r["buy_date"])
    if t not in d.index: continue
    i = d.index.get_loc(t)
    if i < 25 or i + 40 >= len(d): continue
    c = float(d["close"].iloc[i]); hp = float(d["high"].iloc[i-20:i+1].max())
    rec.append(dict(fr=r["fr_recalc"], pos=c/hp))
df = pd.DataFrame(rec); df["pbin"] = pd.qcut(df.pos, 3, labels=["深回撤","中","贴近高点"])
a = df[df.pbin == "贴近高点"].fr.values   # treated（结论有利的一组）
b = df[df.pbin == "深回撤"].fr.values     # control
rng = np.random.default_rng(42); NB = 10000

def ci(x, y):
    d = (np.median(rng.choice(x, (NB, len(x)), True), axis=1)
         - np.median(rng.choice(y, (NB, len(y)), True), axis=1))
    return np.median(x) - np.median(y), *np.percentile(d, [2.5, 97.5])

def tipping(a, b, fr_missing=-0.90, step=0.01, cap=1.50):
    """往 treated 组按比例注入缺失的退市票（fr=fr_missing），找 CI 开始跨 0 的比例。"""
    f = 0.0
    while f <= cap:
        n_add = int(round(len(a) * f))
        aa = np.concatenate([a, np.full(n_add, fr_missing)]) if n_add else a
        pt, lo, hi = ci(aa, b)
        if lo < 0 < hi:
            return f, pt, lo, hi
        f += step
    return None, *ci(a, b)

pt, lo, hi = ci(a, b)
print(f"[worked example · pos 分组] treated n={len(a)}, control n={len(b)}")
print(f"  原始: Δ = {pt:+.3f}  CI [{lo:+.3f}, {hi:+.3f}]")
print(f"\n[临界点] 往 treated 注入 fr = 退市典型值的缺失票，直到 CI 跨 0:")
for frm in (-0.90, -0.70, -0.50):
    f, p2, l2, h2 = tipping(a, b, frm)
    if f is None:
        print(f"  缺失票 fr={frm:+.2f}: 注入到 {150}% 仍不跨 0 ⟹ 对幸存者偏差极稳健")
    else:
        print(f"  缺失票 fr={frm:+.2f}: 临界比例 = **{f*100:.0f}%**（相对 treated 现有规模）"
              f" → 此时 Δ={p2:+.3f} CI [{l2:+.3f}, {h2:+.3f}]")
print("""
[判读标准（§4-2 强制项）]
  临界比例 < 10%  ⟹ 结论对幸存者偏差不稳，不得接入
  10% ~ 30%       ⟹ 需外部退市率证据佐证（该票池的年化退市率 × 持有期）
  > 30%           ⟹ 对幸存者偏差稳健，可报
""")
