# -*- coding: utf-8 -*-
"""筛选核:在工作点附近逐个改一处参数,判断哪些改动的首次穿越率差分辨得出,并渲染成业务语言报告。

前半部分(`screen_core` 及报告渲染)只做纯计算与渲染,不读分类表、不过守卫、不写账本、不落盘;
文件末尾的 `run` 是 `tune.screen` 的编排:前置检查、读扫描结果、落盘、写账本。

口径(全部比例口径,0.02 = 2 点;报告层再乘 100):
- 观测单位 = 买点事件:输入的两份 Prepared 都用买点事件口径(同一检测组合内同一买点事件只计一次)。
- 首次穿越率 r = ΣU / ΣD,U = up 计数,D = up+down+both(定向 bar),N = 四态总计。
- 误差按股去簇(`inference.ratio_contrast` 的按股线性化 SE);时间维只作旗标。

对比族(`screen_core`):两个底座(工作点 working、宽进点 wide)× 每个单处改动。
- 检测参数翻转(kind="d_flip"):改后格 = 底座把该轴换成翻转档;est = r(改后格) − r(底座格)。
- 在役闸关闸(kind="gate_off"):两个底座上都比「关 − 开」。开格 = 底座把该闸取工作点的档,
  关格 = 底座把该闸取关闸档;est = r(关格) − r(开格)。宽进点上闸本来就关着,开格是「在宽进点上
  把这道闸打开」,符号仍按「关 − 开」报。
下文把每个对比的两格统称「改后格 X」与「对照格 Y」,est = r_X − r_Y。

多重比较:两年合并的双侧 p 在整个对比族上做 BH,族大小 m = 族里实际的对比个数。
"""
from __future__ import annotations

import itertools
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy import stats

import edge_core
import region_core as RC
from inference import bh, cochran_q, level_se, ratio_contrast, time_window_codes, time_window_days

BASES = ("working", "wide")
Z_FLAG = 2.0            # 年交互 / 差中差 / 探针的旗标门槛(|z|)
P_TIME = 0.05           # 时间窗 Cochran Q 的旗标门槛
NI_Z = 1.645            # 非劣效单侧 95% 下界的 z
BARELY_FRAC = 0.5       # 刚过线:幸存但 q 值 > 阈值 × 此比例(把门槛收紧一半就过不了)
KEEP_SHRINK = 0.3       # 买点数比对照格少这么多以上时报告里标出
_STAB_CHUNK_BYTES = 1 << 27


@dataclass(frozen=True)
class ScreenSpec:
    """筛选的格定义。轴键同 `region_core.cell_index`:检测参数轴用参数键,谓词轴用长表列名。

    working: 全部轴 → 档值(工作点)。
    wide: 全部轴 → 档值(宽进点:检测参数同工作点、谓词轴取最松档)。
    d_flips: 检测参数轴 → [翻转档值, ...](每轴 1~2 个)。
    gate_offs: 在役闸轴(谓词列名)→ 关闸档值(最松档 / 机制下限)。
    """
    working: dict
    wide: dict
    d_flips: dict
    gate_offs: dict


def _family(spec: ScreenSpec, combo_levels: dict, pred_specs: list) -> list[dict]:
    """展开对比族:每个元素 {base, axis, kind, level, x: 改后格档值, y: 对照格档值}。先校验 spec。"""
    pred_axes = [c for c, _, _ in pred_specs]
    for name in BASES:
        lv = getattr(spec, name)
        RC.cell_index(combo_levels, pred_specs, lv)            # 缺轴 / 档值不在表里直接报错
    for ax in combo_levels:
        if spec.wide[ax] != spec.working[ax]:
            raise ValueError(f"ScreenSpec: 宽进点的检测参数 {ax} 应同工作点({spec.working[ax]!r}),实际 {spec.wide[ax]!r}")
    for ax, flips in spec.d_flips.items():
        if ax not in combo_levels:
            raise ValueError(f"ScreenSpec: d_flips 的轴 {ax!r} 不是检测参数轴 {list(combo_levels)}")
        if spec.working[ax] in flips:
            raise ValueError(f"ScreenSpec: {ax} 的翻转档 {flips} 含工作点现值 {spec.working[ax]!r}")
    for ax, off in spec.gate_offs.items():
        if ax not in pred_axes:
            raise ValueError(f"ScreenSpec: gate_offs 的轴 {ax!r} 不是谓词轴 {pred_axes}")
        if spec.working[ax] == off:
            raise ValueError(f"ScreenSpec: 闸 {ax} 的关闸档 {off!r} 等于工作点现值,不是在役闸")
    fam = []
    for base in BASES:
        B = getattr(spec, base)
        for ax, flips in spec.d_flips.items():
            for v in flips:
                fam.append(dict(base=base, axis=ax, kind="d_flip", level=v, x={**B, ax: v}, y=B))
        for ax, off in spec.gate_offs.items():
            fam.append(dict(base=base, axis=ax, kind="gate_off", level=off,
                            x={**B, ax: off}, y={**B, ax: spec.working[ax]}))
    return fam


def design_cells(spec: ScreenSpec, combo_levels: dict, pred_specs: list, *, pair_probes: bool = True) -> dict:
    """筛选用到的全部格:对比族的改后格与对照格、工作点格、工作点上的两两翻转格。

    返回 {
        "family": `_family` 的对比族,每个元素另带 xi / yi = 改后格 / 对照格在 coords 里的列下标,
        "coords": 格坐标列表(combo+pred,不含 fold),同一格只占一列,对比族的格排在最前,
        "n_family_cells": 对比族用到的格数(coords 的前这么多列),
        "working": 工作点格的列下标,
        "pairs": [(改动 a, 改动 b, 两处同时改的格的列下标)]——工作点上任意两个不同轴的单处改动;
                 pair_probes=False 时为空,
    }
    """
    fam = _family(spec, combo_levels, pred_specs)
    cells = _Cells(combo_levels, pred_specs)
    for f in fam:
        f["xi"], f["yi"] = cells.id(f["x"]), cells.id(f["y"])
    n_fam_cells = len(cells.coords)
    w0 = cells.id(spec.working)
    pairs = []
    if pair_probes:
        singles = [f for f in fam if f["base"] == "working"]
        for a, b in itertools.combinations(singles, 2):
            if a["axis"] != b["axis"]:
                pairs.append((a, b, cells.id({**spec.working, a["axis"]: a["level"], b["axis"]: b["level"]})))
    return {"family": fam, "coords": cells.coords, "n_family_cells": n_fam_cells, "working": w0, "pairs": pairs}


def joint_with_interactions(survived, probes) -> list:
    """「下一步一起调」的轴:幸存轴,再加交互兜底——探针 |z| ≥ 2 且其中一方的轴已幸存时,另一方的轴也进。

    survived: 幸存轴(有序);probes: [(axis_a, axis_b, z)]。返回幸存轴在前、兜底带入的轴按探针顺序追加。
    """
    got = set(survived)
    joint = list(survived)
    for a, b, z in probes:
        if not abs(z) >= Z_FLAG:
            continue
        for mine, other in ((a, b), (b, a)):
            if mine in got and other not in joint:
                joint.append(other)
    return joint


class _Cells:
    """格坐标登记表:档值 dict → 列下标(同一格只占一列)。"""

    def __init__(self, combo_levels, pred_specs):
        self.combo_levels, self.pred_specs = combo_levels, pred_specs
        self.coords: list[tuple] = []
        self._pos: dict[tuple, int] = {}

    def id(self, levels: dict) -> int:
        c = RC.cell_index(self.combo_levels, self.pred_specs, levels)
        if c not in self._pos:
            self._pos[c] = len(self.coords)
            self.coords.append(c)
        return self._pos[c]


def _contrast(U, D, N, ids, coefs) -> dict:
    """在 (S, K) 的每股和上算 Σ c·r。同一格重复出现时系数相加;只把涉及格传给 ratio_contrast。"""
    K = U.shape[1]
    c = np.zeros(K)
    np.add.at(c, np.asarray(ids), np.asarray(coefs, dtype=float))
    inv = np.flatnonzero(c != 0)
    if not len(inv):
        return {"est": 0.0, "se": float("nan"), "z": float("nan")}
    return ratio_contrast(U[:, inv], D[:, inv], N[:, inv], c[inv])


def _p_two_sided(z: float) -> float:
    return float(2 * stats.norm.sf(abs(z))) if np.isfinite(z) else float("nan")


def screen_core(prep_year, prep_win, spec: ScreenSpec, *, years: list[str], q: float, delta: float,
                B: int = 300, seed: int = 0, pair_probes: bool = True) -> dict:
    """筛选核:对比族的效应、误差、BH 幸存、各类旗标、交互探针、稳定性。

    参数:
        prep_year: 买点事件口径的 Prepared,折 = 年(`years` 必须都在它的 folds 里)。
        prep_win: 同一张长表、同样轴定义的买点事件口径 Prepared,折 = 时间窗号(窗宽由调用方从标签前瞻期推出)。
        spec: 工作点、宽进点、检测参数翻转档、在役闸关闸档。
        years: 参与「两年合并」与分年的年份折标签,按时间先后。
        q: BH 幸存阈值(q 值 ≤ q 即幸存)。
        delta: 最小关心改进(比例);删闸非劣效门槛取 −delta。
        B, seed: 稳定性检查的按股 bootstrap 副本数与种子。
        pair_probes: 是否做两两交互探针(False 时 probes 为空、没有交互兜底)。

    返回 dict:
        contrasts: DataFrame,一行一个对比,列:
            base / axis / kind / level:底座、轴、改动类型、翻转档或关闸档。
            est, se, z, p:两年合并(`years` 各折之和)的 r_X − r_Y、按股线性化 SE、est/se、双侧 p。
            q_bh, survive:全族 BH q 值;q_bh ≤ q。
            est_<年>, se_<年>, z_<年>:只用该年折算的同一对比。
            z_int, flag_year:年交互 z = (e_末年 − e_首年) / hypot(se_首年, se_末年);|z_int| > 2。
            cochran_p, flag_time:各时间窗分别算 est/se 后的 Cochran Q 的 p(可用窗 < 2 为 nan);p < 0.05。
            ni_lower, ni_pass:仅 gate_off 有意义——删闸非劣效单侧 95% 下界 est − 1.645·se,
                ≥ −delta 为通过;d_flip 行 ni_lower 为 nan、ni_pass 为 False。
            keep_ratio:买点保留比例 = N(改后格) / N(对照格),两年合并。gate_off 即 N(关)/N(开)。
            did_est, did_se, did_z:差中差 (X_working − Y_working) − (X_wide − Y_wide),同一改动在两个
                底座上的效应之差,两年合并;只填在 working 行,wide 行为 nan。
        probes: DataFrame[axis_a, level_a, axis_b, level_b, est, se, z]。工作点上任意两个不同轴的单处改动
            (检测参数翻转、在役闸关闸)同时改的交互 f_ab − f_a − f_b + f_0,两年合并。
        joint_axes: 工作点上有对比幸存的轴(按族顺序),再加交互兜底带入的轴——探针 |z| ≥ 2 且其中
            一方的轴已幸存时,另一方的轴也进。
        level: 工作点格两年合并 {"r", "se_level", "n_dir", "deff", "n_bars"}:首次穿越率、按股线性化 SE、
            定向 bar 数 ΣD、设计效应 (SE / √(r(1−r)/ΣD))²、四态 bar 总数 ΣN。
        stability: {"inclusion_freq": {轴: 频率}, "set_repro": 频率, "B": B}。每个副本按股
            multinomial 抽权重 w(S 只股等概率抽 S 次),用加权每股和重算全族 est、se、z、BH:
            r_k = Σw·U / Σw·D;SE = √(n/(n−1)·Σ_s w_s·T_s²),n = 涉及格里 N>0 且 w>0 的股数。
            inclusion_freq = 该轴在工作点上有对比幸存的副本比例;set_repro = 工作点幸存轴集合与原样本
            完全相同的副本比例。
        settings: {"years", "q", "delta", "m", "n_probes", "detect_axes", "pred_axes", "spec"}。
    """
    if prep_year.combo_levels != prep_win.combo_levels or prep_year.pred_specs != prep_win.pred_specs:
        raise ValueError("screen_core(): prep_year 与 prep_win 的轴定义不一致,应来自同一张长表、同一套档位")
    missing = [y for y in years if y not in prep_year.folds]
    if missing or not years:
        raise ValueError(f"screen_core(): years {years} 须非空且都在 prep_year.folds {prep_year.folds} 里")
    combo_levels, pred_specs = prep_year.combo_levels, prep_year.pred_specs
    dz = design_cells(spec, combo_levels, pred_specs, pair_probes=pair_probes)
    fam, coords, n_fam_cells, w0, pairs = dz["family"], dz["coords"], dz["n_family_cells"], dz["working"], dz["pairs"]

    U, D, N = RC.stock_sums(prep_year, coords, "per_fold")
    yi = [prep_year.folds.index(y) for y in years]
    Up, Dp, Np = (A[:, :, yi].sum(-1) for A in (U, D, N))

    rows = []
    for f in fam:
        ids, coefs = [f["xi"], f["yi"]], [1.0, -1.0]
        c = _contrast(Up, Dp, Np, ids, coefs)
        row = dict(base=f["base"], axis=f["axis"], kind=f["kind"], level=f["level"],
                   est=c["est"], se=c["se"], z=c["z"], p=_p_two_sided(c["z"]))
        for j, y in zip(yi, years):
            cy = _contrast(U[:, :, j], D[:, :, j], N[:, :, j], ids, coefs)
            row[f"est_{y}"], row[f"se_{y}"], row[f"z_{y}"] = cy["est"], cy["se"], cy["z"]
        e0, e1 = row[f"est_{years[0]}"], row[f"est_{years[-1]}"]
        s0, s1 = row[f"se_{years[0]}"], row[f"se_{years[-1]}"]
        row["z_int"] = (e1 - e0) / np.hypot(s0, s1) if len(years) > 1 else float("nan")
        row["flag_year"] = bool(abs(row["z_int"]) > Z_FLAG)
        nx, ny = Np[:, f["xi"]].sum(), Np[:, f["yi"]].sum()
        row["keep_ratio"] = float(nx / ny) if ny > 0 else float("nan")
        if f["kind"] == "gate_off":
            row["ni_lower"] = row["est"] - NI_Z * row["se"]
            row["ni_pass"] = bool(row["ni_lower"] >= -delta)
        else:
            row["ni_lower"], row["ni_pass"] = float("nan"), False
        rows.append(row)
    df = pd.DataFrame(rows)
    df["level"] = pd.Series([f["level"] for f in fam], dtype=object)
    df["q_bh"] = bh(df["p"].to_numpy())
    df["survive"] = df["q_bh"] <= q

    # 差中差:同一改动在 working 与 wide 两底座上的效应之差
    did = {k: np.full(len(fam), np.nan) for k in ("did_est", "did_se", "did_z")}
    wide_of = {(f["axis"], f["kind"], f["level"]): f for f in fam if f["base"] == "wide"}
    for i, f in enumerate(fam):
        if f["base"] != "working":
            continue
        g = wide_of[(f["axis"], f["kind"], f["level"])]
        c = _contrast(Up, Dp, Np, [f["xi"], f["yi"], g["xi"], g["yi"]], [1.0, -1.0, -1.0, 1.0])
        did["did_est"][i], did["did_se"][i], did["did_z"][i] = c["est"], c["se"], c["z"]
    for k, v in did.items():
        df[k] = v

    # 时间窗 Cochran Q
    Uw, Dw, Nw = RC.stock_sums(prep_win, coords[:n_fam_cells], "per_fold")
    cp = []
    for f in fam:
        ew, sw = [], []
        for w in range(Uw.shape[2]):
            c = _contrast(Uw[:, :, w], Dw[:, :, w], Nw[:, :, w], [f["xi"], f["yi"]], [1.0, -1.0])
            ew.append(c["est"]); sw.append(c["se"])
        res = cochran_q(ew, sw)
        cp.append(res["p"] if res else float("nan"))
    df["cochran_p"] = cp
    df["flag_time"] = df["cochran_p"] < P_TIME
    del Uw, Dw, Nw

    # 两两交互探针 + 交互兜底
    prow = []
    for a, b, ab in pairs:
        c = _contrast(Up, Dp, Np, [ab, a["xi"], b["xi"], w0], [1.0, -1.0, -1.0, 1.0])
        prow.append(dict(axis_a=a["axis"], level_a=a["level"], axis_b=b["axis"], level_b=b["level"],
                         est=c["est"], se=c["se"], z=c["z"]))
    probes = pd.DataFrame(prow, columns=["axis_a", "level_a", "axis_b", "level_b", "est", "se", "z"])
    for k in ("level_a", "level_b"):
        probes[k] = pd.Series([p[k] for p in prow], dtype=object)
    work = df["base"] == "working"
    survived = list(dict.fromkeys(df.loc[work & df["survive"], "axis"]))
    joint = joint_with_interactions(survived, [(p["axis_a"], p["axis_b"], p["z"]) for p in prow])

    lv = level_se(Up[:, w0], Dp[:, w0], Np[:, w0])
    level = {"r": lv["r"], "se_level": lv["se"], "n_dir": int(lv["n_dir"]), "deff": lv["deff"],
             "n_bars": int(Np[:, w0].sum())}

    fam_ids = np.array([[f["xi"], f["yi"]] for f in fam])
    stability = _stability(Up[:, :n_fam_cells], Dp[:, :n_fam_cells], Np[:, :n_fam_cells], fam_ids,
                           df["axis"].to_numpy(), work.to_numpy(), set(survived), q=q, B=B, seed=seed)

    settings = {"years": list(years), "q": q, "delta": delta, "m": len(fam), "n_probes": len(prow),
                "detect_axes": list(combo_levels), "pred_axes": [c for c, _, _ in pred_specs], "spec": asdict(spec)}
    return {"contrasts": df, "probes": probes, "joint_axes": joint, "level": level,
            "stability": stability, "settings": settings}


def _stability(Up, Dp, Np, fam_ids, axes, working, survived: set, *, q: float, B: int, seed: int) -> dict:
    """按股 multinomial bootstrap 重做全族 BH(定义见 `screen_core` 的 stability 说明)。

    Up/Dp/Np: (S, K) 两年合并每股和(K = 对比族用到的格);fam_ids: (m, 2) 每个对比的 (改后格, 对照格) 列;
    axes / working: 每个对比的轴名、是否工作点行;survived: 原样本的工作点幸存轴集合。
    """
    S = Up.shape[0]
    W = np.random.default_rng(seed).multinomial(S, np.full(S, 1.0 / S), size=B).astype(float)
    axis_list = list(dict.fromkeys(axes))
    hits = dict.fromkeys(axis_list, 0)
    same = 0
    for got in survivors_under_weights(Up, Dp, Np, fam_ids, axes, W, q=q, working=working):
        for a in got:
            hits[a] += 1
        same += got == survived
    return {"inclusion_freq": {a: hits[a] / B for a in axis_list}, "set_repro": same / B, "B": B}


def survivors_under_weights(Up, Dp, Np, fam_ids, axes, W, *, q: float, working=None) -> list[set]:
    """按给定的按股权重重做全族 BH,每个副本给出一个幸存轴集合。

    参数:
        Up/Dp/Np: (S, K) 两年合并每股和(K = 对比族用到的格)。
        fam_ids: (m, 2) 每个对比的 (改后格, 对照格) 列下标。
        axes: (m,) 每个对比的轴名。
        W: (b, S) 按股权重,每行一个副本(全 1 即原样本)。
        q: BH 幸存阈值。
        working: (m,) 布尔,只把这些对比的轴计入幸存集合(筛选里 = 工作点行);None = 全部对比。
            BH 始终在全族 m 个对比上做,working 只决定哪些幸存对比算数。
    每个副本:est、SE 按 `_boot_stats` 的加权公式,z = est/se,双侧 p,全族 BH,q 值 ≤ q 即幸存。
    返回长度 b 的列表,第 i 个元素 = 第 i 个副本的幸存轴集合。
    """
    S, K = np.shape(Up)
    fam_ids = np.asarray(fam_ids)
    m = len(fam_ids)
    C = np.zeros((m, K))
    C[np.arange(m), fam_ids[:, 0]] += 1.0
    C[np.arange(m), fam_ids[:, 1]] -= 1.0
    axes = np.asarray(axes, dtype=object)
    working = np.ones(m, bool) if working is None else np.asarray(working, bool)
    W = np.atleast_2d(np.asarray(W, float))
    out = []
    step = max(1, _STAB_CHUNK_BYTES // (8 * S * max(K, m)))
    for b0 in range(0, len(W), step):
        est, se = _boot_stats(Up, Dp, Np, C, W[b0:b0 + step])
        with np.errstate(divide="ignore", invalid="ignore"):
            z = np.where(se > 0, est / se, np.nan)
        p = np.where(np.isfinite(z), 2 * stats.norm.sf(np.abs(z)), np.nan)
        out += [set(axes[working & (bh(pb) <= q)]) for pb in p]
    return out


def joint_axes_under_weights(prep_year, spec: ScreenSpec, W, *, years: list, q: float,
                             pair_probes: bool = True) -> list[set]:
    """按给定的按股权重把筛选的挑选部分重做一遍,每个副本给出「下一步一起调」的轴集合。

    定义与 `screen_core` 的 joint_axes 相同(工作点幸存轴 ∪ 交互兜底),只是每股和按 W 加权:幸存判定走
    `survivors_under_weights`,两两探针的 z 走 `_boot_stats`。W 为一行全 1 时,结果(作集合)等于
    `screen_core` 的 joint_axes。
    参数:
        prep_year / spec / years / q / pair_probes: 同 `screen_core`。
        W: (b, prep_year.n_sym) 按 prep_year 的 symbol 码对齐的按股权重。
    返回长度 b 的集合列表。
    """
    combo_levels, pred_specs = prep_year.combo_levels, prep_year.pred_specs
    W = np.atleast_2d(np.asarray(W, float))
    if W.shape[1] != prep_year.n_sym:
        raise ValueError(f"joint_axes_under_weights(): W 的列数 {W.shape[1]} 应等于股票数 {prep_year.n_sym}")
    dz = design_cells(spec, combo_levels, pred_specs, pair_probes=pair_probes)
    fam, nf, w0, pairs = dz["family"], dz["n_family_cells"], dz["working"], dz["pairs"]
    U, D, N = RC.stock_sums(prep_year, dz["coords"], "per_fold")
    yi = [prep_year.folds.index(y) for y in years]
    Up, Dp, Np = (A[:, :, yi].sum(-1) for A in (U, D, N))
    surv = survivors_under_weights(Up[:, :nf], Dp[:, :nf], Np[:, :nf], [[f["xi"], f["yi"]] for f in fam],
                                   [f["axis"] for f in fam], W, q=q, working=[f["base"] == "working" for f in fam])
    if not pairs:
        return surv
    S, K = Up.shape
    P = np.zeros((len(pairs), K))
    for j, (a, b, ab) in enumerate(pairs):
        np.add.at(P[j], [ab, a["xi"], b["xi"], w0], [1.0, -1.0, -1.0, 1.0])
    out = []
    step = max(1, _STAB_CHUNK_BYTES // (8 * S * max(K, len(pairs))))
    for b0 in range(0, len(W), step):
        est, se = _boot_stats(Up, Dp, Np, P, W[b0:b0 + step])
        with np.errstate(divide="ignore", invalid="ignore"):
            z = np.where(se > 0, est / se, np.nan)
        for i, zb in enumerate(z):
            probes = [(a["axis"], b["axis"], zb[j]) for j, (a, b, _) in enumerate(pairs)]
            out.append(set(joint_with_interactions(sorted(surv[b0 + i]), probes)))
    return out


def _boot_stats(Up, Dp, Np, C, W):
    """加权每股和上的对比估计与按股线性化 SE(W 全 1 时与逐个对比调 `ratio_contrast` 的结果相同)。

    参数:Up/Dp/Np (S, K) 每股和;C (m, K) 对比系数;W (b, S) 按股权重。
    公式:r_k = Σ_s w_s·U_{k,s} / Σ_s w_s·D_{k,s};E_{k,s} = (U_{k,s} − r_k·D_{k,s}) / Σ_s w_s·D_{k,s};
        T_{j,s} = Σ_k C_{jk}·E_{k,s};est_j = Σ_k C_{jk}·r_k(只加系数非零的格);
        SE_j = √(n_j/(n_j−1)·Σ_s w_s·T_{j,s}²),n_j = 在对比 j 的涉及格里 N>0 且 w_s>0 的股数(< 2 时 nan)。
    返回 (est, se),形状均为 (b, m)。
    """
    Uf, Df = np.asarray(Up, float), np.asarray(Dp, float)
    W = np.atleast_2d(np.asarray(W, float))
    nz = C != 0
    present = ((np.asarray(Np) > 0).astype(float) @ nz.T.astype(float)) > 0     # (S, m)
    with np.errstate(divide="ignore", invalid="ignore"):
        Dw = W @ Df                                                               # (b, K)
        r = (W @ Uf) / Dw
        E = np.nan_to_num((Uf[None] - r[:, None, :] * Df[None]) / Dw[:, None, :], nan=0.0, posinf=0.0, neginf=0.0)
        T = E @ C.T                                                               # (b, S, m)
        n = (W > 0).astype(float) @ present.astype(float)                        # (b, m)
        se = np.where(n >= 2, np.sqrt(n / np.maximum(n - 1, 1) * np.einsum("bs,bsm->bm", W, T ** 2)), np.nan)
    est = np.empty((len(W), len(C)))
    for j in range(len(C)):
        k = np.flatnonzero(nz[j])
        est[:, j] = r[:, k] @ C[j, k]
    return est, se

def segments_changed(shards, segment_cols, cell_a: dict, cell_b: dict, combo_levels: dict, pred_specs: list,
                     fold_col: str, folds: list) -> dict:
    """两格的买点事件集合差:格 a 有而格 b 没有的(dropped)、格 b 有而格 a 没有的(added),逐折计数。

    参数:
        shards: 长表 parquet 分片路径(分片之间 symbol 不相交,逐片算差再相加)。
        segment_cols: 买点事件键列。买点事件 = (symbol, 折, 买点事件键)。
        cell_a, cell_b: {轴: 档值},键同 `region_core.cell_index`。
        combo_levels, pred_specs, fold_col, folds: 同 `region_core.prepare`。
    过滤语义同 `region_core.prepare`:检测参数列精确等于该格档值;谓词列经 `pred_level_index` 取最紧的
    满足档,档号 ≥ 格的档号即过闸;折不在 folds 里的行丢弃。一个买点事件只要有一行过某格就属于该格。
    返回 {"dropped": {折: n}, "added": {折: n}}。
    """
    ia = RC.cell_index(combo_levels, pred_specs, cell_a)
    ib = RC.cell_index(combo_levels, pred_specs, cell_b)
    nc = len(combo_levels)
    seg = list(segment_cols)
    cols = list(dict.fromkeys(list(combo_levels) + [c for c, _, _ in pred_specs] + [fold_col, "symbol"] + seg))
    dropped = dict.fromkeys(folds, 0)
    added = dict.fromkeys(folds, 0)
    for sp in shards:
        df = pd.read_parquet(sp, columns=cols)
        fold = pd.Categorical(df[fold_col], categories=folds).codes
        codes = ([pd.Categorical(df[c], categories=lv).codes for c, lv in combo_levels.items()]
                 + [RC.pred_level_index(df[c].values, op, lv) for c, op, lv in pred_specs])
        keys = pd.DataFrame({"symbol": np.asarray(df["symbol"], dtype=object), "_fold": fold,
                             **{c: df[c].to_numpy() for c in seg}})

        def members(idx):
            m = fold >= 0
            for j, (x, i) in enumerate(zip(codes, idx)):
                m &= (x == i) if j < nc else (x >= i)
            return keys[m].drop_duplicates()

        both = members(ia).merge(members(ib), how="outer", indicator=True)
        for code, f in enumerate(folds):
            at = both["_fold"] == code
            dropped[f] += int((at & (both["_merge"] == "left_only")).sum())
            added[f] += int((at & (both["_merge"] == "right_only")).sum())
    return {"dropped": dropped, "added": added}


def pool_drift(arm_a_rows, arm_b_rows, base_rows, *, delta: float, **edge_kw) -> dict:
    """换池漂移:两臂各自对逐日基线做层匹配后,匹配基线率之差。

    参数:
        arm_a_rows, arm_b_rows: 两臂的买点行 DataFrame[symbol, date, M, up, down, both](计数)。
        base_rows: 逐日基线行,同列。
        delta: 最小关心改进(比例);|漂移| ≥ delta/2 标旗。
        edge_kw: 原样传给 `edge_core.edge_delta`(time_key、cut、B、seed、min_dir、win_days)。
    定义:两臂原始率差 rate_a − rate_b = (est_a − est_b) + (base_a − base_b),其中 est = edge_delta 的
        优势估计、base = 层匹配基线率(matched_base_rate)。漂移 = base_a − base_b,即两臂的差里有多少
        只是因为换了一批波动层 / 交易日构成不同的股票。
    返回 {"available": True, "drift", "flag", "a": edge_delta 输出, "b": edge_delta 输出};
        任一份输入缺 M 列 → {"available": False}。
    """
    if any("M" not in rows.columns for rows in (arm_a_rows, arm_b_rows, base_rows)):
        return {"available": False}
    a = edge_core.edge_delta(arm_a_rows, base_rows, **edge_kw)
    b = edge_core.edge_delta(arm_b_rows, base_rows, **edge_kw)
    drift = a["matched_base_rate"] - b["matched_base_rate"]
    return {"available": True, "drift": drift, "flag": bool(abs(drift) >= delta / 2), "a": a, "b": b}


# ── 报告渲染(业务语言) ──

GATE_DROP, GATE_KEEP, GATE_HOLD = "删了不亏", "有用", "说不清"


def gate_outcome(row) -> str:
    """在役闸关闸对比(工作点行)的三种结局。

    - 「删了不亏」:ni_pass(关 − 开的单侧 95% 下界 ≥ −delta);
    - 「有用」:没通过非劣效,且对比幸存、关掉变差(est < 0);
    - 「说不清」:其余——关掉可能亏得超过 delta,又分辨不出闸确实有用,维持现值。
    """
    if row["ni_pass"]:
        return GATE_DROP
    if row["survive"] and row["est"] < 0:
        return GATE_KEEP
    return GATE_HOLD


def _v(x) -> str:
    """档值的显示:None → 不设;数字用最短表示。"""
    if x is None:
        return "不设"
    return f"{x:g}" if isinstance(x, (int, float, np.integer, np.floating)) else str(x)


def _pt(x, signed: bool = True) -> str:
    """比例 → 点(两位小数)。"""
    if x is None or not np.isfinite(x):
        return "—"
    return f"{x * 100:+.2f}" if signed else f"{x * 100:.2f}"


def _change(axis, level, working: dict, pred_axes, base: str = "working") -> str:
    """一处改动的人话描述;宽进点上的改动加前缀说明是在闸全关掉的情况下比的。"""
    cur = _v(working[axis])
    if axis in pred_axes:
        return f"{'其他闸全关掉时' if base == 'wide' else ''}关掉 `{axis}`({cur} → {_v(level)})"
    return f"{'闸全关掉时 ' if base == 'wide' else ''}`{axis}` {cur} → {_v(level)}"


def _years_text(row, years) -> str:
    return "、".join(f"{y} 年 {_pt(row[f'est_{y}'])}" for y in years)


def render_report(result: dict, *, app: str, window: str, delta: float) -> str:
    """把 `screen_core` 的结果渲染成给用户看的中文 markdown。

    只说业务层的话:改了什么、首次穿越率变了几个点、分辨不分辨得出、删闸亏不亏、哪里需要留意。
    contrasts 里若另有调用方补上的列,也一并渲染:
        dropped_<年> / added_<年>:`segments_changed` 的买点事件增减(只填幸存对比与报告行);
        drift / flag_drift:`pool_drift` 的换池漂移与旗标。
    """
    df, st = result["contrasts"], result["settings"]
    working, years, q = st["spec"]["working"], st["years"], st["q"]
    pred_axes = set(st["pred_axes"])
    name = lambda r: _change(r["axis"], r["level"], working, pred_axes, r["base"])  # noqa: E731
    k = int(df["survive"].sum())
    L = [f"## {app} · {window} · 筛选结果", "",
         f"在现在这套参数附近逐个改一处,一共比了 {len(df)} 个改动,{k} 个分辨得出。"
         f"每个改动在「现在这套闸」和「闸全关掉」下各比一次;同一段买点只计一次,误差按股票算"
         f"(同一只股票的多段买点不当成互相独立);改进不到 {delta * 100:g} 点不算数。"]

    L += ["", "### 分辨得出的改动", ""]
    surv = df[df["survive"]]
    if surv.empty:
        L.append("没有。")
    for _, r in surv.iterrows():
        keep_of = "改前" if r["kind"] == "d_flip" else "闸开着时"
        s = (f"- {name(r)}:首次穿越率 {_pt(r['est'])} 点(误差 ±{_pt(r['se'], False)}),{_years_text(r, years)};"
             f"买点数是{keep_of}的 {r['keep_ratio'] * 100:.0f}%")
        if all(f"dropped_{y}" in df.columns for y in years) and pd.notna(r.get(f"dropped_{years[0]}")):
            s += ";涉及的买点:" + "、".join(
                f"{y} 年掉出 {int(r[f'dropped_{y}'])} 段、新增 {int(r[f'added_{y}'])} 段" for y in years)
        if r["q_bh"] > q * BARELY_FRAC:
            s += "。刚过线"
        L.append(s + "。")

    gates = df[(df["base"] == "working") & (df["kind"] == "gate_off")]
    if not gates.empty:
        L += ["", f"### 现在这几道闸:删了亏不亏(最多能容忍差 {delta * 100:g} 点)", "",
              "| 闸 | 关掉后首次穿越率 | 买点数 | 结论 |", "|---|---|---|---|"]
        for _, r in gates.iterrows():
            out, worst = gate_outcome(r), -r["ni_lower"]
            if out == GATE_DROP:
                text = (f"删了不亏:关掉最坏也只差 {worst * 100:.2f} 点" if worst > 0
                        else "删了不亏:关掉最坏也不会变差")
            elif out == GATE_KEEP:
                text = "有用:关掉明显变差,保留"
            else:
                text = f"说不清:关掉最坏可能差 {_pt(worst, False)} 点,超过能容忍的,维持现值"
            L.append(f"| {name(r)} | {_pt(r['est'])} 点(误差 ±{_pt(r['se'], False)}) "
                     f"| 是闸开着时的 {r['keep_ratio'] * 100:.0f}% | {text} |")

    notes = []
    wide_est = {(r["axis"], r["kind"], r["level"]): r["est"] for _, r in df[df["base"] == "wide"].iterrows()}
    for _, r in df.iterrows():
        nm = name(r)
        if r["flag_year"]:
            notes.append(f"{nm}:两年明显不一样({_years_text(r, years)} 点)")
        if r["flag_time"]:
            notes.append(f"{nm}:时好时坏,不同时间段的效果差别超出误差")
        if r["base"] == "working" and abs(r["did_z"]) >= Z_FLAG:
            notes.append(f"{nm}:效果依赖其他闸开不开——现在这套闸下 {_pt(r['est'])} 点,"
                         f"闸全关掉时 {_pt(wide_est[(r['axis'], r['kind'], r['level'])])} 点")
        if not r["survive"] and abs(r["z"]) >= Z_FLAG:
            notes.append(f"{nm}:差一点没过线({_pt(r['est'])} 点,误差 ±{_pt(r['se'], False)}),先不动")
        if r["keep_ratio"] < 1 - KEEP_SHRINK:
            notes.append(f"{nm}:买点少了 {(1 - r['keep_ratio']) * 100:.0f}%")
        if "flag_drift" in df.columns and r.get("flag_drift") is True:
            notes.append(f"{nm}:可能换成了另一批波动或行情的股票(相差 {_pt(r['drift'])} 点)")
    if notes:
        L += ["", "### 需要留意", ""] + [f"- {x}" for x in notes]

    probes = result["probes"]
    hot = probes[probes["z"].abs() >= Z_FLAG] if len(probes) else probes
    if len(hot):
        L += ["", "### 一起改时会互相影响", ""]
        for _, p in hot.iterrows():
            L.append(f"- {_change(p['axis_a'], p['level_a'], working, pred_axes)} 与 "
                     f"{_change(p['axis_b'], p['level_b'], working, pred_axes)} 一起改:"
                     f"比两处各自的效果相加多 {_pt(p['est'])} 点(误差 ±{_pt(p['se'], False)})")

    L += ["", "### 下一步一起调", ""]
    survived = set(df.loc[(df["base"] == "working") & df["survive"], "axis"])
    if not result["joint_axes"]:
        L.append("没有要一起调的参数。")
    for a in result["joint_axes"]:
        L.append(f"- `{a}`" + ("" if a in survived else "(本身没分辨出来,但和入选的参数一起改时会互相影响,一并带上)"))

    stab = result["stability"]
    L += ["", "### 稳不稳", "", f"把股票重新抽 {stab['B']} 次、每次重做一遍判断:"]
    for a, fr in stab["inclusion_freq"].items():
        if fr > 0 or a in result["joint_axes"]:
            L.append(f"- `{a}` 被选入的比例 {fr * 100:.0f}%")
    L.append(f"- 选入的参数和这次完全一样的比例 {stab['set_repro'] * 100:.0f}%")

    lv = result["level"]
    eff = lv["n_dir"] / lv["deff"] if lv["deff"] and np.isfinite(lv["deff"]) else float("nan")
    L += ["", "### 现在这套参数的分辨力", "",
          f"现在这套参数下首次穿越率 {lv['r'] * 100:.1f}%,误差 ±{_pt(lv['se_level'], False)} 点;"
          f"{lv['n_bars']} 个买点 bar 里有 {lv['n_dir']} 个在前瞻期内碰到了上下边界。"
          f"同一只股票的买点彼此牵连,这些 bar 大约只相当于 {eff:.0f} 个互不相关的样本。"]
    return "\n".join(L) + "\n"


def draft_fc_rows(result: dict, *, app: str, window: dict | None = None, stock_rule: str | None = None,
                  report: str | None = None) -> str:
    """待验证行草稿:工作点上幸存的检测参数翻转、通过非劣效的删闸,各写一条登记簿条目(markdown)。

    这些是执行端证据,还没经换样本验证;字段按登记簿「待验证条目」格式。screen_core 不知道的项由调用方给:
    window = {"start", "end", "label_horizon"}(买点起止日期、标签前瞻期交易日数)、stock_rule = 股票规则的
    文字说明、report = 筛选报告路径;不给的项写「待填」。没有符合条件的行时返回空串。
    """
    df, st = result["contrasts"], result["settings"]
    working, years, q, delta, m = st["spec"]["working"], st["years"], st["q"], st["delta"], st["m"]
    kv = lambda axes: "、".join(f"`{a}`={_v(working[a])}" for a in axes)  # noqa: E731
    span = (f"买点 {window['start']} 至 {window['end']},标签前瞻期 {window['label_horizon']} 个交易日"
            if window else "起止日期与标签前瞻期待填")
    sample = (f"窗口:买点年份 {'、'.join(years)}({span});股票规则:{stock_rule or '待填'};"
              f"工作点:{kv(st['detect_axes'])};where 设置:{kv(st['pred_axes'])};"
              f"查询次数:{m} 个单处改动 + {st['n_probes']} 个两两组合")
    wide = {(r["axis"], r["kind"], r["level"]): r for _, r in df[df["base"] == "wide"].iterrows()}
    pick = df[(df["base"] == "working")
              & (((df["kind"] == "d_flip") & df["survive"]) | ((df["kind"] == "gate_off") & df["ni_pass"]))]
    out = []
    for _, r in pick.iterrows():
        axis, cur, lvl = r["axis"], _v(working[r["axis"]]), _v(r["level"])
        by_year = "、".join(f"{y} {_pt(r[f'est_{y}'])} ± {_pt(r[f'se_{y}'], False)}(z {r[f'z_{y}']:.2f})" for y in years)
        flags = []
        if r["flag_year"]:
            flags.append(f"⚠ 年交互 z {r['z_int']:.2f}(|z|>{Z_FLAG:g})")
        if r["flag_time"]:
            flags.append(f"⚠ 时间窗异质(Cochran Q p={r['cochran_p']:.3f})")
        if abs(r["did_z"]) >= Z_FLAG:
            w = wide[(axis, r["kind"], r["level"])]
            flags.append(f"⚠ 依赖在役闸:宽进点上 {_pt(w['est'])} ± {_pt(w['se'], False)}pt,"
                         f"差中差 {_pt(r['did_est'])} ± {_pt(r['did_se'], False)}(z {r['did_z']:.2f})")
        unit = "首次穿越率 = up/(up+down+both),同一检测组合内同一买点事件只计一次,按买点 bar 汇总,按股去簇"
        if r["kind"] == "d_flip":
            title = f"[执行端证据] `{axis}` {cur}→{lvl} 改变首次穿越率"
            caliber = f"工作点上只把 `{axis}` 从 {cur} 改为 {lvl} 的配对差(改后 − 改前);{unit};族内 {m} 个对比做 BH(q={q:g})"
            direction = "改后首次穿越率上升" if r["est"] > 0 else "改后首次穿越率下降"
            effect = (f"两年合并 {_pt(r['est'])} ± {_pt(r['se'], False)}pt(z {r['z']:.2f},BH q={r['q_bh']:.3f},幸存"
                      f"{',刚过线' if r['q_bh'] > q * BARELY_FRAC else ''});分年 {by_year};买点保留比例 {r['keep_ratio']:.2f}")
        else:
            title = f"[执行端证据] 删闸 `{axis}`({cur}→{lvl})不亏"
            caliber = (f"工作点上关掉 `{axis}`({cur}→{lvl})的配对差(关 − 开);{unit};"
                       f"删闸判据 = 单侧 95% 下界 est − {NI_Z}·SE ≥ −δ,δ = {delta * 100:g}pt")
            direction = "关掉后首次穿越率不比开着时差出 δ 以上"
            effect = (f"两年合并 {_pt(r['est'])} ± {_pt(r['se'], False)}pt,非劣效下界 {_pt(r['ni_lower'])}pt;"
                      f"分年 {by_year};买点保留比例(关/开){r['keep_ratio']:.2f}")
        out.append("\n".join([
            f"### FC-??? · {title}",
            f"- **app / 轴**:{app} / `{axis}`",
            f"- **口径**:{caliber}",
            f"- **方向**:{direction}",
            f"- **效应量**:{effect}",
            f"- **发现样本**:{sample}",
            "- **原构造目的**:执行端筛选(在工作点附近逐个改一处参数,看哪些改动分辨得出)",
            f"- **已知纠缠/反驳**:{';'.join(flags) if flags else '无旗标'}",
            "- **执行端动作**:未执行",
            "- **状态**:`exploratory`",
            f"- **发现报告**:{report or '待填'}",
        ]))
    return "\n\n".join(out) + ("\n" if out else "")


# ── 编排:tune.screen 的前置检查、落盘与记账 ──

ACTOR = "tune-gates"
SCREEN_DIR_PREFIX = "screen_"
DRIFT_COLS = ("symbol", "date", "M", "up", "down", "both")


def axis_params(cl: dict) -> dict:
    """格坐标的轴键 → 参数键(params.yaml 里的 section.field)。

    检测参数轴的轴键本身就是参数键;谓词轴的轴键是长表列名(node.field),经分类表的 filter_fields /
    where_fields 反查到参数键。报告与账本里给人看的参数名一律用参数键。"""
    from multivar_core import node_col
    out = {k: k for k, kind in cl["kinds"].items() if kind == "D" and k in cl["scan_grid"]}
    fields = [(k, cl["filter_fields"][k]) for k in cl["scan_grid"] if cl["kinds"][k] == "F"]
    fields += [(k, cl["where_fields"][k]) for k in cl["where_levels"]]
    for k, (node, field, _op) in fields:
        col = node_col(node, field)
        if col in out:
            raise ValueError(f"分类表里参数 {out[col]} 与 {k} 落在同一个轴 {col} 上,认不出这个轴对应哪个参数")
        out[col] = k
    return out


def spec_from_classification(cl: dict, working_point: dict | None = None) -> tuple:
    """由分类表推筛选的格定义。返回 (ScreenSpec, 工作点 {参数键: 值},覆盖全部轴)。

    - 工作点 = 分类表记录的工作点(正式参数在全部轴档位上的落点);working_point 给出的参数覆盖对应值
      (删闸后在新工作点上重算用),值必须是该轴档位表里的档。
    - 宽进点:检测参数同工作点,谓词轴取最松档(档位表第 0 档)。
    - 检测参数翻转档:档位表里不等于工作点值的档(只有一档的轴不翻)。
    - 在役闸:工作点值不是最松档的谓词轴,关闸档 = 最松档。
    """
    import study_io as S
    combo, preds = S.derived_axes(cl)
    names = axis_params(cl)
    levels = {names[c]: list(lv) for c, lv in combo.items()}
    levels.update({names[c]: list(lv) for c, _, lv in preds})
    wp = {k: cl["ref_point"][k] for k in levels}
    if working_point:
        unknown = sorted(set(working_point) - set(levels))
        if unknown:
            raise SystemExit(f"指定的工作点里有这个窗口没列的参数 {unknown}(这个窗口的参数: {sorted(levels)})")
        off = {k: v for k, v in working_point.items() if v not in levels[k]}
        if off:
            raise SystemExit("指定的工作点取值不在这个窗口列过的档位上:"
                             + ";".join(f"{k} = {v!r}(可选 {levels[k]})" for k, v in off.items()))
        wp.update(working_point)
    working = {c: wp[names[c]] for c in combo}
    working.update({c: wp[names[c]] for c, _, _ in preds})
    wide = {c: working[c] for c in combo}
    wide.update({c: lv[0] for c, _, lv in preds})
    d_flips = {c: [v for v in lv if v != working[c]] for c, lv in combo.items() if len(lv) > 1}
    gate_offs = {c: lv[0] for c, _, lv in preds if working[c] != lv[0]}
    return ScreenSpec(working=working, wide=wide, d_flips=d_flips, gate_offs=gate_offs), wp


def require_fresh_edge(app: str, window: str) -> dict:
    """机械闸 8:账本里有优势检查记录,且那之后检测代码与标签代码都没变。返回当前四个指纹。"""
    import ledger
    rec = ledger.latest(app, "edge")
    if rec is None:
        raise SystemExit(f"「{app}」还没做过优势检查:不知道这个 pattern 比同一天、同样波动水平的随机买入日好不好,"
                         "也不知道样本能分辨多小的改进。先做优势检查。")
    now = ledger.current_fingerprints(app, window)
    if any(rec[k] != now[k] for k in ("source_fingerprint", "ruler_fingerprint")):
        raise SystemExit("优势检查之后代码变过(检测逻辑或涨跌结果的算法改了),先重做优势检查。")
    return now


def check_consistency(out_dir, cl: dict) -> None:
    """一致性验证红线:验证跑完、全部对上、比过的股票够数,且做验证时的研究声明与标签代码都与现在相同。
    任一不满足 → 人话拒绝。

    验证日志首行记录声明与标签代码的版本,结论行含「mismatch=N,」与三个股数(比过 / 抽到 / 扫描范围)。"""
    import compare_longtable as CL
    import ledger
    log = Path(out_dir) / "compare_longtable.log"
    if not log.exists():
        raise SystemExit("这批扫描结果还没做一致性验证(扫描结果与逐个组合重跑 pattern 是否一致),先做一致性验证。")
    lines = log.read_text(encoding="utf-8").splitlines()
    head = re.match(r"study_fingerprint=(\S+) ruler_fingerprint=(\S+)", lines[0]) if lines else None
    if head is None:
        raise SystemExit("一致性验证的记录认不出是在哪份声明、哪版涨跌结果算法下做的,重做一致性验证。")
    n_bad = cover = None
    for ln in reversed(lines):
        if "mismatch=" in ln:
            try:
                n_bad = int(ln.split("mismatch=")[1].split(",")[0])
            except ValueError:
                pass
            cover = re.search(r"compared_symbols=(\d+) sampled_symbols=(\d+) universe_symbols=(\d+)", ln)
            break
    if n_bad is None:
        raise SystemExit("一致性验证没有跑完(没得出结论),重做一致性验证。")
    if n_bad != 0:
        raise SystemExit(f"一致性验证没通过:有 {n_bad} 处扫描结果和重跑 pattern 对不上,扫描结果不可信,先查清原因。")
    if cover is None:
        raise SystemExit("一致性验证的记录没写比了多少只股票,判断不了抽样够不够,重做一致性验证。")
    n_cmp_syms, n_sampled, n_universe = map(int, cover.groups())
    if not CL.coverage_ok(n_cmp_syms, n_sampled, n_universe):
        raise SystemExit(f"一致性验证只比了 {n_cmp_syms} 只股票,不到 {CL.MIN_SYMBOLS} 只,也没有覆盖这批扫描的全部 "
                         f"{n_universe} 只;抽样太窄,证明不了扫描结果可信,放宽抽样的股票范围后重做一致性验证。")
    if head.group(1) != cl["fingerprints"]["study"]:
        raise SystemExit("一致性验证是在另一份研究声明下做的,和现在这批扫描对不上,重做一致性验证。")
    if head.group(2) != ledger.ruler_fingerprint():
        raise SystemExit("一致性验证之后,涨跌结果或基线的计算代码改过,重做一致性验证。")


def artifact_path(path) -> str:
    """账本 ref 里的产物路径:在仓库内写相对仓库根的路径,否则写绝对路径(账本两种都认)。"""
    import ledger
    p = Path(path).resolve()
    try:
        return str(p.relative_to(ledger.REPO))
    except ValueError:
        return str(p)


def jsonable(x):
    """转成可写进标准 JSON 的值:numpy 标量 → Python 数;NaN / ±inf → None;dict / list / tuple 递归。"""
    if isinstance(x, dict):
        return {str(k): jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, np.ndarray)):
        return [jsonable(v) for v in x]
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, (float, np.floating)):
        return float(x) if np.isfinite(x) else None
    return x


def stock_rule_text(meta: dict) -> str:
    """扫描的股票规则(人话):价格与成交量过滤。"""
    return f"收盘价 {meta['price_min']:g}~{meta['price_max']:g}、成交量 ≥ {meta['volume_min']:g}"


def _preps(shards, combo, preds, fold_col, folds, seg_cols, meta):
    """筛选核要的两份买点事件口径 Prepared:折 = 年;折 = 时间窗号(窗宽由标签前瞻期推出,窗数由数据跨度定)。"""
    prep_year = RC.prepare_shards(shards, combo, preds, fold_col, folds, segment_cols=seg_cols)
    start = meta["start_date"]
    win_days = time_window_days(int(meta["label_horizon"]))
    ends = [d for sp in shards for d in pd.read_parquet(sp, columns=["buy_date"])["buy_date"].agg(["min", "max"])
            if pd.notna(d)]
    _, win_levels = time_window_codes(ends, start, win_days)

    def win_of(s):
        return pd.Series(time_window_codes(s, start, win_days)[0], index=s.index)

    prep_win = RC.prepare_shards(shards, combo, preds, fold_col, win_levels, segment_cols=seg_cols,
                                 fold_from=("buy_date", win_of))
    return prep_year, prep_win


def _event_rows(shards, cells: list, combo_levels, pred_specs, fold_col, folds, segment_cols) -> dict:
    """每个格的买点事件行,同一买点事件只留一行:{格坐标: DataFrame[symbol, date, M, up, down, both]}。

    过滤语义同 `segments_changed`:检测参数列精确等于档值,谓词列取最紧的满足档、档号 ≥ 格的档号即过闸,
    折不在 folds 里的行丢弃。买点事件 = (symbol, 折, 买点事件键),同一事件各行的四态与 M 相同,取第一行。"""
    seg = list(segment_cols)
    idx = {RC.cell_index(combo_levels, pred_specs, lv) for lv in cells}
    nc = len(combo_levels)
    cols = list(dict.fromkeys(list(combo_levels) + [c for c, _, _ in pred_specs]
                              + [fold_col, "symbol", "buy_date", "M", "fp_up", "fp_down", "fp_both"] + seg))
    parts = {ix: [] for ix in idx}
    for sp in shards:
        df = pd.read_parquet(sp, columns=cols)
        fold = pd.Categorical(df[fold_col], categories=folds).codes
        codes = ([pd.Categorical(df[c], categories=lv).codes for c, lv in combo_levels.items()]
                 + [RC.pred_level_index(df[c].values, op, lv) for c, op, lv in pred_specs])
        for ix in idx:
            m = fold >= 0
            for j, (x, i) in enumerate(zip(codes, ix)):
                m &= (x == i) if j < nc else (x >= i)
            sub = df.loc[m].assign(_fold=fold[m]).drop_duplicates(["symbol", "_fold"] + seg)
            parts[ix].append(pd.DataFrame({
                "symbol": np.asarray(sub["symbol"], dtype=object), "date": sub["buy_date"].to_numpy(),
                "M": sub["M"].to_numpy(float), "up": sub["fp_up"].to_numpy(), "down": sub["fp_down"].to_numpy(),
                "both": sub["fp_both"].to_numpy()}))
    return {ix: pd.concat(v, ignore_index=True) for ix, v in parts.items()}


def _annotate(res: dict, spec: ScreenSpec, shards, seg_cols, combo, preds, fold_col, folds, *, base_dir,
              delta: float) -> dict:
    """给幸存对比与全部在役闸行补买点事件增减(dropped_<年> / added_<年>);优势检查的逐日基线存在且扫描结果
    有 M 列时,再给这些行补换池漂移(drift / flag_drift)。原地改 res["contrasts"],其余行留空。

    返回 {"available": 换池漂移查不查得了, "reason": 查不了的原因(人话)或 None}。"""
    df = res["contrasts"]
    fam = _family(spec, combo, preds)                 # 与 contrasts 同序
    rows = [i for i, f in enumerate(fam) if bool(df.at[i, "survive"]) or f["kind"] == "gate_off"]
    for y in folds:
        df[f"dropped_{y}"] = np.nan
        df[f"added_{y}"] = np.nan
    for i in rows:
        ch = segments_changed(shards, seg_cols, fam[i]["y"], fam[i]["x"], combo, preds, fold_col, folds)
        for y in folds:
            df.at[i, f"dropped_{y}"], df.at[i, f"added_{y}"] = ch["dropped"][y], ch["added"][y]
    base_parts = sorted(Path(base_dir).glob("part-*.parquet"))
    missing = [why for why, bad in (("没有优势检查的逐日基线", not base_parts),
                                    ("这批扫描结果没有记录波动率", "M" not in pq.read_schema(shards[0]).names)) if bad]
    if missing:
        return {"available": False, "reason": "、".join(missing)}
    if not rows:
        return {"available": True, "reason": None}
    ev = _event_rows(shards, [fam[i][k] for i in rows for k in ("x", "y")], combo, preds, fold_col, folds, seg_cols)
    base = pd.concat([pd.read_parquet(p, columns=list(DRIFT_COLS)) for p in base_parts], ignore_index=True)
    df["drift"] = np.nan
    df["flag_drift"] = pd.Series([None] * len(df), dtype=object)
    for i in rows:
        x = ev[RC.cell_index(combo, preds, fam[i]["x"])]
        y = ev[RC.cell_index(combo, preds, fam[i]["y"])]
        d = pool_drift(x, y, base, delta=delta, B=0)      # 漂移只用层匹配基线率的点估计,不做 bootstrap
        if d["available"]:
            df.at[i, "drift"], df.at[i, "flag_drift"] = d["drift"], bool(d["flag"])
    return {"available": True, "reason": None}


def _named(res: dict, names: dict) -> dict:
    """把结果里的轴键(谓词轴是长表列名)换成参数键,供渲染与落盘。"""
    nm = lambda a: names.get(a, a)  # noqa: E731
    df = res["contrasts"].copy()
    df["axis"] = df["axis"].map(nm)
    pr = res["probes"].copy()
    pr["axis_a"], pr["axis_b"] = pr["axis_a"].map(nm), pr["axis_b"].map(nm)
    st = dict(res["settings"])
    st["spec"] = {k: {nm(a): v for a, v in d.items()} for k, d in st["spec"].items()}
    st["detect_axes"] = [nm(a) for a in st["detect_axes"]]
    st["pred_axes"] = [nm(a) for a in st["pred_axes"]]
    stab = dict(res["stability"])
    stab["inclusion_freq"] = {nm(a): v for a, v in stab["inclusion_freq"].items()}
    return {**res, "contrasts": df, "probes": pr, "joint_axes": [nm(a) for a in res["joint_axes"]],
            "settings": st, "stability": stab}


def run(app: str, window: str, cfg, *, delta: float, working_point: dict | None = None,
        apps_dir=None, out_root=None, calendar=None) -> dict:
    """tune.screen 的编排:前置检查 → 筛选核 → 补买点事件增减与换池漂移 → 落盘 → 写账本。

    参数:
        app / window: 被筛选的 app 与窗口。
        cfg: Settings(用 fold_col、folds、screen_fdr_q、b_boot、boot_seed)。
        delta: 最小关心改进(比例,0.02 = 2 点)。
        working_point: {参数键: 值},覆盖工作点里的部分参数(须在档位表上)。删闸之后在新工作点上重算用,
            筛选的检测组合都已在扫描结果里,不需要新扫描。
        apps_dir / out_root / calendar: 研究声明根目录(缺省 skill 的 apps/)、输出根目录(缺省
            outputs/tune_gates)、交易日历(缺省数据目录的日历)。单测注入用。
    前置(依次检查,任一不满足 → 人话拒绝,不读标签、不写任何东西):
        1. 机械闸 8:账本里有优势检查记录,且那之后检测代码与标签代码没变(`require_fresh_edge`);
        2. 分类表与研究声明一致、扫描结果与分类表一致;一致性验证跑完且全部对上(`check_consistency`);
        3. 窗口声明的工作点覆盖全部轴(旧窗口只写了检测参数,不能筛选);
        4. 确认窗守卫放行本窗口买点区间的标签读取。
    落盘到 <输出根>/<app>/<window>/screen_<工作点哈希前 8 位>/:report.md、contrasts.csv、probes.csv、
    fc_drafts.md、result.json,给人看的参数名一律是参数键。最后写一条 select 记录(ref = 报告与对比表的
    sha256;n_looks = 对比数 + 探针数)。
    返回 {"out_dir", "report", "working_point", "survivors", "joint_axes", "m", "n_probes"}。
    """
    import holdout
    import ledger
    import study_io as S
    apps_dir = Path(apps_dir) if apps_dir else S.APPS_DIR
    root = Path(out_root) if out_root else S.REPO / "outputs" / "tune_gates"
    out = root / app / window
    lt = out / "longtable"

    fps = require_fresh_edge(app, window)
    cl = S.load_classification(app, window, apps_dir)
    S.check_study_matches(cl, S.study_path(app, window, apps_dir))
    meta = S.load_run_meta(lt)
    if meta.get("app") != app:
        raise SystemExit(f"这批扫描结果属于「{meta.get('app')}」,不是「{app}」,拒绝按「{app}」的声明去切它。")
    S.check_run_matches_classification(meta, cl)
    check_consistency(out, cl)
    if cl.get("ref_point_scope") != "all":
        raise SystemExit("这个窗口是旧版声明:工作点只写了检测参数、没写各道闸的现值,不能在它上面做筛选。"
                         "请按现在的正式参数重新落地这个窗口的声明。")
    holdout.guard_label_access(app, meta["start_date"], meta["end_date"], "screen", calendar=calendar)

    spec, wp = spec_from_classification(cl, working_point)
    if not spec.d_flips and not spec.gate_offs:
        raise SystemExit("这个工作点附近没有可比的改动:检测参数都只有一档,也没有开着的闸。")
    names = axis_params(cl)
    combo, preds = S.derived_axes(cl)
    shards = sorted(lt.glob("part-*.parquet"))
    if not shards:
        raise SystemExit("这个窗口还没有扫描结果,先扫描。")
    seg_cols = S.segment_cols(cl, pq.read_schema(shards[0]).names)
    folds = list(cfg.folds)
    prep_year, prep_win = _preps(shards, combo, preds, cfg.fold_col, folds, seg_cols, meta)
    res = screen_core(prep_year, prep_win, spec, years=folds, q=cfg.screen_fdr_q, delta=delta,
                      B=cfg.b_boot, seed=cfg.boot_seed)
    del prep_year, prep_win
    drift = _annotate(res, spec, shards, seg_cols, combo, preds, cfg.fold_col, folds,
                      base_dir=root / app / "edge" / "baseline", delta=delta)

    named = _named(res, names)
    st, c = named["settings"], named["contrasts"]
    d = out / f"{SCREEN_DIR_PREFIX}{S.canonical_hash(wp)[:8]}"
    d.mkdir(parents=True, exist_ok=True)
    report, contrasts = d / "report.md", d / "contrasts.csv"
    text = render_report(named, app=app, window=window, delta=delta)
    if not drift["available"]:
        text += ("\n### 换没换一批股票\n\n这次查不了「改动之后是不是换成了另一批波动或行情的股票」:"
                 f"{drift['reason']}。\n")
    report.write_text(text, encoding="utf-8")
    c.to_csv(contrasts, index=False)
    named["probes"].to_csv(d / "probes.csv", index=False)
    win = {"start": str(meta["start_date"]), "end": str(meta["end_date"])}
    (d / "fc_drafts.md").write_text(draft_fc_rows(
        named, app=app, window={**win, "label_horizon": meta["label_horizon"]},
        stock_rule=stock_rule_text(meta), report=artifact_path(report)), encoding="utf-8")

    work = c["base"] == "working"
    survivors = list(dict.fromkeys(c.loc[work & c["survive"], "axis"]))
    summary = {"tool": "screen", "working_point": wp, "delta": delta, "q": st["q"], "m": st["m"],
               "n_probes": st["n_probes"], "years": folds, "survivors": survivors, "joint_axes": named["joint_axes"],
               "ni_lower": {r["axis"]: r["ni_lower"] * 100 for _, r in c[work & (c["kind"] == "gate_off")].iterrows()},
               "stability": named["stability"], "drift_available": drift["available"],
               "drift_unavailable_reason": drift["reason"], "window_name": window, "out_dir": artifact_path(d)}
    (d / "result.json").write_text(json.dumps(jsonable({
        **summary, "level": named["level"], "settings": st, "contrasts": c.to_dict("records"),
        "probes": named["probes"].to_dict("records")}), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    rec = ledger.make_record(
        "select", app, actor=ACTOR, round=None,
        axes=list(dict.fromkeys(names[a] for a in [*spec.d_flips, *spec.gate_offs])),
        window=win, label_horizon=int(meta["label_horizon"]), head_buffer=int(meta["head_buffer"]), **fps,
        n_looks=int(st["m"] + st["n_probes"]),
        ref={artifact_path(report): ledger.sha256_file(report), artifact_path(contrasts): ledger.sha256_file(contrasts)},
        data=jsonable(summary))
    ledger.append(rec)
    return {"out_dir": str(d), "report": str(report), "working_point": wp, "survivors": survivors,
            "joint_axes": named["joint_axes"], "m": st["m"], "n_probes": st["n_probes"]}
