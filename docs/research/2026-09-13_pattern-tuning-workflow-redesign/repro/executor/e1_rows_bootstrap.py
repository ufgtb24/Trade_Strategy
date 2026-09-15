# -*- coding: utf-8 -*-
"""e1：长表行级实验（2 档子设计「生产值↔备选」的 2^12 = 4096 格）。

回答：
  A. 因子主效应 / 两两交互的抽样误差——按股簇 bootstrap、按时间块 bootstrap、按行(match) bootstrap
     三种口径各报 SE，看噪声主要来自个股还是同期行情（决定「换股票」能否当独立样本）；
  B. 每格有效样本：买点日 / match 行 / 股 / 股×标签窗簇 / 时间桶；设计效应 = bootstrap 方差 ÷ 二项方差；
  C. 有效格数：在 4096 格（与其 64 格子设计）上「挑最好一格」时 bootstrap 最大偏离 → 反推 K_eff，
     并算 bootstrap optimism，检验噪声地板公式 σ·E[max of K_eff 个标准正态]；
  D. 突破幅度阈值 0.003→0.0075 的收益拆解：删掉的买点 / 新出现的买点 / 共同买点。

只读 outputs/tune_gates/bb_v1/main/longtable/ 分片的需要列，逐片过滤，单进程峰值 < 1.5GB。
"""
import itertools
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[5]
LT = ROOT / "outputs/tune_gates/bb_v1/main/longtable"
OUT = Path(__file__).resolve().parent
T0 = time.time()

D_COLS = ["bo.exceed_threshold", "bo.min_relative_height", "burst.gap_max", "tb.max_rise_k", "tb.max_span",
          "tb.stop_confirm_bars"]
D_NAMES = ["exceed", "mrh", "gap", "rise", "span", "scb"]
D_LOHI = [(0.003, 0.0075), (0.2, 0.3), (8, 4), (1.5, 2.25), (20, 10), (1, 3)]
W_NAMES = ["count", "dpk", "fd", "pa", "vs", "mdd"]
NAMES = D_NAMES + W_NAMES
COLS = ["symbol"] + D_COLS + ["burst.count", "burst.distinct_pk", "burst.first_drought", "burst.peak_age_max",
                              "burst.max_bar_vol_ratio", "tb.max_day_drop", "burst.start", "burst.end", "tb.start",
                              "tb.end", "buy_date", "fp_up", "fp_down", "fp_both", "fp_none", "fold_6M"]
FOLD6 = ["2024H1", "2024H2", "2025H1", "2025H2"]
POWER = 100
B = 200

parts = []
for sp in sorted(LT.glob("part-*.parquet")):
    df = pq.read_table(sp, columns=COLS).to_pandas()
    keep = np.ones(len(df), bool)
    for c, (lo, hi) in zip(D_COLS, D_LOHI):
        v = df[c].to_numpy(dtype=float)
        keep &= np.isclose(v, lo) | np.isclose(v, hi)
    df = df[keep]
    out = pd.DataFrame({"symbol": df["symbol"].astype(str).to_numpy()})
    dcode = np.zeros(len(df), np.int64)
    for j, (c, (lo, hi)) in enumerate(zip(D_COLS, D_LOHI)):
        dcode |= (np.isclose(df[c].to_numpy(dtype=float), hi).astype(np.int64) << j)
    out["dcode"] = dcode
    mdd = df["tb.max_day_drop"].to_numpy(dtype=float)
    passes = [df["burst.count"].to_numpy() >= 2, df["burst.distinct_pk"].to_numpy() >= 3,
              df["burst.first_drought"].to_numpy() >= 40, df["burst.peak_age_max"].to_numpy() >= 60,
              df["burst.max_bar_vol_ratio"].to_numpy() >= 3, mdd < 0.2]
    pm = np.zeros(len(df), np.int64)
    for b, p in enumerate(passes):
        pm |= (p.astype(np.int64) << b)
    out["pmask"] = pm
    out["nan_mdd"] = np.isnan(mdd)
    for c in ["burst.start", "burst.end", "tb.start", "tb.end", "fp_up", "fp_down", "fp_both", "fp_none"]:
        out[c] = df[c].to_numpy()
    out["day"] = (pd.to_datetime(df["buy_date"]).to_numpy().astype("datetime64[D]").astype(np.int64))
    out["f6"] = pd.Categorical(df["fold_6M"].astype(str), categories=FOLD6).codes
    parts.append(out)
    del df
R = pd.concat(parts, ignore_index=True); del parts
print(f"读入 {len(R)} 行(2 档子设计)，NaN max_day_drop 行 {int(R.nan_mdd.sum())}，fold 缺失 {(R.f6 < 0).sum()}，耗时 {time.time()-T0:.0f}s")
R = R[R.f6 >= 0].reset_index(drop=True)

sym_code = pd.Categorical(R.symbol).codes.astype(np.int64); NS = sym_code.max() + 1
blk_code = ((R.day - R.day.min()) // 29).to_numpy()          # 约 20 交易日一块
NBK = blk_code.max() + 1
clu58 = ((R.day - R.day.min()) // 58).to_numpy()              # 40 交易日标签窗 ≈ 58 日历天
ST = R[["fp_up", "fp_down", "fp_both", "fp_none"]].to_numpy(np.float64)
base_idx = (R.dcode.to_numpy() * 64 + R.pmask.to_numpy()) * 4 + R.f6.to_numpy()
NCELL = 64 * 64 * 4
print(f"股 {NS}，时间块(29 日历天) {NBK}，58 天桶 {clu58.max()+1}")


def cell_tensor(w=None):
    """→ (2,)*12 + (4 folds, 4 states)，W/F 6 位按「闸开=只留通过行」做超集和。"""
    arr = np.zeros((NCELL, 4))
    for s in range(4):
        arr[:, s] = np.bincount(base_idx, weights=ST[:, s] if w is None else ST[:, s] * w, minlength=NCELL)
    t = arr.reshape((2,) * 6 + (2,) * 6 + (4, 4))            # D 6 位(dcode bit j 在低位)……
    # dcode 的 bit0 是 exceed：reshape 后第 0 轴是最高位，需要把位序翻过来
    t = t.transpose(list(range(5, -1, -1)) + list(range(11, 5, -1)) + [12, 13])
    for ax in range(6, 12):                                    # 闸位 0=关(全体) 1=开(通过者)
        a0 = np.take(t, 0, axis=ax); a1 = np.take(t, 1, axis=ax)
        t = np.stack([a0 + a1, a1], axis=ax)
    return t


def fp_of(t, pool_year=True):
    if pool_year:
        t = np.stack([t[..., 0, :] + t[..., 1, :], t[..., 2, :] + t[..., 3, :]], axis=-2)
    den = t[..., 0] + t[..., 1] + t[..., 2]
    with np.errstate(invalid="ignore", divide="ignore"):
        return t[..., 0] / den, t.sum(-1)


T = cell_tensor()
FPY, NY = fp_of(T)                     # (2,)*12 + (2 years,)
T_all = np.stack([T.sum(-2)], axis=-2)
FPA, NA = fp_of(T_all, pool_year=False)
FPA, NA = FPA[..., 0], NA[..., 0]
OK = (NY >= POWER).all(-1)             # 按年功效线(与 region 同口径)


def effects(fpy, fpa):
    """主效应(按年 2 个 + 两年合并 1 个) 与 两两交互(条件效应之差)。只用四臂都过功效线的配对。"""
    me, ia = {}, {}
    for j, a in enumerate(NAMES):
        okp = np.take(OK, 1, axis=j) & np.take(OK, 0, axis=j)
        dy = np.take(fpy, 1, axis=j) - np.take(fpy, 0, axis=j)
        da = np.take(fpa, 1, axis=j) - np.take(fpa, 0, axis=j)
        me[a] = np.array([dy[okp][:, 0].mean(), dy[okp][:, 1].mean(), da[okp].mean()])
    for j, k in itertools.combinations(range(12), 2):
        def sl(x, bj, bk):
            return np.take(np.take(x, bk, axis=k), bj, axis=j)
        okk = sl(OK, 1, 1) & sl(OK, 1, 0) & sl(OK, 0, 1) & sl(OK, 0, 0)
        dy = (sl(fpy, 1, 1) - sl(fpy, 0, 1)) - (sl(fpy, 1, 0) - sl(fpy, 0, 0))
        da = (sl(fpa, 1, 1) - sl(fpa, 0, 1)) - (sl(fpa, 1, 0) - sl(fpa, 0, 0))
        ia[(NAMES[j], NAMES[k])] = np.array([dy[okk][:, 0].mean(), dy[okk][:, 1].mean(), da[okk].mean()])
    return me, ia


ME0, IA0 = effects(FPY, FPA)

# ---- 选格统计：score = 两年 delta(相对 D=生产 且闸全关 那一格) 的 min，与 region 同口径(无邻域)
REF = (0,) * 12


def select_stats(fpy, sub=None):
    d = fpy - fpy[REF]
    s = np.where(OK, d.min(-1), np.nan)
    if sub is not None:
        s = s[sub]
    return s


PROD = (0,) * 6 + (0, 1, 1, 1, 1, 1)
_g = np.indices((2,) * 12).reshape(12, -1).T
HAM = (np.abs(_g - np.array(PROD)).sum(1) <= 2).reshape((2,) * 12)
SUBS = {"4096 格(D×闸)": None,
        "79 格(生产点汉明距≤2)": HAM,
        "64 格(只 D，闸全关)": (Ellipsis,) + (0,) * 6,
        "64 格(只闸，D=生产)": (0,) * 6 + (Ellipsis,)}
S0 = {k: select_stats(FPY, v) for k, v in SUBS.items()}

rng = np.random.default_rng(20260913)
boot = {"股簇": [], "时间块": [], "行(match)": []}
REP = {"股簇": [], "时间块": [], "行(match)": []}
opt = {m: {k: [] for k in SUBS} for m in boot}
zmax = {m: {k: [] for k in SUBS} for m in boot}
REP_FP = {m: [] for m in boot}
for m in boot:
    for b in range(B):
        if m == "股簇":
            w = rng.multinomial(NS, np.full(NS, 1 / NS))[sym_code].astype(float)
        elif m == "时间块":
            w = rng.multinomial(NBK, np.full(NBK, 1 / NBK))[blk_code].astype(float)
        else:
            w = rng.multinomial(len(R), np.full(len(R), 1 / len(R))).astype(float)
        t = cell_tensor(w)
        fpy, _ = fp_of(t)
        fpa, _ = fp_of(np.stack([t.sum(-2)], axis=-2), pool_year=False)
        me, ia = effects(fpy, fpa[..., 0])
        boot[m].append((me, ia))
        REP[m].append((fpy, fpa[..., 0], _.copy()))
        REP_FP[m].append(fpy[REF])
        for k, v in SUBS.items():
            sb = select_stats(fpy, v)
            s0 = S0[k]
            cb = np.nanargmax(sb)
            opt[m][k].append(sb.ravel()[cb] - s0.ravel()[cb])
            zmax[m][k].append(sb - s0)
    print(f"  bootstrap {m} 完成，累计 {time.time()-T0:.0f}s")

lines = []
P = lines.append
P("## A. 主效应（pt；2024 / 2025 / 两年合并）与三种 bootstrap SE（两年合并口径）")
P("| 因子 lo→hi | 2024 | 2025 | 合并 | SE股簇 | SE时间块 | SE行 | z(取最大SE) | 两年同号 | 买点日× |")
P("|---|---|---|---|---|---|---|---|---|---|")
for j, a in enumerate(NAMES):
    ses = {m: np.std([x[0][a][2] for x in boot[m]], ddof=1) * 100 for m in boot}
    v = ME0[a] * 100
    nh = np.take(NA, 1, axis=j)[np.take(OK, 1, axis=j) & np.take(OK, 0, axis=j)].sum()
    nl = np.take(NA, 0, axis=j)[np.take(OK, 1, axis=j) & np.take(OK, 0, axis=j)].sum()
    lohi = D_LOHI[j] if j < 6 else ["off→on"]
    z = v[2] / max(ses.values())
    P(f"| {a} {lohi} | {v[0]:+.2f} | {v[1]:+.2f} | {v[2]:+.2f} | {ses['股簇']:.2f} | {ses['时间块']:.2f} | {ses['行(match)']:.2f} | {z:+.1f} | {'是' if v[0]*v[1]>0 else '否'} | {nh/nl:.3f} |")
P("")
P("## A2. 两两交互（条件效应之差，两年合并 pt）按 |z| 排序前 15（z 用股簇与时间块 SE 的较大者）")
rows = []
for key, v in IA0.items():
    se = max(np.std([x[1][key][2] for x in boot[m]], ddof=1) for m in ["股簇", "时间块"]) * 100
    rows.append((key, v * 100, se))
rows.sort(key=lambda r: -abs(r[1][2]) / r[2])
P("| 对 | 2024 | 2025 | 合并 | SE | z | 同 node |")
P("|---|---|---|---|---|---|---|")
node = dict(exceed="bo", mrh="bo", gap="burst", rise="tb", span="tb", scb="tb", count="burst", dpk="burst", fd="burst",
            pa="burst", vs="burst", mdd="tb")
for key, v, se in rows[:15]:
    P(f"| {key[0]}×{key[1]} | {v[0]:+.2f} | {v[1]:+.2f} | {v[2]:+.2f} | {se:.2f} | {v[2]/se:+.1f} | {'是' if node[key[0]]==node[key[1]] else '否'} |")
zs = np.array([abs(v[2]) / se for _, v, se in rows])
same = np.array([node[k[0]] == node[k[1]] for k, _, _ in rows])
P(f"\n|z| 分布：全部 66 对 中位 {np.median(zs):.2f}，|z|≥3 的 {int((zs>=3).sum())} 对；同 node {same.sum()} 对 |z| 中位 {np.median(zs[same]):.2f}，跨 node {(~same).sum()} 对 |z| 中位 {np.median(zs[~same]):.2f}")
mez = []
for j, a in enumerate(NAMES):
    se = max(np.std([x[0][a][2] for x in boot[m]], ddof=1) for m in ["股簇", "时间块"]) * 100
    mez.append(abs(ME0[a][2] * 100) / se)
P(f"|主效应 z| 中位 {np.median(mez):.2f}")

P("\n## A3. 运行点(改前生产点)上的单参数效应（OAT，pt）与 SE；以及局部交互探针")
P("| 因子 翻转 | 2024 | 2025 | 合并 | SE股簇 | SE时间块 | z | 两年同号 | 买点日× |")
P("|---|---|---|---|---|---|---|---|---|")
def flip(c, *js):
    c = list(c)
    for j in js:
        c[j] = 1 - c[j]
    return tuple(c)
def oat(fpy, fpa, j):
    a, b = flip(PROD, j), PROD
    return np.array([fpy[a][0] - fpy[b][0], fpy[a][1] - fpy[b][1], fpa[a] - fpa[b]])
for j, a in enumerate(NAMES):
    v = oat(FPY, FPA, j) * 100
    ses = {m: np.std([oat(x[0], x[1], j)[2] for x in REP[m]], ddof=1) * 100 for m in ["股簇", "时间块"]}
    z = v[2] / max(ses.values())
    r = NA[flip(PROD, j)] / NA[PROD]
    P(f"| {a} | {v[0]:+.2f} | {v[1]:+.2f} | {v[2]:+.2f} | {ses['股簇']:.2f} | {ses['时间块']:.2f} | {z:+.1f} | {'是' if v[0]*v[1]>0 else '否'} | {r:.3f} |")
P("\n局部交互探针（运行点上 j 的效应在 k 翻转后变了多少，合并 pt），按 |z| 前 12：")
def probe(fpy, fpa, j, k):
    e_k = fpa[flip(PROD, j, k)] - fpa[flip(PROD, k)]
    e_0 = fpa[flip(PROD, j)] - fpa[PROD]
    return e_k - e_0
pr = []
for j, k in itertools.combinations(range(12), 2):
    v = probe(FPY, FPA, j, k) * 100
    se = max(np.std([probe(x[0], x[1], j, k) for x in REP[m]], ddof=1) for m in ["股簇", "时间块"]) * 100
    pr.append((NAMES[j], NAMES[k], v, se))
pr.sort(key=lambda r: -abs(r[2]) / r[3])
for a, b, v, se in pr[:12]:
    P(f"- {a}×{b}: {v:+.2f}pt (SE {se:.2f}, z {v/se:+.1f})")
zz = np.array([abs(v) / se for _, _, v, se in pr])
P(f"局部探针 |z| 中位 {np.median(zz):.2f}，|z|≥3 共 {int((zz>=3).sum())} / 66")
P("\n对照：全因子平均主效应 vs 运行点效应 的差（合并 pt），及其 SE（股簇/时间块取大）")
for j, a in enumerate(NAMES):
    diff = lambda fpy, fpa, me: oat(fpy, fpa, j)[2] - me
    d0 = (oat(FPY, FPA, j)[2] - ME0[a][2]) * 100
    se = max(np.std([oat(x[0], x[1], j)[2] - y[0][a][2] for x, y in zip(REP[m], boot[m])], ddof=1) for m in ["股簇", "时间块"]) * 100
    P(f"- {a}: 运行点 − 全因子平均 = {d0:+.2f}pt (SE {se:.2f}, z {d0/se:+.1f})")

P("\n## B. 每格有效样本（参照格：D=生产、闸全关；按年）")
sel = (R.dcode.to_numpy() == 0)
for yi, (f0, f1) in enumerate([(0, 1), (2, 3)]):
    mk = sel & np.isin(R.f6.to_numpy(), [f0, f1])
    days = ST[mk].sum(); rows_ = mk.sum(); syms = len(np.unique(sym_code[mk]))
    sc58 = len(np.unique(sym_code[mk] * 1000 + clu58[mk])); tb58 = len(np.unique(clu58[mk]))
    p = FPY[REF][yi]
    den = ST[mk][:, :3].sum()
    var_bin = p * (1 - p) / den
    P(f"- {2024+yi}：买点日 {int(days)}（有方向 {int(den)}）/ match 行 {rows_} / 股 {syms} / 股×58天簇 {sc58} / 58天时间桶 {tb58}；FP={p:.4f}")
    for m in boot:
        v = np.var([x[yi] for x in REP_FP[m]], ddof=1)
        P(f"    - {m} bootstrap：SE={np.sqrt(v)*100:.2f}pt，设计效应={v/var_bin:.1f}，等效独立买点日≈{p*(1-p)/v:.0f}")
    P(f"    - 二项（买点日独立）SE={np.sqrt(var_bin)*100:.2f}pt")

P("\n## C. 选格偏差与有效格数（score = 两年 Δ 的 min，相对参照格；无邻域）")
sim = np.random.default_rng(1).standard_normal((4000, 4096))
emax_tab = {K: np.mean(np.max(sim[:, :K], axis=1)) for K in [1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096]}
Ks = np.array(list(emax_tab)); Es = np.array(list(emax_tab.values()))
for k in SUBS:
    s0 = S0[k]; nev = int(np.isfinite(s0).sum())
    for m in ["股簇", "时间块"]:
        devs = np.array([np.asarray(x).ravel() for x in zmax[m][k]])     # (B, cells)
        sd = np.nanstd(devs, axis=0, ddof=1)
        zz = devs / sd
        emax = np.nanmean(np.nanmax(zz, axis=1))
        keff = float(np.interp(emax, Es, Ks)) if emax <= Es[-1] else float("inf")
        o = np.array(opt[m][k]) * 100
        top = np.nanargmax(s0.ravel())
        P(f"- {k}：可评估 {nev} 格；{m}：E[max z]={emax:.2f} → K_eff≈{keff:.0f}；中位格 SE={np.nanmedian(sd)*100:.2f}pt；"
          f"最高格朴素分={np.nanmax(s0)*100:+.2f}pt，其 SE={sd[top]*100:.2f}pt；bootstrap optimism={o.mean():+.2f}±{o.std(ddof=1)/np.sqrt(len(o)):.2f}pt")

# ---- D. exceed 0.003→0.0075 拆解(其余 D=生产)
P("\n## D. 突破幅度阈值 0.003→0.0075 的收益拆解（其余 D=生产）")
for wname, wmask in [("闸全关", 0), ("生产闸(dpk≥3,fd≥40,vs≥3,mdd<0.2;峰龄关)", (1 << 1) | (1 << 2) | (1 << 4) | (1 << 5))]:
    sub = R[(R.dcode.isin([0, 1])) & ((R.pmask & wmask) == wmask)].copy()
    sub["tbk"] = list(zip(sub.symbol, sub["tb.start"], sub["tb.end"]))
    lo = sub[sub.dcode == 0]; hi = sub[sub.dcode == 1]
    klo, khi = set(lo.tbk), set(hi.tbk)
    for yname, fs in [("2024", [0, 1]), ("2025", [2, 3])]:
        def agg(df):
            d = df[df.f6.isin(fs)]
            u, dn, bo, no = d.fp_up.sum(), d.fp_down.sum(), d.fp_both.sum(), d.fp_none.sum()
            return int(u + dn + bo + no), (u / (u + dn + bo) if (u + dn + bo) else np.nan)
        rem = lo[~lo.tbk.isin(khi)]; new = hi[~hi.tbk.isin(klo)]; com = hi[hi.tbk.isin(klo)]
        comlo = lo[lo.tbk.isin(khi)]
        nl, fl = agg(lo); nh, fh = agg(hi); nr, fr_ = agg(rem); nn, fn = agg(new); nc, fc = agg(com); ncl, fcl = agg(comlo)
        P(f"- {wname} {yname}：旧 n={nl} FP={fl:.4f} → 新 n={nh} FP={fh:.4f}（Δ{(fh-fl)*100:+.2f}pt）；"
          f"删掉的买点段 n={nr} FP={fr_:.4f}；新出现的 n={nn} FP={fn:.4f}；共同(新侧) n={nc} FP={fc:.4f} / 共同(旧侧) n={ncl} FP={fcl:.4f}")

txt = "\n".join(lines)
(OUT / "e1_output.md").write_text(txt, encoding="utf-8")
print(txt)
print(f"总耗时 {time.time()-T0:.0f}s")
