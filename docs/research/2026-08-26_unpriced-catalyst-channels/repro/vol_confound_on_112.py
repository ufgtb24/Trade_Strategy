"""
陷阱 4-4 的实测：在上一轮的 112 行 bb 买点上，波动率对 fr 的解释力有多大？
这设定了任何新支流「增量」的门槛——新变量必须在控制波动率之后仍有解释力。
只读主 worktree 的 pkl（本 worktree 为空），不写不改。
"""
import json, pickle, numpy as np, pandas as pd, sys
sys.path.insert(0, ".")
from path2.calc.atr import rolling_atr_pct_nanmedian

PKL = "/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls/{}.pkl"
rows = [r for r in json.load(open(
  "docs/research/2026-08-16_news-sentiment-path2-integration/repro/full_metrics_20260816-193657.json"))
  if r.get("fr_recalc") is not None]

rec = []
miss = 0
for r in rows:
    try:
        with open(PKL.format(r["symbol"]), "rb") as f: d = pickle.load(f)
    except Exception:
        miss += 1; continue
    t = pd.Timestamp(r["buy_date"])
    if t not in d.index: miss += 1; continue
    i = d.index.get_loc(t)
    m = rolling_atr_pct_nanmedian(d["high"], d["low"], d["close"], 20).iloc[i]
    if not np.isfinite(m): miss += 1; continue
    close = float(d["close"].iloc[i]); vol = float(d["volume"].iloc[i])
    rec.append(dict(sym=r["symbol"], fr=r["fr_recalc"], atr=float(m),
                    close=close, dv=close*vol, fp6=r["fp"]["6"]))
print(f"[对齐] 成功 {len(rec)} / {len(rows)}，缺失 {miss}")
df = pd.DataFrame(rec)
print(f"[ATR%(20)] median={df.atr.median():.4f} q10={df.atr.quantile(.1):.4f} q90={df.atr.quantile(.9):.4f}")
print(f"[成交额]   median=${df.dv.median():,.0f}  q10=${df.dv.quantile(.1):,.0f} q90=${df.dv.quantile(.9):,.0f}")
print(f"[收盘价]   median=${df.close.median():.2f} (微盘占比: close<$5 = {(df.close<5).mean()*100:.1f}%)")

ly = np.log1p(df.fr.clip(lower=-0.99)); la = np.log(df.atr)
print(f"\n=== 波动率 → fr 的解释力 ===")
print(f"  Spearman(ATR%, fr)      = {df.atr.corr(df.fr, method='spearman'):+.3f}")
print(f"  Pearson(log ATR%, log1p fr) = {np.corrcoef(la, ly)[0,1]:+.3f}   → R² = {np.corrcoef(la,ly)[0,1]**2:.3f}")
print(f"  Spearman(成交额, fr)    = {df.dv.corr(df.fr, method='spearman'):+.3f}")
print(f"  Spearman(收盘价, fr)    = {df.close.corr(df.fr, method='spearman'):+.3f}")

print(f"\n=== ATR% 三分位内的 fr median（若单调，波动率是主混杂）===")
df["bin"] = pd.qcut(df.atr, 3, labels=["低波动", "中波动", "高波动"])
g = df.groupby("bin", observed=True).agg(n=("fr","size"), fr_median=("fr","median"),
                                          atr_median=("atr","median"))
print(g.to_string())
det = df[df.fp6.isin(["up","down"])]
gg = det.groupby("bin", observed=True).apply(lambda x: (x.fp6=="up").mean(), include_groups=False)
gn = det.groupby("bin", observed=True).size()
print("\n=== ATR% 三分位内的 FPR_k6（阈值已按波动率归一，理应更平）===")
for b in gg.index: print(f"  {b}: FPR={gg[b]:.3f} (n判定={gn[b]})")

# --- 追加：低 vs 高波动三分位的 bootstrap CI（对照我算的 MDE） ---
rng = np.random.default_rng(42); NB = 10000
lo = df[df.bin == "低波动"].fr.values; hi = df[df.bin == "高波动"].fr.values
pt = np.median(lo) - np.median(hi)
b = (np.median(rng.choice(lo, (NB, len(lo)), True), axis=1)
     - np.median(rng.choice(hi, (NB, len(hi)), True), axis=1))
l, h = np.percentile(b, [2.5, 97.5])
print(f"\n=== 低波动 − 高波动 三分位 fr median 差 ===")
print(f"  点估计 = {pt:+.3f}   bootstrap 95% CI = [{l:+.3f}, {h:+.3f}]   跨0? {'是' if l<0<h else '否'}")
dlo = det[det.bin=="低波动"]; dhi = det[det.bin=="高波动"]
plo = (dlo.fp6=="up").values.astype(float); phi = (dhi.fp6=="up").values.astype(float)
bb_ = (rng.binomial(len(plo), plo.mean(), NB)/len(plo)
       - rng.binomial(len(phi), phi.mean(), NB)/len(phi))
l2, h2 = np.percentile(bb_, [2.5, 97.5])
print(f"  FPR_k6 差 = {plo.mean()-phi.mean():+.3f}  CI = [{l2:+.3f}, {h2:+.3f}]  跨0? {'是' if l2<0<h2 else '否'}")
# k=4,5 稳健性
for k in ("4","5"):
    dd = df.copy(); dd["fpk"] = [r["fp"][k] for r in rows]
    dd = dd[dd.fpk.isin(["up","down"])]
    a = (dd[dd.bin=="低波动"].fpk=="up").mean(); c = (dd[dd.bin=="高波动"].fpk=="up").mean()
    print(f"  FPR_k{k} 差 = {a-c:+.3f}  (低 {a:.3f} / 高 {c:.3f})")
