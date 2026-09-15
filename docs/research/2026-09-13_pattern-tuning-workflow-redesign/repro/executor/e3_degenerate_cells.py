# -*- coding: utf-8 -*-
"""e3：265 万格里有多少格与相邻档「完全相同」（机制退化 / 本数据上恒真的闸档）——
只读 cells.npz。W/F 轴是嵌套谓词：紧档计数 == 松档计数 ⟹ 两格样本集合相同（严格证明）。"""
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[5]
Z = np.load(ROOT / "outputs/tune_gates/bb_v1/main/cells.npz", allow_pickle=True)
CNT, FP = Z["count"], Z["fp"]
AX = ["exceed", "mrh", "gap", "rise", "span", "scb", "count", "dpk", "fd", "pa", "vs", "mdd"]
NEST = set(AX[6:])
dup_any = np.zeros(CNT.shape[:-1], bool)
for ax, nm in enumerate(AX):
    L = CNT.shape[ax]
    for i in range(1, L):
        a = np.take(CNT, i, axis=ax); b = np.take(CNT, i - 1, axis=ax)
        fa = np.take(FP, i, axis=ax); fb = np.take(FP, i - 1, axis=ax)
        same = (a == b).all(-1) & (np.isclose(fa, fb, equal_nan=True)).all(-1) & (a.sum(-1) > 0)
        idx = [slice(None)] * dup_any.ndim; idx[ax] = i
        dup_any[tuple(idx)] |= same
        print(f"{nm:6s} 档{i-1}->{i}：与相邻松档完全相同的格占该档 {same.mean():.4f}{'（嵌套谓词，严格同集）' if nm in NEST else ''}")
tot = int(np.prod(dup_any.shape))
print(f"\n至少沿一条轴与相邻档完全相同的格：{int(dup_any.sum())} / {tot} = {dup_any.mean():.4f}")
sig = np.concatenate([CNT.reshape(tot, -1).astype(float), np.nan_to_num(FP.reshape(tot, -1), nan=-1.0)], axis=1)
nz = CNT.reshape(tot, -1).sum(1) > 0
u = np.unique(np.round(sig[nz], 12), axis=0)
print(f"非空格 {int(nz.sum())}；按 (两折计数, 两折 FP) 去重后的不同格 ≤ {len(u)}")
