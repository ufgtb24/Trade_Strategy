"""
⚠ 本脚本算的是 **H0-uniform**（财报均匀落在全窗），**已被 H0-recent 取代**。
「最近一次」财报只能落在 [buy_date − P, buy_date]（P = 该票实际申报间隔），全窗均匀会高估旱期基率。
正确版见 FinChannel 的 repro/analyze_baserate_and_g.py（旱期 85.0% / burst 9.8%）。
本脚本保留作**保守上界与敏感性对照**：主结论（77.1% 不构成证据）在两个 null 下都成立。

红队 Phase 2：对 FinChannel §6.1b「77.1% 的财报落在旱期内」做基率对照。

问题：旱期被 first_drought>=40 硬闸定义成长段（中位 66 bar），burst/回踩只有几根 bar，
      旱期本来就占掉时间轴绝大部分 ⟹ 不给基率，77.1% 只是基率复读（同 win_rate 的失效模式）。
方法：用 FinChannel 已有的 filing_in_drought_*.json，算各段占 (drought_start → buy_date)
      全窗的时间比例 = 财报日均匀随机落点时各段的期望命中率，与实测比。
"""
import json, glob, datetime as dt, numpy as np
from math import comb
src = sorted(glob.glob("docs/research/2026-08-26_unpriced-catalyst-channels/repro/filing_in_drought_*.json"))[-1]
d = json.load(open(src)); rows = d["rows"]
print(f"[源] {src}\n[实测 counts] {d['counts']}")
D = lambda s: dt.date.fromisoformat(s)
fd, fb, ft, span = [], [], [], []
for r in rows:
    ds, bs, be, buy = D(r["drought_start"]), D(r["burst_start"]), D(r["burst_end"]), D(r["buy_date"])
    tot = (buy - ds).days
    if tot <= 0: continue
    fd.append((bs - ds).days / tot); fb.append(max((be - bs).days, 0) / tot)
    ft.append(max((buy - be).days, 0) / tot); span.append(tot)
fd, fb, ft = map(np.array, (fd, fb, ft))
n = len(rows)
print(f"\n[全窗长度] median {np.median(span):.0f} 自然日  (n={len(span)})")
print(f"[各段时间占比 = 均匀随机落点的基率]  旱期 {fd.mean()*100:.1f}% · "
      f"burst {fb.mean()*100:.1f}% · 回踩 {ft.mean()*100:.1f}%")
print(f"\n{'段':<10}{'实测':>10}{'基率':>9}{'lift':>7}{'单尾二项p':>11}")
for name, key, p0 in (("旱期内", "旱期内", fd.mean()),
                      ("burst 期内", "burst 期内", fb.mean()),
                      ("回踩期内", "回踩期内", ft.mean())):
    obs = d["counts"][key]
    pv = sum(comb(n, i) * p0**i * (1 - p0)**(n - i) for i in range(obs, n + 1))
    print(f"{name:<10}{obs}/{n}={obs/n*100:5.1f}%{p0*100:8.1f}%{(obs/n)/p0:7.2f}{pv:11.4f}")
print("""
[判读]
  旱期实测 **低于** 基率 ⟹ 「77.1% 落在旱期」不构成「bb 编码了利好未兑现」的证据。
  burst 期实测 **高于** 基率 ×2.1（p≈0.043，单一未校正检验、n=48，不构成证据），
  ⟹ 「burst 常常就是对财报的反应」这条担忧 **未被推翻**。
  站得住的只有：first_drought>=40 使「价格没动」成为形态的定义性推论（同义反复），
  且因 B 在 bb 内无变异 ⟹ **无法在 bb 内估计 B 的贡献** ⟹ 支持全宇宙路线。
""")
