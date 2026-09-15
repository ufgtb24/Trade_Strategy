# -*- coding: utf-8 -*-
"""联合识别(`tune.find`)与单格查询记账(`tune.cell`)。

联合识别:筛选之后,把筛选里分辨得出的参数、以及和它们一起改时会互相影响的参数放在一张网格上一起调,
找「自己好、相邻组合也好」的参数组合,并估计「从很多组合里挑最好的」本身带来的乐观偏差。

口径:
- 观测单位 = 买点事件:同一检测组合内同一买点事件只计一次;首次穿越率 = up/(up+down+both)。
- 参照格 = 工作点(检测参数与各道闸都取正式值)。每格每折相对参照格的首次穿越率差取各折最差者 → r=1 邻域
  取最小(只在可评估的格之间)→ 按 `region_core.rank_cells` 的键排序。
- 可评估 = 每折四态总数 ≥ 功效线、每折买点事件数 ≥ 下限、且不是退化格(收紧一档一个买点事件都没多筛掉)。
  功效线 = ceil(n_pl(δ)),设计效应与定向占比取账本里最近一次优势检查的实测值,不回退标定常数。
- 候选格:给定一组「一起调」的参数 J,联合网格里移动的参数 ⊆ J 的格;J 里不在联合网格维度上的参数,
  由筛选扫描里现成的单翻转 / 两两翻转格补上(移动的参数 ⊆ J,且至少移动一个这样的参数)。补上的格在筛选
  网格上打分;两张表的同名检测组合是同一批行,工作点格的计数两表逐位自检一致,所以共用工作点参照。
- 校正:按股 bootstrap「连筛选一起重做」。每个副本先用同一组按股权重在筛选扫描上重做挑选,得到这个副本自己的
  J_b(`screen.joint_axes_under_weights`),再在 J_b 决定的候选格上重做联合挑选;股票权重按 symbol 名对齐两张表。
  optimism = mean_b[副本选中格在副本上的邻域分 − 同一格在原样本上的邻域分]。按股 bootstrap 只含个股噪声、
  不含同期行情的噪声,所以它是真实外推损失的下界。对半分验证在联合网格内照报。

`cell_query` 读联合识别产出的全量格张量查单个格,每次查询记一条账。
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
# 显式 REPO 相对路径,不用 Path(__file__).parent——REPO 由 git 顶层推,不依赖进程 cwd(与 multivar_scan.py 同款写法)。
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / ".claude/skills/tune-gates"))
import budget  # noqa: E402
import holdout  # noqa: E402
import ledger  # noqa: E402
import region_core as RC  # noqa: E402
import screen  # noqa: E402
import study_io as S  # noqa: E402

JOINT, SCREEN = "joint", "screen"
CSV_TOP = 5000
# 两张表必须同口径、同代码扫出来,同名检测组合才是同一批买点事件(连筛选一起重做的精确性前提)
CALIBER_WORDS = {"start_date": "买点起始日", "end_date": "买点截止日", "head_buffer": "首部缓冲",
                 "label_horizon": "涨跌结果的前瞻期", "first_passage_k": "首次穿越的边界宽度",
                 "price_min": "价格下限", "price_max": "价格上限", "volume_min": "成交量下限",
                 "source_fingerprint": "检测代码", "ruler_fingerprint": "涨跌结果的算法"}


# ── 机械闸 ──

def power_line(app: str, delta: float) -> tuple[int, dict]:
    """机械闸 2 的功效线:每格每折要的四态 bar 数 = ceil(n_pl(δ)),δ 为比例。

    设计效应与定向占比只取账本里最近一次优势检查的实测值;没有记录 → 人话拒绝,不回退任何标定常数。
    返回 (功效线, 那条记录的分辨力数据)。"""
    rec = ledger.latest(app, "edge")
    if rec is None:
        raise SystemExit(f"「{app}」还没做过优势检查,样本够不够分辨多小的改进不知道,先做优势检查。")
    res = rec["data"]["resolution"]
    return math.ceil(budget.n_pl(delta, deff=res["deff"], s_dec=res["s_dec"])), res


def grid_dims(cl: dict) -> list:
    """本窗网格里档数 > 1 的参数(参数键,网格声明顺序)。"""
    return [k for k, lv in {**cl["scan_grid"], **cl["where_levels"]}.items() if len(lv) > 1]


def working_point_diff(screen_wp: dict, cl: dict) -> list:
    """筛选记录的工作点与本窗扫描实际取值不一致的参数(参数键,排序)。

    本窗网格上的参数比本窗工作点;不在本窗网格上的参数比底座快照(正式参数 ⊕ 宽进覆盖,扫描时就固定在
    这个值上);本窗网格上有、筛选工作点里没有的参数也算不一致。"""
    eff = {f"{sec}.{k}": v for sec, kv in cl["ref_params"].items() for k, v in kv.items()}
    eff.update(cl["ref_point"])
    diff = {k for k, v in screen_wp.items() if k not in eff or eff[k] != v}
    diff |= {k for k in cl["ref_point"] if k not in screen_wp}
    return sorted(diff)


def screen_record(app: str, cl: dict, meta: dict) -> dict:
    """机械闸 1 的记录部分:同一段训练数据上、工作点与本窗一致的最近一条筛选记录;没有 → 人话拒绝。"""
    recs = [r for r in ledger.read(app) if r["kind"] == "select" and r["data"].get("tool") == "screen"]
    if not recs:
        raise SystemExit("还没做筛选:联合调参之前,要先在现在这组参数附近逐个改一处,看哪些改动分辨得出。先做筛选。")
    win = {"start": str(meta["start_date"]), "end": str(meta["end_date"])}
    same = [r for r in recs if r["window"] == win]
    if not same:
        raise SystemExit(f"做过的筛选都不是在这段训练数据({win['start']} 到 {win['end']} 的买点)上做的,"
                         "先在这段数据上做筛选。")
    for r in reversed(same):
        if not working_point_diff(r["data"]["working_point"], cl):
            return r
    diff = working_point_diff(same[-1]["data"]["working_point"], cl)
    raise SystemExit(f"筛选时的那组参数和这次一起调的网格里的现值不一样(不一致的参数:{diff}),筛选结论只对它自己那组参数成立。"
                     "先在现在这组参数上重做筛选(删过闸的,按删闸后的参数重做)。")


# ── 两张表上的格 ──

@dataclass
class Side:
    """一张扫描表上参与联合挑选的格。

    name: JOINT(联合网格)/ SCREEN(筛选扫描,只提供补充的单翻转 / 两两翻转格)。
    prep: 买点事件口径的 Prepared(折 = 年)。
    ref: 工作点格坐标(combo+pred)。
    params / levels: 各轴的参数键与档位表(格坐标轴序)。
    flats: 可作候选的格(combo+pred 扁平下标);联合表 = 全部格,筛选表 = 单翻转与两两翻转格。
    bits / n_moved: 每个 flats 格相对工作点移动了哪些参数(位掩码,位号见 bit_of)与移动的参数个数。
    bdist: 每个 flats 格到网格边界的距离(排序的末位平局键)。
    """
    name: str
    prep: RC.Prepared
    ref: tuple
    params: list
    levels: list
    flats: np.ndarray
    bits: np.ndarray
    n_moved: np.ndarray
    bdist: np.ndarray

    @property
    def shape(self) -> tuple:
        return tuple(self.prep.shape[:-2])

    @property
    def n_cells(self) -> int:
        return int(np.prod(self.shape))


def param_bits(*param_lists) -> dict:
    """参数键 → 位号(按参数键排序)。"""
    keys = sorted(set().union(*map(set, param_lists)))
    if len(keys) > 62:
        raise ValueError(f"参数个数 {len(keys)} 超过位掩码容量 62")
    return {k: i for i, k in enumerate(keys)}


def mask_of(keys, bit_of: dict) -> int:
    return sum(1 << bit_of[k] for k in set(keys))


def make_side(name: str, prep, ref: tuple, params: list, bit_of: dict, flats=None) -> Side:
    """建 Side:flats=None 取全部格;算每格移动的参数位掩码与个数。"""
    shape = tuple(prep.shape[:-2])
    if len(params) != len(shape) or len(ref) != len(shape):
        raise ValueError(f"make_side(): 轴数不一致(形状 {shape},参数 {params},参照格 {ref})")
    levels = list(prep.combo_levels.values()) + [lv for _, _, lv in prep.pred_specs]
    w = np.array([1 << bit_of[k] for k in params], np.int64)
    if flats is None:
        bits = np.zeros(shape, np.int64)
        n = np.zeros(shape, np.int16)
        for ax, (size, r) in enumerate(zip(shape, ref)):
            sh = [1] * len(shape); sh[ax] = size
            mv = (np.arange(size) != r).reshape(sh)
            bits |= np.where(mv, w[ax], np.int64(0))
            n += mv
        flats, bits, n = np.arange(int(np.prod(shape))), bits.ravel(), n.ravel()
    else:
        flats = np.unique(np.asarray(flats, np.int64))
        mv = np.stack(np.unravel_index(flats, shape), 1) != np.asarray(ref)
        bits, n = (mv * w).sum(1).astype(np.int64), mv.sum(1).astype(np.int16)
    return Side(name=name, prep=prep, ref=tuple(int(x) for x in ref), params=list(params), levels=levels,
                flats=flats, bits=bits, n_moved=n, bdist=RC.boundary_dist(shape).ravel()[flats])


def align_weights(W, union, symbols) -> np.ndarray:
    """按 symbol 名取出某张表的按股权重:W 的列对应 union,返回的列对应 symbols(该表的 symbol 码序)。"""
    pos = {s: i for i, s in enumerate(union)}
    missing = [s for s in symbols if s not in pos]
    if missing:
        raise ValueError(f"align_weights(): {len(missing)} 只股票不在股票全集里(例 {missing[:3]})")
    return np.asarray(W)[:, [pos[s] for s in symbols]]


def check_working_cell(joint: Side, other: Side) -> None:
    """两表工作点格的计数必须逐位相等:各折四态总计,以及按 symbol 名对齐后的每股每折 U/D/N。不等 → ValueError。

    这是「两表同名格是同一批买点事件、按名对齐的股票权重作用在同一批计数上」的自检。"""
    ta, tb = RC.tensor(joint.prep)[joint.ref], RC.tensor(other.prep)[other.ref]
    if ta.shape != tb.shape or not np.array_equal(ta, tb):
        raise ValueError(f"联合扫描与筛选扫描在工作点这一格的计数不一致(各折四态:联合 {ta.tolist()},"
                         f"筛选 {tb.tolist()}):两次扫描的同名组合不是同一批买点,不能连筛选一起重做校正")
    union = np.unique(np.concatenate([joint.prep.symbols, other.prep.symbols]).astype(object))
    pos = {s: i for i, s in enumerate(union)}
    per = []
    for side in (joint, other):
        sums = RC.stock_sums(side.prep, [side.ref], "per_fold")
        full = np.zeros((3, len(union), sums[0].shape[2]), np.int64)
        full[:, [pos[s] for s in side.prep.symbols]] = np.stack([a[:, 0, :] for a in sums])
        per.append(full)
    if not np.array_equal(*per):
        raise ValueError("联合扫描与筛选扫描在工作点这一格的每只股票计数不一致:两次扫描的同名组合不是同一批买点,"
                         "不能连筛选一起重做校正")


# ── 挑选与校正 ──

def _analyze(side: Side, min_count: int, min_segments: int, weights=None) -> dict:
    return RC.analyze_tensor(side.prep, side.ref, min_count, list(range(len(side.shape))), weights=weights,
                             min_segments=min_segments)


def candidate_masks(joint: Side, other: Side, J: int, dims: int) -> tuple[np.ndarray, np.ndarray]:
    """给定一起调的参数位掩码 J 与联合网格维度位掩码 dims:
    联合表候选 = 移动的参数 ⊆ J;筛选表候选 = 移动的参数 ⊆ J 且至少移动一个 J 里不在联合网格维度上的参数。"""
    mj = (joint.bits & ~J) == 0
    ms = ((other.bits & ~J) == 0) & ((other.bits & (J & ~dims)) != 0)
    return mj, ms


def identify(joint: Side, other: Side, J: int, dims: int, *, min_count: int, min_segments: int,
             RJ: dict | None = None, RS: dict | None = None, wj=None, ws=None) -> dict:
    """一次联合挑选:两表打分(RJ / RS 已给则复用)→ 取 J 决定的候选格 → 排序。

    候选 id:联合表的格 = 其扁平下标;筛选表的格 = 联合表格数 + 其扁平下标。
    返回 {"RJ", "RS", "ids": 排好序的候选 id, "s": 对应邻域分, "ev": 对应可评估, "n_moved": 对应移动参数个数}。"""
    RJ = _analyze(joint, min_count, min_segments, wj) if RJ is None else RJ
    RS = _analyze(other, min_count, min_segments, ws) if RS is None else RS
    mj, ms = candidate_masks(joint, other, J, dims)
    fj, fs = joint.flats[mj], other.flats[ms]
    s = np.r_[RJ["s_nb"].ravel()[fj], RS["s_nb"].ravel()[fs]]
    n = np.r_[RJ["n_eval_nb"].ravel()[fj], RS["n_eval_nb"].ravel()[fs]]
    b = np.r_[joint.bdist[mj], other.bdist[ms]]
    ev = np.r_[RJ["evaluable"].ravel()[fj], RS["evaluable"].ravel()[fs]]
    nm = np.r_[joint.n_moved[mj], other.n_moved[ms]]
    order = RC.rank_order(s, n, b)
    ids = np.r_[fj, fs + joint.n_cells][order]
    return {"RJ": RJ, "RS": RS, "ids": ids, "s": s[order], "ev": ev[order], "n_moved": nm[order]}


def cell_value(R: dict, joint: Side, other: Side, key: str, cid: int):
    """候选 id 在所属表上的某个格级量:key 为 `analyze_tensor` 输出的键;逐折的量返回 (折数,) 数组,其余返回标量。"""
    if cid < joint.n_cells:
        return R["RJ"][key][np.unravel_index(cid, joint.shape)]
    return R["RS"][key][np.unravel_index(cid - joint.n_cells, other.shape)]


def _near(a: int, b: int, joint: Side, other: Side) -> bool:
    """两个候选 id 是同一格或同一张表上只差一档的相邻格。"""
    if (a < joint.n_cells) != (b < joint.n_cells):
        return False
    shape, off = (joint.shape, 0) if a < joint.n_cells else (other.shape, joint.n_cells)
    return int(np.abs(np.subtract(np.unravel_index(a - off, shape), np.unravel_index(b - off, shape))).sum()) <= 1


def joint_bootstrap(joint: Side, other: Side, reselect, J0: set, dims: set, bit_of: dict, *, min_count: int,
                    min_segments: int, B: int, seed: int, top_n: int, base: dict | None = None) -> dict:
    """连筛选一起重做的按股 bootstrap。

    参数:
        joint / other: 联合表与筛选表。
        reselect: fn(W_other) → list[set];W_other 形状 (B, other.prep.n_sym),按筛选表的 symbol 码对齐,
            返回每个副本「一起调」的参数集合(参数键)。
        J0: 原样本的一起调参数集合;dims: 联合网格维度(参数键);bit_of: 参数键 → 位号。
        min_count / min_segments: 可评估门槛(功效线、每折买点事件数下限)。
        B / seed / top_n: 副本数、种子、top_freq 的名次截断。
        base: 原样本的 `identify` 结果(给了就不重算)。
    算法:股票全集 = 两表 symbol 名的并集(有序);每个副本抽 multinomial(全集股数, 等概率) 的整数权重,按名分给
        两张表;reselect 得 J_b;两表按权重重新打分,在 J_b 的候选里挑第一名 ĉ_b。ĉ_b 的邻域分无定义的副本跳过。
    返回 {"center": ĉ, "stability": P(ĉ_b 与 ĉ 同格或相邻), "n_valid", "ci": ĉ 在副本上邻域分的 2.5/97.5 分位,
          "optimism", "optimism_se", "n_opt", "top_freq": {候选 id: 进前 top_n 的次数},
          "reselect": {"inclusion_freq": {参数键: 频率}, "set_repro": 频率}, "n_candidates": 每个副本的候选格数, "B"}。
    """
    Jb0, Db = mask_of(J0, bit_of), mask_of(dims, bit_of)
    base = identify(joint, other, Jb0, Db, min_count=min_count, min_segments=min_segments) if base is None else base
    c_hat = int(base["ids"][0])
    s_hat0 = float(base["s"][0])
    union = np.unique(np.concatenate([joint.prep.symbols, other.prep.symbols]).astype(object))
    rng = np.random.default_rng(seed)
    W = rng.multinomial(len(union), np.full(len(union), 1.0 / len(union)), size=B)
    Wj, Ws = align_weights(W, union, joint.prep.symbols), align_weights(W, union, other.prep.symbols)
    Js = [set(x) for x in reselect(Ws)]
    if len(Js) != B:
        raise ValueError(f"joint_bootstrap(): reselect 返回 {len(Js)} 个集合,应为 {B}")
    incl = dict.fromkeys(sorted(set(J0).union(*Js)), 0)
    same = 0
    hits = n_valid = 0
    s_at_hat, opt, top_freq, n_cand = [], [], {}, []
    for b in range(B):
        for k in Js[b]:
            incl[k] += 1
        same += Js[b] == set(J0)
        r = identify(joint, other, mask_of(Js[b], bit_of), Db, min_count=min_count, min_segments=min_segments,
                     wj=Wj[b], ws=Ws[b])
        n_cand.append(len(r["ids"]))
        if not np.isfinite(s_hat0) or not len(r["ids"]) or not np.isfinite(r["s"][0]):
            continue
        cb = int(r["ids"][0])
        n_valid += 1
        hits += _near(cb, c_hat, joint, other)
        s_at_hat.append(float(cell_value(r, joint, other, "s_nb", c_hat)))
        s0 = float(cell_value(base, joint, other, "s_nb", cb))
        if np.isfinite(s0):
            opt.append(float(r["s"][0]) - s0)
        for i, sv in zip(r["ids"][:top_n], r["s"][:top_n]):
            if np.isfinite(sv):
                top_freq[int(i)] = top_freq.get(int(i), 0) + 1
    fin = np.array([x for x in s_at_hat if np.isfinite(x)])
    opt_arr = np.array(opt, float)
    return {"center": c_hat, "stability": hits / n_valid if n_valid else float("nan"), "n_valid": n_valid,
            "ci": (float(np.percentile(fin, 2.5)), float(np.percentile(fin, 97.5))) if len(fin) else (float("nan"),) * 2,
            "optimism": float(opt_arr.mean()) if len(opt_arr) else float("nan"),
            "optimism_se": float(opt_arr.std(ddof=1) / np.sqrt(len(opt_arr))) if len(opt_arr) > 1 else float("nan"),
            "n_opt": len(opt_arr), "top_freq": top_freq,
            "reselect": {"inclusion_freq": {k: v / B for k, v in incl.items()}, "set_repro": same / B},
            "n_candidates": n_cand, "B": B}


# ── 落盘与报告 ──

def _v(x) -> str:
    if x is None:
        return "不设"
    return f"{x:g}" if isinstance(x, (int, float, np.integer, np.floating)) else str(x)


def _pt(x, signed: bool = True) -> str:
    if x is None or not np.isfinite(x):
        return "—"
    return f"{x * 100:+.2f}" if signed else f"{x * 100:.2f}"


def cell_values(cid: int, joint: Side, other: Side, wp: dict) -> dict:
    """候选 id → {参数键: 取值};该表网格上没有的参数取工作点值。"""
    side, off = (joint, 0) if cid < joint.n_cells else (other, joint.n_cells)
    vals = dict(wp)
    for k, lv, i in zip(side.params, side.levels, np.unravel_index(cid - off, side.shape)):
        vals[k] = lv[int(i)]
    return vals


def describe(vals: dict, wp: dict) -> str:
    ch = [f"`{k}` {_v(wp[k])} → {_v(v)}" for k, v in vals.items() if k in wp and v != wp[k]]
    return "、".join(ch) if ch else "维持现在这组参数"


def _cells_table(base: dict, bs: dict, joint: Side, other: Side, wp: dict, folds: list, n: int) -> pd.DataFrame:
    rows = []
    for rank, cid in enumerate(base["ids"][:n], 1):
        cid = int(cid)
        row = {"rank": rank, "source": JOINT if cid < joint.n_cells else SCREEN,
               "flat": cid if cid < joint.n_cells else cid - joint.n_cells, **cell_values(cid, joint, other, wp)}
        for key in ("evaluable", "degenerate", "s", "s_nb", "n_eval_nb"):
            row[key] = cell_value(base, joint, other, key, cid).item()
        row["boot_top"] = bs["top_freq"].get(cid, 0)
        for key in ("count", "segments", "fp", "delta"):
            vals = cell_value(base, joint, other, key, cid)
            for f, fold in enumerate(folds):
                row[f"{key}_{fold}"] = vals[f].item()
        rows.append(row)
    return pd.DataFrame(rows)


def _report(*, app, window, delta, folds, n_pl, res, floor, wp, joint, other, base, bs, shm, tier, tol, n_eval,
            n_degen, n_sup, top_n) -> str:
    c_hat = bs["center"]
    vals = cell_values(c_hat, joint, other, wp)
    naive = float(base["s"][0])
    opt, opt_se = bs["optimism"], bs["optimism_se"]
    corrected = naive - opt if np.isfinite(opt) else float("nan")
    from_screen = "(这个组合不在这次一起调的网格里,取自筛选时现成的扫描)" if c_hat >= joint.n_cells else ""
    L = [f"# {app} · {window} · 联合调参结果", "",
         f"在现在这组参数附近,把筛选里分辨得出的参数(以及和它们一起改时会互相影响的参数)放在一起调,找「自己好、"
         f"相邻组合也好」的组合。同一段买点只计一次;每个组合在 {'、'.join(folds)} 各年分别和现在这组参数比首次穿越率,"
         f"取最差的一年,再和只差一档的相邻组合取最差;改进不到 {delta * 100:g} 点不算数。", "", "## 结论", ""]
    if tier == RC.VERDICT_CANDIDATE:
        L.append(f"推荐组合:{describe(vals, wp)}{from_screen}。它在最差的一年、连同相邻组合里最差的那个,首次穿越率"
                 f"仍比现在高 {_pt(naive)} 点;扣掉挑选带来的乐观偏差后约 {_pt(corrected)} 点(这个扣减只会少扣,见下文)。")
    elif tier == RC.VERDICT_CORRECTED_NEGATIVE:
        L.append(f"本次没有找到稳健的组合:看上去最好的是 {describe(vals, wp)}{from_screen}(比现在高 {_pt(naive)} 点),"
                 f"但扣掉挑选带来的乐观偏差后是 {_pt(corrected)} 点,不构成改进。下面的数字只供诊断,不构成推荐。")
    else:
        L.append(f"本次没有找到稳健的组合:没有哪个组合在最差的一年、连同相邻组合都比现在这组参数好。"
                 f"看上去最不坏的是 {describe(vals, wp)}{from_screen}({_pt(naive)} 点),不构成推荐。")

    L += ["", "## 三种算法给的分数", "",
          f"- 朴素分数:{_pt(naive)} 点。挑出来那一组自己的分数,偏乐观,只作参考。"]
    if not np.isfinite(opt):
        L.append("- 扣掉挑选带来的乐观偏差:估不出来(重新抽股票后挑中的组合样本都不够)。")
    else:
        L.append(f"- 扣掉挑选带来的乐观偏差:偏差 {_pt(opt)} ± {_pt(opt_se, False)} 点({bs['n_opt']}/{bs['B']} 次重抽可用),"
                 f"扣完 {_pt(corrected)} 点。每次重新抽股票都把筛选也重做一遍——哪些参数进联合随之变,再在变化后的组合里"
                 "重新挑。**这个偏差是往小了估的**:重抽股票只模拟了「换一批股票」,没模拟「换一段行情」,真实的落差只会更大,"
                 "扣完的数仍然偏乐观;它只用来判断值不值得花掉留作最后验证的数据,不能代替验证。")
        if opt < 0:
            L.append("  - 偏差估计为负:这次没看出挑选带来的虚高(也可能被重抽的随机性盖住),扣完的数不能当成保守的数读。")
    L.append(f"- 对半分验证:一半股票挑、另一半股票打分(只在这次一起调的网格内挑),{shm['n_valid']} 个分法平均 {_pt(shm['mean'])} "
             f"± {_pt(shm['se'], False)} 点;这个数对怎么分很敏感,只看方向。")

    L += ["", "## 挑选稳不稳", "",
          f"- 重新抽 {bs['B']} 次股票,挑中的组合就是推荐组合或与它只差一档的比例 {bs['stability'] * 100:.0f}%"
          f"(基于 {bs['n_valid']} 次挑得出组合的重抽);推荐组合自己的分数 95% 区间 [{_pt(bs['ci'][0])}, {_pt(bs['ci'][1])}] 点。",
          "- 筛选结论稳不稳(重抽股票、重做筛选后,各参数进入联合的比例):"
          + "、".join(f"`{k}` {v * 100:.0f}%" for k, v in bs["reselect"]["inclusion_freq"].items()) + ";"
          f"进入联合的参数和这次完全一样的比例 {bs['reselect']['set_repro'] * 100:.0f}%。"]

    ref_R = base["RJ"]
    L += ["", "## 样本够不够", "",
          f"- 一个组合每年至少要有 {n_pl} 个买点 bar、至少 {floor} 段买点,才下结论(由最小关心改进 {delta * 100:g} 点"
          f"和优势检查实测的样本相关程度推出:同一只股票的买点彼此牵连,约 {res['deff']:.1f} 个 bar 才顶一个独立样本)。",
          f"- 这次一起调的网格 {joint.n_cells} 个组合,另从筛选的扫描里补了 {n_sup} 个单改 / 两两改的组合;样本够、能下结论的 {n_eval} 个。",
          f"- 其中 {n_degen} 个组合收紧的那道闸一个买点都没多筛掉,和放松一档是同一批样本,不单独算、也不当相邻组合。",
          "- 现在这组参数:" + ";".join(
              f"{fold} 年 {int(ref_R['count'][joint.ref + (f,)])} 个买点 bar({int(ref_R['segments'][joint.ref + (f,)])} 段买点)、"
              f"首次穿越率 {ref_R['fp'][joint.ref + (f,)] * 100:.1f}%" for f, fold in enumerate(folds)) + "。"]

    if tol is not None:
        L += ["", "## 容错宽度", "", "推荐组合沿每个参数按档位表顺序往前、往后各挪几档,邻域分数仍为正:"]
        L += [f"- `{joint.params[ax]}`:往前 {d} 档、往后 {u} 档" for ax, (d, u) in tol.items() if len(joint.levels[ax]) > 1]

    L += ["", f"## 排名前 {top_n} 的组合", "",
          "| 排名 | 改了什么 | 最差一年比现在 | 连同相邻组合最差 | 能比的相邻组合 | "
          + " | ".join(f"{fold} 首次穿越率 / 买点 bar" for fold in folds) + f" | 重抽里进前 {top_n} 的次数 |",
          "|---|---|---|---|---|" + "---|" * len(folds) + "---|"]
    for rank, cid in enumerate(base["ids"][:top_n], 1):
        cid = int(cid)
        tag = "(筛选补充)" if cid >= joint.n_cells else ""
        fp, cnt = cell_value(base, joint, other, "fp", cid), cell_value(base, joint, other, "count", cid)
        L.append(f"| {rank} | {describe(cell_values(cid, joint, other, wp), wp)}{tag} "
                 f"| {_pt(float(cell_value(base, joint, other, 's', cid)))} "
                 f"| {_pt(float(cell_value(base, joint, other, 's_nb', cid)))} "
                 f"| {int(cell_value(base, joint, other, 'n_eval_nb', cid))} | "
                 + " | ".join(f"{fp[f] * 100:.1f}% / {int(cnt[f])}" if np.isfinite(fp[f]) else f"— / {int(cnt[f])}"
                              for f in range(len(folds)))
                 + f" | {bs['top_freq'].get(cid, 0)} |")
    L += ["", "## 下一步", "",
          ("- 把推荐组合(连同它的相邻组合)写进验证清单,在留作最后验证的数据上各开一次核对;任意一个组合的数字可以单独查。"
           if tier == RC.VERDICT_CANDIDATE else
           "- 本次没有值得拿去验证的组合:维持现值,或在筛选里分辨得出的单个改动里挑。")]
    return "\n".join(L) + "\n"


# ── 入口 ──

def run(app: str, cfg, longtable_dir: str, *, delta: float, apps_dir=None, calendar=None) -> dict:
    """联合阶段识别(`tune.find`)。

    参数:
        app: app 名。
        cfg: Settings(用 fold_col、folds、min_segments_floor、b_boot、boot_seed、split_half_seeds、top_n)。
        longtable_dir: 联合窗口的扫描结果目录(绝对路径或相对仓库根);window = 其父目录名,筛选窗口的扫描
            结果按同一输出根下的 <筛选窗口>/longtable 找。
        delta: 最小关心改进(比例,0.02 = 2 点)。
        apps_dir / calendar: 研究声明根目录、交易日历(单测注入;缺省走真实路径)。
    前置(依次,任一不满足 → 人话拒绝,不读标签、不写任何东西):
        1. 分类表与声明一致、扫描结果与分类表一致;一致性验证跑完、全部对上;
        2. 机械闸 1:窗口声明的工作点覆盖全部轴;同一段训练数据上有工作点一致的筛选记录;本窗网格里档数 > 1 的
           参数 ⊆ 该记录的「一起调」参数;筛选窗口的扫描结果还在、与本窗同口径同代码;
        3. 机械闸 2:功效线取自优势检查实测(没有记录 → 拒绝);
        4. 确认窗守卫放行;
        5. 自检(不过 → ValueError):两表工作点格计数逐位一致;用筛选扫描复算的「一起调」参数等于记录;
        6. 机械闸 2 的结论:同时移动两个及以上参数的候选格一个都不可评估(网格维度 ≥ 2 时)、或没有任何移动了参数
           的候选格可评估 → 拒绝(样本只够一次改一个参数)。
    落盘到联合窗口输出目录:cells.npz(联合网格全量格张量,count_unit="event")、cells.csv(候选格排名前
    CSV_TOP 行,含筛选补充格)、region_report.md;最后写一条 select 记录(n_looks = 可评估候选格数;data 含
    window_name = 联合窗口名、screen_window_name = 所用筛选窗口名,供状态推导按记录找产物)。
    返回 {"report", "verdict", "center": {参数键: 值}, "n_evaluable", "optimism", "joint_axes"}。
    """
    apps_dir = Path(apps_dir) if apps_dir else S.APPS_DIR
    lt = Path(longtable_dir)
    lt = lt if lt.is_absolute() else REPO / lt
    out, window = lt.parent, lt.parent.name
    if not (lt / "run_meta.json").exists():
        raise SystemExit("这个窗口还没有扫描结果,先扫描。")
    meta = S.load_run_meta(lt)
    if meta.get("app") != app:
        raise SystemExit(f"这批扫描结果属于「{meta.get('app')}」,不是「{app}」,拒绝按「{app}」的声明去切它。")
    cl = S.load_classification(app, window, apps_dir)
    S.check_study_matches(cl, S.study_path(app, window, apps_dir))
    S.check_run_matches_classification(meta, cl)
    screen.check_consistency(out, cl)

    if cl.get("ref_point_scope") != "all":
        raise SystemExit("这个窗口是旧版声明:工作点只写了检测参数、没写各道闸的现值,不能做联合调参。"
                         "请按现在的正式参数重新落地这个窗口的声明。")
    rec = screen_record(app, cl, meta)
    J0 = list(rec["data"]["joint_axes"])
    dims = grid_dims(cl)
    if not dims:
        raise SystemExit("这张联合网格里每个参数都只有一档,没有要一起调的参数。")
    extra = [k for k in dims if k not in J0]
    if extra:
        raise SystemExit(f"联合网格里要调的 {extra} 在筛选里既没分辨出来,也不是和分辨出来的参数一起改时有互相影响而"
                         f"被带进来的(筛选给出的一起调参数:{J0}),不能直接进联合调参。把它们固定在现值,或先重做筛选。")
    sw = rec["data"]["window_name"]
    cl_s = S.load_classification(app, sw, apps_dir)
    S.check_study_matches(cl_s, S.study_path(app, sw, apps_dir))
    lt_s = out.parent / sw / "longtable"
    if not (lt_s / "run_meta.json").exists():
        raise SystemExit("做筛选用的那批扫描结果已经不在了,没法连筛选一起重做校正;重新扫描筛选窗口后重做筛选。")
    meta_s = S.load_run_meta(lt_s)
    S.check_run_matches_classification(meta_s, cl_s)
    bad = [w for k, w in CALIBER_WORDS.items() if meta_s.get(k) != meta.get(k)]
    if bad:
        raise SystemExit(f"筛选和这次联合调参的两批扫描口径不同({'、'.join(bad)}),同名组合不再是同一批买点,"
                         "没法连筛选一起重做校正;两批要在同一套口径与代码下扫描。")
    n_pl, res = power_line(app, delta)
    floor = int(cfg.min_segments_floor)
    folds = list(cfg.folds)
    years, q = list(rec["data"]["years"]), float(rec["data"]["q"])
    if any(y not in folds for y in years):
        raise SystemExit(f"筛选按 {years} 分年,这次联合调参按 {folds} 分年,对不上。")

    holdout.guard_label_access(app, meta["start_date"], meta["end_date"], "find", calendar=calendar)

    names_j = screen.axis_params(cl)
    combo_j, preds_j = S.derived_axes(cl)
    shards_j = sorted(lt.glob("part-*.parquet"))
    prep_j = RC.prepare_shards(shards_j, combo_j, preds_j, cfg.fold_col, folds,
                               segment_cols=S.segment_cols(cl, pq.read_schema(shards_j[0]).names))
    axes_j = list(combo_j) + [c for c, _, _ in preds_j]
    ref_j = RC.cell_index(combo_j, preds_j, {a: cl["ref_point"][names_j[a]] for a in axes_j})

    spec_s, wp = screen.spec_from_classification(cl_s, rec["data"]["working_point"])
    names_s = screen.axis_params(cl_s)
    combo_s, preds_s = S.derived_axes(cl_s)
    shards_s = sorted(lt_s.glob("part-*.parquet"))
    prep_s = RC.prepare_shards(shards_s, combo_s, preds_s, cfg.fold_col, folds,
                               segment_cols=S.segment_cols(cl_s, pq.read_schema(shards_s[0]).names))
    axes_s = list(combo_s) + [c for c, _, _ in preds_s]
    ref_s = RC.cell_index(combo_s, preds_s, spec_s.working)
    dz = screen.design_cells(spec_s, combo_s, preds_s)
    sup = ([dz["coords"][f["xi"]] for f in dz["family"] if f["base"] == "working"]
           + [dz["coords"][ab] for _, _, ab in dz["pairs"]])
    shape_s = tuple(prep_s.shape[:-2])

    params_j, params_s = [names_j[a] for a in axes_j], [names_s[a] for a in axes_s]
    bit_of = param_bits(params_j, params_s)
    joint = make_side(JOINT, prep_j, ref_j, params_j, bit_of)
    other = make_side(SCREEN, prep_s, ref_s, params_s, bit_of,
                      flats=[np.ravel_multi_index(c, shape_s) for c in sup] if sup else np.zeros(0, np.int64))
    check_working_cell(joint, other)

    def reselect(W):
        return [{names_s[a] for a in got}
                for got in screen.joint_axes_under_weights(prep_s, spec_s, W, years=years, q=q)]

    again = reselect(np.ones((1, prep_s.n_sym)))[0]
    if again != set(J0):
        raise ValueError(f"用筛选那批扫描结果复算不出筛选记录里一起调的参数(复算 {sorted(again)},记录 {sorted(J0)}):"
                         "筛选之后扫描结果或筛选设置变过,先重做筛选")

    base = identify(joint, other, mask_of(J0, bit_of), mask_of(dims, bit_of), min_count=n_pl, min_segments=floor)
    ev, nm = base["ev"], base["n_moved"]
    n_eval = int(ev.sum())
    if len(dims) >= 2 and not (ev & (nm >= 2)).any():
        raise SystemExit(f"样本只够一次改一个参数:同时改两个及以上参数的组合,没有一个的样本量够分辨 {delta * 100:g} 点的差别"
                         f"(每个组合每年至少要 {n_pl} 个买点 bar、{floor} 段买点)。建议在筛选里分辨得出的单个改动里挑,"
                         "不做联合调参。")
    if not (ev & (nm >= 1)).any():
        raise SystemExit(f"样本只够维持现值:改动任何一个参数的组合,样本量都不够分辨 {delta * 100:g} 点的差别"
                         f"(每个组合每年至少要 {n_pl} 个买点 bar、{floor} 段买点)。")

    bs = joint_bootstrap(joint, other, reselect, set(J0), set(dims), bit_of, min_count=n_pl, min_segments=floor,
                         B=cfg.b_boot, seed=cfg.boot_seed, top_n=cfg.top_n, base=base)
    shm = RC.split_half_multi(prep_j, ref_j, n_pl, list(range(len(joint.shape))), list(cfg.split_half_seeds),
                              min_segments=floor)
    naive = float(base["s"][0])
    tier = RC.verdict(naive, bs["optimism"], shm["mean"])
    c_hat = bs["center"]
    tol = RC.tolerance(base["RJ"]["s_nb"], tuple(int(i) for i in np.unravel_index(c_hat, joint.shape))) \
        if c_hat < joint.n_cells and np.isfinite(naive) else None
    mj, ms = candidate_masks(joint, other, mask_of(J0, bit_of), mask_of(dims, bit_of))
    n_sup = int(ms.sum())
    n_degen = int(base["RJ"]["degenerate"].ravel()[joint.flats[mj]].sum()
                  + base["RS"]["degenerate"].ravel()[other.flats[ms]].sum())

    RC.save_cells_npz(out / "cells.npz", base["RJ"], joint.shape, folds, cl["fingerprints"]["study"], count_unit="event")
    _cells_table(base, bs, joint, other, wp, folds, CSV_TOP).to_csv(out / "cells.csv", index=False)
    report = out / "region_report.md"
    report.write_text(_report(app=app, window=window, delta=delta, folds=folds, n_pl=n_pl, res=res, floor=floor, wp=wp,
                              joint=joint, other=other, base=base, bs=bs, shm=shm, tier=tier, tol=tol, n_eval=n_eval,
                              n_degen=n_degen, n_sup=n_sup, top_n=cfg.top_n), encoding="utf-8")

    center = cell_values(c_hat, joint, other, wp)
    data = {"tool": "find", "window_name": window, "screen_window_name": sw, "working_point": wp, "delta": delta,
            "power_line": n_pl, "min_segments": floor,
            "screen_ts": rec["ts"], "joint_axes": J0, "n_cells": joint.n_cells, "n_supplement": n_sup,
            "n_evaluable": n_eval, "n_degenerate": n_degen, "verdict": tier, "center": center,
            "center_source": JOINT if c_hat < joint.n_cells else SCREEN, "naive": naive,
            "optimism": bs["optimism"], "optimism_se": bs["optimism_se"], "stability": bs["stability"],
            "split_half": {k: shm[k] for k in ("mean", "se", "n_valid")}, "reselect": bs["reselect"], "B": bs["B"]}
    npz = out / "cells.npz"
    ledger.append(ledger.make_record(
        "select", app, actor=screen.ACTOR, round=None, axes=list(dims),
        window={"start": str(meta["start_date"]), "end": str(meta["end_date"])},
        label_horizon=int(meta["label_horizon"]), head_buffer=int(meta["head_buffer"]),
        **ledger.current_fingerprints(app, window), n_looks=n_eval,
        ref={screen.artifact_path(report): ledger.sha256_file(report), screen.artifact_path(npz): ledger.sha256_file(npz)},
        data=screen.jsonable(data)))
    return {"report": str(report), "verdict": tier, "center": center, "n_evaluable": n_eval,
            "optimism": bs["optimism"], "joint_axes": J0}


def cell_query(app: str, window: str, levels: dict, *, note: str = "", apps_dir=None, out_root=None,
               calendar=None) -> dict:
    """按参数取值查联合识别产出的单个格(`tune.cell`),每次查询在账本里记一条 select。

    参数:
        levels: {参数键: 档值},本窗网格的每个参数都要给,值须精确等于档位表里的档(None 可以)。
        note: 这次查询的用途说明,原样记进账本。
        apps_dir / out_root / calendar: 研究声明根目录、输出根目录、交易日历(单测注入)。
    先过确认窗守卫(格级数字来自标签);cells.npz 是另一份研究声明下算的 → 拒绝。
    返回 `region_core.cell_metrics` 的输出另加 count_unit:新产物 = "event"(买点事件口径);没有这个键的旧产物 =
    "row(legacy)"(逐行口径,同一段买点可能重复计数)。账本记录:tool="cell"、n_looks=1、axes = 本窗全部参数键、
    ref = cells.npz 的 sha256、data.window_name / data.levels / data.note。
    """
    apps_dir = Path(apps_dir) if apps_dir else S.APPS_DIR
    out = (Path(out_root) if out_root else REPO / "outputs" / "tune_gates") / app / window
    npz = out / "cells.npz"
    if not npz.exists():
        raise SystemExit("这个窗口还没做过联合调参,没有可查的组合结果。")
    cl = S.load_classification(app, window, apps_dir)
    combo, preds = S.derived_axes(cl)
    names = screen.axis_params(cl)
    axis_of = {p: a for a, p in names.items()}
    params = [names[a] for a in list(combo) + [c for c, _, _ in preds]]
    grid = dict(zip(params, list(combo.values()) + [lv for _, _, lv in preds]))
    missing, unknown = [k for k in params if k not in levels], sorted(set(levels) - set(params))
    if missing or unknown:
        raise SystemExit(f"查一个组合要把这个窗口的每个参数都给上:缺 {missing},不认识 {unknown}(这个窗口的参数:{params})")
    off = {k: v for k, v in levels.items() if v not in grid[k]}
    if off:
        raise SystemExit("这些参数的取值不在网格的档位上:" + ";".join(f"{k} = {v!r}(可选 {grid[k]})" for k, v in off.items()))
    lt = out / "longtable"
    if not (lt / "run_meta.json").exists():
        raise SystemExit("这个窗口的扫描结果已经不在了,认不出组合结果读的是哪段数据,拒绝查询。")
    meta = S.load_run_meta(lt)
    holdout.guard_label_access(app, meta["start_date"], meta["end_date"], "cell", calendar=calendar)
    cells = RC.load_cells_npz(npz)
    fp_npz, fp_now = str(cells["study_fingerprint"]), cl["fingerprints"]["study"]
    if fp_npz and fp_npz != fp_now:
        raise SystemExit("这份组合结果是在另一份研究声明下算的(网格变过,组合的位置含义已经不同),重做联合调参后再查。")
    idx = RC.cell_index(combo, preds, {axis_of[k]: v for k, v in levels.items()})
    out_metrics = RC.cell_metrics(cells, idx, [str(x) for x in cells["folds"]])
    out_metrics["count_unit"] = str(cells["count_unit"]) if "count_unit" in cells else "row(legacy)"
    ledger.append(ledger.make_record(
        "select", app, actor=screen.ACTOR, round=None, axes=params,
        window={"start": str(meta["start_date"]), "end": str(meta["end_date"])},
        label_horizon=int(meta["label_horizon"]), head_buffer=int(meta["head_buffer"]),
        **ledger.current_fingerprints(app, window), n_looks=1,
        ref={screen.artifact_path(npz): ledger.sha256_file(npz)},
        data=screen.jsonable({"tool": "cell", "window_name": window, "levels": {k: levels[k] for k in params},
                              "note": note,
                              "count_unit": out_metrics["count_unit"]})))
    return out_metrics
