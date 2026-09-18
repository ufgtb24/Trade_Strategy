"""v2 汇总：端到端（挑选 → 门槛 → 前向窗）、新规则、报数覆盖率、T=2 vs T=3。

用法：uv run python report2.py --tag v2T2 --T 2
"""
import argparse
import os

import numpy as np
import pandas as pd

from sim import AT, DELTA, REF_FLAT, scenarios

HERE = os.path.dirname(os.path.abspath(__file__))
BANDS = ["全平", "小效应", "大效应", "工作点即最优"]
NAMES = {
    "keep": "维持现行参数", "naive": "朴素取最大", "naive_gd": "朴素取最大 >δ才换", "cur": "现行规则",
    "cur_gated": "现行规则 校正后>0才换", "cur_gd": "现行规则 >δ才换", "one_se": "一倍标准误",
    "one_se_gd": "一倍标准误 >δ才换", "cf_draft": "草案交叉拟合", "cf_draft_g": "草案交叉拟合 >0才换",
    "cf_strict_g": "双向剔除(取高规则) >0才换", "cf_loyo_g": "整年留出(取高规则) >0才换",
    "pk_loyog": "朴素取最大 + 整年留出>0才换", "pl_loyog": "现行规则 + 整年留出>0才换",
    "pk_strictg": "朴素取最大 + 双向剔除>0才换", "pk_draftg": "朴素取最大 + 留一格>0才换",
    "wf_pk_g": "朴素取最大 + walk-forward>0才换", "eA": "两向随机效应(逐格水平)", "eA_g": "两向随机效应 >δ才换",
    "eP_g": "配对收缩(格均值中心) >δ才换", "ePz_g": "配对收缩(0中心) >δ才换", "eb_2way": "平滑先验后验",
    "oracle": "oracle",
}


def band(r):
    if r.surface == "flat":
        return "全平"
    if r.surface == "theta0opt":
        return "工作点即最优"
    return "小效应" if r.A <= 2 else "大效应"


def load(tag, T):
    df = pd.read_parquet(os.path.join(HERE, "results", f"rows_{tag}.parquet"))
    meta = pd.DataFrame(scenarios(T=T))
    meta["band"] = meta.apply(band, axis=1)
    df = df.merge(meta, on="sid")
    df["proc"] = df.proc.astype(str); df["obj"] = df.obj.astype(str)
    df["dl"] = df.obj.map(DELTA)
    return df


def nm(p):
    base, v = (p[:-2], "+前向窗") if p.endswith("+v") else (p, "")
    return NAMES.get(base, base) + v


def tbl_e2e(df, obj, noise, procs):
    d = df[(df.obj == obj) & (df.noise == noise)]
    L = ["| 流程 | " + " | ".join(f"{b}：部署年增益 / 10%分位 / 差出δ / 写入" for b in BANDS) + " |",
         "|---|" + "---|" * len(BANDS)]
    for p in procs:
        cells = []
        for b in BANDS:
            g = d[(d.proc == p) & (d.band == b)]
            if g.empty:
                cells.append("—"); continue
            cells.append(f"{g.G_F.mean():+.2f} / {g.G_F.quantile(.1):+.1f} / {(g.G_F < -g.dl).mean():.0%} / "
                         f"{(g.cell != REF_FLAT).mean():.0%}")
        L.append(f"| {nm(p)} | " + " | ".join(cells) + " |")
    return "\n".join(L)


def tbl_sel(df, obj, noise, procs):
    d = df[(df.obj == obj) & (df.noise == noise)]
    L = ["| 流程 | " + " | ".join(f"{b}：平稳增益 / 差出δ/2 / 不动" for b in BANDS) + " |", "|---|" + "---|" * len(BANDS)]
    for p in procs:
        cells = []
        for b in BANDS:
            g = d[(d.proc == p) & (d.band == b)]
            cells.append(f"{g.G_S.mean():+.2f} / {(g.G_S < -g.dl / 2).mean():.0%} / {(g.cell == REF_FLAT).mean():.0%}"
                         if len(g) else "—")
        L.append(f"| {nm(p)} | " + " | ".join(cells) + " |")
    return "\n".join(L)


def tbl_honest(df, obj, procs):
    L = ["| 报数 | " + " | ".join(f"{n}：偏差 / RMSE / 相关 / 90%覆盖" for n in ("N0", "N1", "N2")) + " |", "|---|---|---|---|"]
    for p in procs:
        row = []
        for n in ("N0", "N1", "N2"):
            g = df[(df.obj == obj) & (df.noise == n) & (df.proc == p)]
            g = g[np.isfinite(g.rep_val)]
            if g.empty:
                row.append("—"); continue
            e = g.rep_val - g.G_F
            cr = np.corrcoef(g.rep_val, g.G_F)[0, 1] if g.rep_val.std() > 1e-9 else np.nan
            ok = np.isfinite(g.se)
            cov = (np.abs(e[ok]) <= 1.645 * g.se[ok]).mean() if ok.any() else np.nan
            row.append(f"{e.mean():+.2f} / {np.sqrt((e ** 2).mean()):.2f} / {cr:+.2f} / "
                       + ("—" if not np.isfinite(cov) else f"{cov:.0%}"))
        L.append(f"| {p} | " + " | ".join(row) + " |")
    return "\n".join(L)


def rule_choice(df):
    out = []
    for kind in ("draft", "loyo", "strict"):
        a = df[df.proc == f"cf_{kind}_pk"][["sid", "rep", "obj", "noise", "G_S"]].rename(columns={"G_S": "pk"})
        b = df[df.proc == f"cf_{kind}_pl"][["sid", "rep", "obj", "G_S"]].rename(columns={"G_S": "pl"})
        c = df[df.proc == f"cf_{kind}"][["sid", "rep", "obj", "extra"]]
        m = a.merge(b, on=["sid", "rep", "obj"]).merge(c, on=["sid", "rep", "obj"])
        m = m[np.abs(m.pk - m.pl) > 1e-9]
        m["correct"] = np.where(m.extra == 1, m.pl > m.pk, m.pk > m.pl)
        g = m.groupby(["obj", "noise"]).correct.mean().round(3)
        out.append(f"{kind}: " + ", ".join(f"{o}/{n}={v:.2f}" for (o, n), v in g.items()))
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="v2T2")
    ap.add_argument("--T", type=int, default=2)
    a = ap.parse_args()
    df = load(a.tag, a.T)
    e2e = ["keep", "naive+v", "cur+v", "cur_gated+v", "cur_gd+v", "one_se+v", "one_se_gd+v", "cf_draft+v",
           "cf_draft_g+v", "cf_loyo_g+v", "cf_strict_g+v", "pk_loyog+v", "pl_loyog+v", "pk_strictg+v", "pk_draftg+v",
           "wf_pk_g+v", "eA_g+v", "eP_g+v", "ePz_g+v", "naive_gd+v"]
    sel = ["keep", "naive", "naive_gd", "cur", "cur_gated", "cur_gd", "one_se", "one_se_gd", "cf_draft", "cf_draft_g",
           "pk_loyog", "pl_loyog", "pk_strictg", "pk_draftg", "wf_pk_g", "eA", "eA_g", "eP_g", "ePz_g", "eb_2way",
           "oracle"]
    hon = ["naive", "cur", "cur_corr", "one_se", "cf_draft_pk", "cf_draft_pl", "cf_draft", "cf_loyo_pk", "cf_loyo",
           "cf_strict_pk", "wf_pk", "wf_pl", "eA", "eP", "ePz", "eb_2way", "naive+v"]
    print(f"# {a.tag}（T={a.T}）\n")
    print("## 交叉拟合选对规则的概率\n\n" + rule_choice(df))
    for obj in ("Q", "U"):
        for n in ("N1", "N2", "N0"):
            print(f"\n## 端到端（挑选→门槛→前向窗）{obj} {n}\n")
            print(tbl_e2e(df, obj, n, e2e))
            print(f"\n## 挑选本身（无前向窗）{obj} {n}\n")
            print(tbl_sel(df, obj, n, sel))
        print(f"\n## 报数诚实度 {obj}（相对部署年真值）\n")
        print(tbl_honest(df, obj, hon))


if __name__ == "__main__":
    main()
