# -*- coding: utf-8 -*-
"""agentB:阈值规则删除模拟 + 稳健性检查。

对候选规则(单特征阈值/组合)在 80 样本上模拟删除,报告删前删后
n / fr median / FP(Σup/(Σup+Σdown+Σboth)) / 被删样本 mean_fr,
并检查:好坏组误删、股集中度、特征族相关。
"""
from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
df = pd.read_csv(HERE / "agentB_features.csv")
rows = pickle.loads((HERE / "samples.pkl").read_bytes())
by_id = {r["match_id"]: r for r in rows}

order = df["fr"].rank(method="first")
df["grp"] = np.where(order <= 20, "bad", np.where(order > 60, "good", "mid"))


def fp_cols(sub: pd.DataFrame) -> tuple[int, int, int, int]:
    return (int(sub["fp_up"].sum()), int(sub["fp_down"].sum()),
            int(sub["fp_both"].sum()), int(sub["fp_none"].sum()))


# fp dict 列展开(从 samples.pkl 直接取,避免 csv str 解析)
fpd = pd.DataFrame([{f"fp_{k}": by_id[m]["fp"][k] for k in ("up", "down", "both", "none")}
                    for m in df["match_id"]])
df = pd.concat([df.drop(columns=["fp"]), fpd], axis=1)

base_u, base_d, base_b, base_n = fp_cols(df)
print(f"BASE n=80 median={df['fr'].median():.4f} "
      f"FP={base_u/(base_u+base_d+base_b):.4f} up/dn/both/none={base_u}/{base_d}/{base_b}/{base_n}")

RULES: dict[str, pd.Series] = {
    "body_max_tr>=0.75": df["body_max_tr"] >= 0.75,
    "body_max_tr>=0.60": df["body_max_tr"] >= 0.60,
    "dd_max_tr>=0.60": df["dd_max_tr"] >= 0.60,
    "n_red>=2": df["n_red"] >= 2,
    "vol_red_ratio>=0.15": df["vol_red_ratio"] >= 0.15,
    "vol_red_ratio>=0.25": df["vol_red_ratio"] >= 0.25,
    "OR: body_tr.75|vol.15": (df["body_max_tr"] >= 0.75) | (df["vol_red_ratio"] >= 0.15),
    "OR: body_tr.75|nred2": (df["body_max_tr"] >= 0.75) | (df["n_red"] >= 2),
    "OR: body_tr.75|vol.15|nred2": ((df["body_max_tr"] >= 0.75) | (df["vol_red_ratio"] >= 0.15)
                                     | (df["n_red"] >= 2)),
    "AND: body_tr.75&vol.15": (df["body_max_tr"] >= 0.75) & (df["vol_red_ratio"] >= 0.15),
}

for name, mask in RULES.items():
    keep = df[~mask]
    u, d, b, n = fp_cols(keep)
    del_fr = df.loc[mask, "fr"]
    grp = df.loc[mask, "grp"].value_counts().to_dict()
    syms = df.loc[mask, "symbol"].nunique()
    print(f"{name:32s} del={mask.sum():2d} keep_n={len(keep):2d} "
          f"med={keep['fr'].median():.4f} FP={u/(u+d+b):.4f}(u/d/n={u}/{d}/{n}) "
          f"del_mean_fr={del_fr.mean():.4f} del_grp={grp} del_syms={syms}")

# 好组误删检查(top20 中招比例)
for name, mask in RULES.items():
    hit_good = int((mask & (df["grp"] == "good")).sum())
    hit_bad = int((mask & (df["grp"] == "bad")).sum())
    print(f"{name:32s} hits bad {hit_bad}/20  good {hit_good}/20")

# 特征族相关(Spearman |rho|)
cols = ["n_red", "revert_len", "trough_lag", "red_frac", "body_max_tr",
        "dd_max_tr", "vol_red_ratio", "ddown_bo"]
print("\nSpearman 相关矩阵(8 核心特征):")
print(df[cols].corr(method="spearman").round(2).to_string())

# 被删样本明细(OR 规则)
m = RULES["OR: body_tr.75|vol.15|nred2"]
det = df.loc[m, ["symbol", "fr", "grp", "body_max_tr", "vol_red_ratio", "n_red"]]
print("\nOR 规则删除明细(按 fr 升序):")
print(det.sort_values("fr").to_string(index=False, float_format=lambda v: f"{v:.3f}"))
