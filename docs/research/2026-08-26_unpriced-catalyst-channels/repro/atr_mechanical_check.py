"""
自我证伪：§4-4b 的「低波动 → fr 高」是不是纯机械效应？
机械假说 H_mech：fr = max(high[t+1..t+40])/close[t] − 1。ATR% 高 ⟹ burst 刚发生、
close[t] 处在局部高位 ⟹ 分母偏大 ⟹ fr 天然更低。若成立，这条说的是「别在还在爆的时候买」，
属 tb 企稳判据问题，不是新通道。
判别：① close[t] 相对近期高点的位置 是否与 ATR% 正相关；
      ② 把分母换成 max(high[t-20..t])（近期高点）重算 fr，效应是否消失。
"""
import json, pickle, sys, numpy as np, pandas as pd
sys.path.insert(0, ".")
from path2.calc.atr import rolling_atr_pct_nanmedian
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
    m = rolling_atr_pct_nanmedian(d["high"], d["low"], d["close"], 20).iloc[i]
    if not np.isfinite(m): continue
    c = float(d["close"].iloc[i])
    hi_prev = float(d["high"].iloc[i-20:i+1].max())      # 近 21 日最高
    fwd_max = float(d["high"].iloc[i+1:i+41].max())
    rec.append(dict(sym=r["symbol"], atr=float(m), fr=r["fr_recalc"],
                    pos=c/hi_prev,                        # 买价在近期区间的相对位置
                    fr_from_hi=fwd_max/hi_prev - 1.0))    # 分母换成近期高点
df = pd.DataFrame(rec)
print(f"[对齐] {len(df)} 行")
df["bin"] = pd.qcut(df.atr, 3, labels=["低波动","中波动","高波动"])
print(f"\n① close[t]/近21日最高 与 ATR% 的关系（机械假说要求：ATR%高 ⟹ pos 高）")
print(f"   Spearman(ATR%, pos) = {df.atr.corr(df.pos, method='spearman'):+.3f}")
print(df.groupby("bin", observed=True).agg(n=("pos","size"), pos_median=("pos","median")).to_string())
print(f"\n② 把 fr 的分母从 close[t] 换成 max(high[t-20..t]) 后，效应是否消失")
g = df.groupby("bin", observed=True).agg(fr_close=("fr","median"), fr_from_hi=("fr_from_hi","median"))
print(g.to_string())
rng = np.random.default_rng(42); NB = 10000
for col, name in (("fr","原口径 fr(分母=close[t])"), ("fr_from_hi","改口径(分母=近期高点)")):
    lo = df[df.bin=="低波动"][col].values; hi = df[df.bin=="高波动"][col].values
    b = (np.median(rng.choice(lo,(NB,len(lo)),True),axis=1)
         - np.median(rng.choice(hi,(NB,len(hi)),True),axis=1))
    l,h = np.percentile(b,[2.5,97.5])
    print(f"   {name}: 低−高 = {np.median(lo)-np.median(hi):+.3f}  CI [{l:+.3f}, {h:+.3f}]  跨0? {'是' if l<0<h else '否'}")

# --- 追加：真正的驱动是 ATR% 还是 pos(买价距近期高点)？双向分层 ---
print("\n③ 驱动变量归属：pos 三分位 vs ATR% 三分位，以及交叉分层")
df["pbin"] = pd.qcut(df.pos, 3, labels=["深回撤","中","贴近高点"])
print(df.groupby("pbin", observed=True).agg(n=("fr","size"), pos_med=("pos","median"),
                                            fr_median=("fr","median")).to_string())
print("\n   交叉表 fr median（行=ATR%三分位, 列=pos三分位）:")
print(df.pivot_table(index="bin", columns="pbin", values="fr", aggfunc="median", observed=True).round(3).to_string())
print("\n   交叉表 n:")
print(df.pivot_table(index="bin", columns="pbin", values="fr", aggfunc="size", observed=True).to_string())
rng = np.random.default_rng(1); NB=10000
def ci(a,b):
    d=(np.median(rng.choice(a,(NB,len(a)),True),axis=1)-np.median(rng.choice(b,(NB,len(b)),True),axis=1))
    return np.median(a)-np.median(b), *np.percentile(d,[2.5,97.5])
p,l,h = ci(df[df.pbin=="贴近高点"].fr.values, df[df.pbin=="深回撤"].fr.values)
print(f"\n   pos: 贴近高点 − 深回撤 = {p:+.3f} CI [{l:+.3f},{h:+.3f}] 跨0? {'是' if l<0<h else '否'}")
# 在 pos 中位以上/以下 子样本内，ATR% 效应是否仍在
for lab, sub in (("pos 高半(贴近高点)", df[df.pos>=df.pos.median()]), ("pos 低半(深回撤)", df[df.pos<df.pos.median()])):
    a = sub[sub.atr<sub.atr.median()].fr.values; b = sub[sub.atr>=sub.atr.median()].fr.values
    p2,l2,h2 = ci(a,b)
    print(f"   [{lab}] 内 低ATR−高ATR = {p2:+.3f} CI [{l2:+.3f},{h2:+.3f}] (n={len(a)}/{len(b)}) 跨0? {'是' if l2<0<h2 else '否'}")
