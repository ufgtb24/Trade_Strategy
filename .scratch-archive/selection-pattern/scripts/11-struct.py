"""11 同日对照配对票 · 第五步：规则里引用 pattern 自身结构的部分，对照怎么套用（替代说法的偏差）。

测试用结构规则（任何股票都算得出）：止损位 L = 过去 20 日最低价，止盈位 H = 过去 60 日最高价（都含决策日 t），
次日开盘 P 买入；之后第一个收盘 ≤ L 或 ≥ H 的日子当日收盘卖，40 日到期收盘卖。记 sL = ln(L/P)、sH = ln(H/P)。
对照（同一配对格 / 近邻里的每个成员 j）怎么套：
  A0 基准：用 j 自己的结构位（领先应约为 0）
  A1 同比例：继承买点 i 的 sL_i、sH_i（相对买入价的对数距离）
  A2 固定倍数：sL = cL·M_j、sH = cH·M_j，cL / cH = 这批买点 sL/M、sH/M 的中位数
  A3 移植：sL = (sL_i / M_i)·M_j、sH = (sH_i / M_i)·M_j（继承买点自己的「距离 ÷ M」）；持有上限同买点（这里都是 40 日）
偏差 = 替代下的领先 − A0 下的领先（典型一笔、平均一笔各算）。
买点：无偏好随机、当天 M 最高 / 最低一档、平时波动最高 / 最低一档，均为分散长相、每年 1000 个，20 次。
另把无偏好随机的买点按当天 M 在池内的十档分开，看偏差随波动水平怎么变。
用法：uv run python .scratch/selection-pattern/scripts/11-struct.py [配对 ...]（缺省 M5 M5xH5 M10xH3 K20 K50；
      第一轮就是用这五种跑的；看过结果后补跑推荐的 K10，另存 11-struct-K10.*）
输出：scripts/11-struct.csv.gz、scripts/11-struct_out.txt
"""
from __future__ import annotations

import importlib.util
import sys
import time
import zlib
from multiprocessing import get_context
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("core11", HERE / "11-core.py")
core = importlib.util.module_from_spec(spec); sys.modules["core11"] = core; spec.loader.exec_module(core)
spec_b = importlib.util.spec_from_file_location("bias11", HERE / "11-bias.py")
bias = importlib.util.module_from_spec(spec_b); sys.modules["bias11"] = bias; spec_b.loader.exec_module(bias)

G: dict = {}
N_REP = 20
FAKES = ["rand", "M_top10", "M_bot10", "H_top10", "H_bot10"]
VARIANTS = ["A0", "A1", "A2", "A3"]


def pairs_of(mt, rows):
    """每个买点的对照成员：返回 (买点序号, 成员行号)。"""
    if mt.kind == "cell":
        c = mt.cell[rows]
        st, en = G["cstart"][mt.name][c], G["cstart"][mt.name][c + 1]
        ln = en - st
        hi = np.repeat(np.arange(len(rows)), ln)
        off = np.arange(ln.sum()) - np.repeat(np.cumsum(ln) - ln, ln)
        mem = G["corder"][mt.name][np.repeat(st, ln) + off]
        return hi, mem
    nb = mt.nb[rows]
    hi = np.repeat(np.arange(len(rows)), nb.shape[1])
    mem = nb.ravel()
    ok = mem >= 0
    return hi[ok], mem[ok]


def evaluate(mt, rows):
    P = G["P"]
    sL, sH, M, lp, y0 = P["sL"], P["sH"], P["M"], P["lp"], G["y0"]
    hi, mem = pairs_of(mt, rows)
    keep = G["okS"][mem]                 # 对照成员也要有自己的结构位，A0 才有定义；四种说法用同一批成员
    hi, mem = hi[keep], mem[keep]
    hit_ret = y0[rows]
    cL = float(np.median(sL[rows] / M[rows])); cH = float(np.median(sH[rows] / M[rows]))
    lo_hi = {
        "A1": (sL[rows][hi], sH[rows][hi]),
        "A2": (cL * M[mem], cH * M[mem]),
        "A3": (sL[rows][hi] / M[rows][hi] * M[mem], sH[rows][hi] / M[rows][hi] * M[mem]),
    }
    nper = np.bincount(hi, minlength=len(rows)).astype(float)
    good = nper > 0
    if not good.all():               # 极少数买点所在格里没有带结构位的成员：这个买点不进本次比较
        sel = good[hi]
        hi, mem = np.unique(hi[sel], return_inverse=True)[1], mem[sel]
        rows = rows[good]; hit_ret = hit_ret[good]
        cL = float(np.median(sL[rows] / M[rows])); cH = float(np.median(sH[rows] / M[rows]))
        lo_hi = {
            "A1": (sL[rows][hi], sH[rows][hi]),
            "A2": (cL * M[mem], cH * M[mem]),
            "A3": (sL[rows][hi] / M[rows][hi] * M[mem], sH[rows][hi] / M[rows][hi] * M[mem]),
        }
        nper = np.bincount(hi, minlength=len(rows)).astype(float)
    wpair = 1.0 / nper[hi]
    res = {}
    for v in VARIANTS:
        if v == "A0":
            val = y0[mem]
        else:
            val, _, _ = core.exit_trade(lp[mem], lo_hi[v][0], lo_hi[v][1])
        cmean = np.bincount(hi, weights=val, minlength=len(rows)) / nper
        res[f"{v}_mean"] = float(hit_ret.mean() - cmean.mean())
        res[f"{v}_med"] = float(np.median(hit_ret) - core.wmedian_small(val, wpair))
    return res


def task(args):
    name, rep, scheme = args
    P = G["P"]
    rng = np.random.default_rng(zlib.crc32(f"{name}-{rep}".encode()))
    bias.G.update(P=P, C=G["C"], ndays=G["ndays"])
    rows = bias.disp_sample(name, rng)
    rows = rows[G["okS"][rows]]
    mt = G["mts"][scheme]
    out = []
    for sc in bias.SCOPES:
        m = bias.scope_mask(P, rows, sc)
        if m.sum() < 20:
            continue
        out.append({"cls": name, "rep": rep, "scheme": scheme, "scope": sc, "n": int(m.sum()),
                    **evaluate(mt, rows[m])})
    if name == "rand":   # 按当天 M 十档分开（全期）
        dec = np.minimum((G["rM"][rows] * 10 - 1e-9).astype(int), 9)
        for k in range(10):
            r = rows[dec == k]
            if len(r) >= 20:
                out.append({"cls": f"rand_Mdec{k + 1}", "rep": rep, "scheme": scheme, "scope": "all",
                            "n": len(r), **evaluate(mt, r)})
    return out


def main():
    schemes = sys.argv[1:] or ["M5", "M5xH5", "M10xH3", "K20", "K50"]
    first = ["M5", "M5xH5", "M10xH3", "K20", "K50"]          # 第一轮跑的五种；之后补跑的另存一份
    suffix = "" if schemes == first else "-" + "-".join(schemes)
    t0 = time.time()
    P, Y, hold, mts, S = core.load_all(schemes)
    okS = np.isfinite(P["sL"]) & np.isfinite(P["sH"])
    y0 = np.full(P["N"], np.nan)
    r, _, _ = core.exit_trade(P["lp"][okS], P["sL"][okS], P["sH"][okS])
    y0[okS] = r
    cstart, corder = {}, {}
    for s, mt in mts.items():
        if mt.kind == "cell":
            corder[s] = np.argsort(mt.cell, kind="stable")
            cstart[s] = np.concatenate(([0], np.cumsum(mt.cnt))).astype(np.int64)
    C = bias.classes(P)
    for k in C:
        C[k] &= okS
    ndays = pd.Series(pd.DatetimeIndex(P["calendar"]).year).value_counts().to_dict()
    G.update(P=P, mts=mts, y0=y0, okS=okS, cstart=cstart, corder=corder, C=C, ndays=ndays,
             rM=core.day_rank(P, P["M"]))
    print(f"ready {time.time() - t0:.0f}s；有结构位的行 {okS.mean():.3f}；全池结构规则每笔 中位 {np.nanmedian(y0[okS]):+.4f}",
          flush=True)
    tasks = [(n, r, s) for s in schemes for n in FAKES for r in range(N_REP)]
    with get_context("fork").Pool(12) as mp:
        res = mp.map(task, tasks, chunksize=1)
    df = pd.DataFrame([x for ch in res for x in ch])
    df.to_csv(HERE / f"11-struct{suffix}.csv.gz", index=False)
    for v in ["A1", "A2", "A3"]:
        for t in ("mean", "med"):
            df[f"bias_{v}_{t}"] = df[f"{v}_{t}"] - df[f"A0_{t}"]
    g = df.groupby(["scheme", "cls", "scope"]).mean(numeric_only=True)
    cols = ["n", "A0_med", "A0_mean"] + [f"bias_{v}_{t}" for v in ["A1", "A2", "A3"] for t in ("med", "mean")]
    txt = ("结构规则替代说法：每格为 20 次平均，单位百分点（每笔收益）。A0 列是对照用自己结构位时的领先；"
           "bias 列 = 替代下的领先 − A0 下的领先。\n" + (g[cols] * np.r_[1, [100] * (len(cols) - 1)]).round(3).to_string())
    (HERE / f"11-struct{suffix}_out.txt").write_text(txt + f"\n耗时 {time.time() - t0:.0f}s\n")
    print(txt[:3000])


if __name__ == "__main__":
    main()
