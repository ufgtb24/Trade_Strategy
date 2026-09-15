# -*- coding: utf-8 -*-
"""region_find 的纯函数层:长表 → 联合空间格张量 → 可评估 / 相对参照增量 / fold 最小 / r=1 邻域最小
→ 排序 → 按股 bootstrap + 选择后校正(Task 10 追加)。

格张量:轴 = [combo 轴...] + [pred 轴...] + [fold, 4 态]。combo 轴 = 反转循环真扫的检测组合维
(行值精确等于档位);pred 轴 = 过滤型 / where 维(行带原始量,档位松→紧嵌套):行先落在其满足的
**最紧档**桶,再沿 pred 轴做后缀累加——满足紧档的行也属于所有更松的格。一次 bincount 出全部格。
bootstrap 用同一 flat 索引按 symbol 权重重做 bincount,不在原始行上重采样。

两种计数口径(`prepare(segment_cols=...)`):逐行口径一行计一次;买点事件口径把同一检测组合内同一个
买点事件(买点 node 解析出的事件区间组;同一 symbol、fold、买点事件键)的多行合成一次计数——任一行过某格全部闸,这个买点事件就在该格计一次。
买点事件口径靠带符号的点质量实现,后缀累加后逐格精确(见 `_segment_masses`)。

两套"扁平空间"不要混用:
- `Prepared.flat`(以及 `tensor()` 输出)所在的空间 = combo 轴 × pred 轴 × **fold 轴**。
- `score`/`neighbor_min`/`rank_cells`/`tolerance`/`cell_coords` 所在的空间 = combo 轴 × pred 轴
  (**不含** fold——fold 已经在 `score()` 里被 min 掉了)。
两者维度数不同,`rank_cells` 返回的扁平索引不能直接当 `Prepared.flat` 用,反之亦然。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

STATES = ["fp_up", "fp_down", "fp_both", "fp_none"]
SEG_SUBSET_MAX_K = 10         # 买点事件口径:约简后 k ≤ 此值走子集包含-排斥,否则走谓词格上的逐轴差分
SEG_GRID_MAX = 100_000        # 逐轴差分路径允许的谓词格格数上限
_CHUNK_BYTES = 1 << 26        # 买点事件口径分桶批处理时单块中间数组的字节量级上限
_DERIVED_FOLD = "__fold__"    # prepare_shards(fold_from=...) 派生折的临时列名(不与长表列重名)


def _validate_level_structure(op: str, levels: list) -> None:
    """结构性校验档位序列是否松→紧严格嵌套(不依赖数据是否恰好覆盖到分界情形)。

    None(=不过滤,最松)只允许出现在下标 0;其余为数值,按 op 决定的"更紧"方向必须严格单调:
    >=/>:数值严格递增(阈值越大越紧,满足的行越少);</<=:数值严格递减(阈值越小越紧)。
    这是防"数据侧检查测不出"的第二道闸——例如 [20, 0] 配 ">=" 在数据全部 >=20 时,
    逐行的 ok 掩码不会呈现任何"紧档不是松档子集"的见证,但结构上仍是紧→松写反了。
    """
    if op not in (">=", ">", "<", "<="):
        raise ValueError(f"不支持的 op {op!r}")
    for j, lv in enumerate(levels):
        if lv is None and j != 0:
            raise ValueError(f"档位 {levels}: None(不过滤)只能出现在下标 0,实际出现在下标 {j}")
    finite = [lv for lv in levels if lv is not None]
    if op in (">=", ">"):
        ok = all(a < b for a, b in zip(finite, finite[1:]))
    else:
        ok = all(a > b for a, b in zip(finite, finite[1:]))
    if not ok:
        raise ValueError(f"档位 {levels} 非松→紧严格单调嵌套(op {op!r})")


def pred_level_index(values, op: str, levels: list) -> np.ndarray:
    """把一列原始数值按谓词档位(松→紧、嵌套)映射到"每行满足的最紧档"下标。

    参数:
        values: 谓词列的原始量,可含 NaN(自动 coerce,
            视为不满足任何档)。
        op: 比较算子,">="/">"/"<"/"<=" 之一。
        levels: 档位列表,**下标 0 = 最松**,越往后越紧;元素为 None 表示"不过滤"(全真,
            只能出现在下标 0),否则为数值阈值。levels 必须严格单调嵌套(见 `_validate_level_structure`),
            非法直接 `ValueError`。

    返回:
        int16 数组,每行 = 该行满足的**最紧**档下标;一档都不满足(含最松档)→ -1。

    算法:
        先做结构性校验(不看数据),再逐档从松到紧算布尔 mask 并做数据侧的二次校验——
        后一档的 True 集合必须是前一档的子集(否则档位定义本身矛盾),`idx[ok] = j`
        让更紧的档覆盖前面的赋值,最终每行落在它满足的最紧档。
    """
    _validate_level_structure(op, levels)
    v = np.asarray(pd.to_numeric(pd.Series(values), errors="coerce"), dtype=float)
    idx = np.full(len(v), -1, dtype=np.int16)
    prev = None
    for j, lv in enumerate(levels):
        if lv is None:
            ok = np.ones(len(v), bool)
        elif op == ">=":
            ok = v >= lv
        elif op == ">":
            ok = v > lv
        elif op == "<":
            ok = v < lv
        else:  # "<="
            ok = v <= lv
        if prev is not None and np.any(ok & ~prev):
            raise ValueError(f"档位 {levels} 非松→紧嵌套(op {op})")
        idx[ok] = j
        prev = ok
    return idx


@dataclass
class Prepared:
    """`prepare()` 的输出:长表已离散化为一组「条目」,供 `tensor()` 一次 bincount 出全部格。

    条目 = 一个带符号的点质量:落在格张量的扁平索引 `flat` 上,四态质量 `states`、买点事件计数 `seg`。
    格张量 = 按条目 bincount 后沿 pred 轴做后缀累加。两种口径:
    - 逐行口径(`segment_cols=None`):一行一个条目,质量 = 该行四态、买点事件计数 1,落在该行满足的最紧档。
    - 买点事件口径(给了 `segment_cols`):同一 (检测组合, fold, symbol, 买点事件键) 的多行是同一个买点事件,
      按包含-排斥拆成若干 ±1 条目,使后缀累加后每个格恰好把这个买点事件计一次(算法见 `_segment_masses`)。
    两种口径下条目数都不等于行数的对应关系不要假设——`flat/states/sym_codes/seg` 彼此等长 = 条目数。

    字段:
        flat: 每个条目的格张量扁平索引,空间 = combo 轴 × pred 轴 × **fold 轴**(见模块文档
            "两套扁平空间"的说明,与 `rank_cells` 等下游函数所在的空间不同)。
        states: 形状 (n_entries, 4) 的有符号 int16,四态(fp_up/fp_down/fp_both/fp_none)质量。
            它是该买点事件内合格买点 bar 的**计数**、不是 one-hot;买点事件口径下还带条目符号。构造时断言 |x| < 2^15。
        sym_codes: 每个条目的 symbol 整数编码(供 `tensor(weights=...)` 按股加权)。编码只对
            **保留行**(row_keep 之后)的 symbol 值做(复审 M-5)——不对全表 symbol 编码再切片,否则被丢弃
            行的 symbol 仍占码位(幽灵 symbol),`bootstrap()` 的 `rng.multinomial(prep.n_sym, uniform)`
            会把这些从不产生任何计数的码位也纳入重采样支持集,让总有效簇数额外多一层随机性、CI 偏宽。
        seg: 形状 (n_entries,) 的 int8,条目的买点事件计数(买点事件口径 ±1;逐行口径全 1)。
        symbols: np.ndarray[object],下标 = sym 码、值 = 股票名。跨表(如两份长表各自 prepare)按名对齐用。
        n_sym: symbol 编码空间的长度 = len(symbols)。经 `prepare()` 单表路径或 `prepare_shards()` 得到时
            精确等于保留行去重后的 symbol 数(稠密无空洞的连续编号)。
        shape: 格张量完整形状 = combo 轴长... + pred 轴长... + (n_folds, 4)。
        n_combo_axes / n_pred_axes: combo 轴、pred 轴各自的个数(用于从坐标切出各段)。
        fold_axis: fold 轴在 shape 中的下标(= n_combo_axes + n_pred_axes)。
        combo_levels / pred_specs / folds: 原样保留的输入参数,供 `cell_coords` 等下游函数把
            数字坐标映射回可读的档位值。
        row_keep: 长度 = 原始行数的布尔掩码,标记哪些行过了档位过滤(被丢弃的行是 combo/pred 值不在
            档位表里、fold 不在 folds 里、或谓词列是 NaN)。
        n_rows_raw: 过档位过滤后保留的原始行数(= row_keep.sum())。
        n_segments: 买点事件口径 = 去重后的买点事件数;逐行口径 = n_rows_raw(一行自成一组)。
    """
    flat: np.ndarray
    states: np.ndarray
    sym_codes: np.ndarray
    n_sym: int
    shape: tuple
    n_combo_axes: int
    n_pred_axes: int
    fold_axis: int
    combo_levels: dict
    pred_specs: list
    folds: list
    row_keep: np.ndarray
    seg: np.ndarray
    symbols: np.ndarray
    n_rows_raw: int
    n_segments: int


def _state_int16(states: np.ndarray) -> np.ndarray:
    """四态质量压到有符号 int16,越界直接报错(bar 计数 × 条目符号不该接近 2^15,越界说明上游口径坏了)。"""
    if len(states) and int(np.abs(states).max()) >= 2 ** 15:
        raise ValueError(f"四态质量绝对值 {int(np.abs(states).max())} 超出 int16 值域(须 < 2^15)")
    return states.astype(np.int16)


def _segment_key(df: pd.DataFrame, col: str, keep: np.ndarray) -> np.ndarray:
    """取一列买点事件键(保留行),必须是无缺失的整数列——键靠精确相等分组,浮点 / 缺失会静默拆散同一买点事件。"""
    if col not in df.columns:
        raise ValueError(f"买点事件键列 {col!r} 不在长表里(现有列 {list(df.columns)})")
    s = df[col]
    if not pd.api.types.is_integer_dtype(s):
        raise ValueError(f"买点事件键列 {col!r} 必须是整数列,实际 dtype {s.dtype}")
    v = s.to_numpy()[keep]
    if pd.isna(v).any():
        raise ValueError(f"买点事件键列 {col!r} 在保留行里有缺失值")
    return v.astype(np.int64)


def _segment_masses(cf, sym, seg_keys, V, st, pred_shape):
    """买点事件口径的核心:把同一买点事件的多行合成若干带符号的点质量条目(逐分片调用)。

    参数:
        cf: int64,每行的 combo 码 × n_folds + fold 码。
        sym: int64,每行的 symbol 码。
        seg_keys: 买点事件键列(int64 数组的列表)。组键 = (cf, sym, 买点事件键)。
        V: 形状 (n, P) 的 int16,每行在各 pred 轴上满足的最紧档号(-1 行已由调用方丢弃)。
        st: 形状 (n, 4) 的 int64,每行四态。
        pred_shape: pred 各轴档数。

    返回:
        (g_cf, g_sym, g_st, ent_g, meet, sign)——前三个逐买点事件组:cf、symbol 码、四态;
        后三个逐条目:所属组下标、落点档号向量 (n_entries, P)、符号(int8,±1)。

    要解决的问题:一个买点事件在格 c(pred 档号向量)上被计数,当且仅当它至少有一行在每条 pred 轴上
    都 ≥ c(任一行过该格全部闸,就算这个买点事件过闸)。记 D(v) = {c : c ≤ v},买点事件的计数函数就是
    并集指示函数 1[c ∈ ∪_i D(v_i)]。格张量的后缀累加把落在 m 的单位质量变成 1[c ≤ m] = 1[c ∈ D(m)],
    所以要找一组带符号的点质量,让它们下集指示函数之和逐格等于这个并集指示函数。

    每个组的处理:
        1. 组内四态必须完全相同——扫描端按买点事件的 span 缓存标签,同一买点事件的各行四态天然一样;
           不同就说明这个前提被破坏了,直接报错。
        2. 帕累托约简:去掉重复的 v 和被别的行逐分量支配的行(被支配行的下集含在支配者的下集里,
           对并集没有贡献),剩下 k 个互不可比的向量。
        3. k ≤ SEG_SUBSET_MAX_K:包含-排斥。对每个非空子集 S,在 meet(S) = 分量最小值处放
           (-1)^{|S|+1}。正确性:c ≤ 每个 v_i ⟺ c ≤ 它们的分量最小值,所以 ∩_{i∈S} D(v_i) = D(meet(S));
           包含-排斥 1[∪A_i] = Σ_S (-1)^{|S|+1} 1[∩_{i∈S} A_i] 对指示函数逐点精确成立。于是后缀累加
           后每格得到的是整数 0 或 1,全程整数运算,没有舍入。
        4. k > SEG_SUBSET_MAX_K:2^k 个子集太多,改在谓词格上直接算。先得到并集指示函数
           I[c] = any_i(v_i ≥ c)(在各 v_i 处置 1,再沿每轴做后缀或),再沿每轴做前向差分
           μ ← μ − shift₊₁(μ)。前向差分正是后缀累加的逆运算,所以后缀累加 μ 精确还原 I。
           μ 的非零值可能是 ±2 这类,按 |μ| 拆成多个 ±1 条目。谓词格格数 > SEG_GRID_MAX 时报错。

    按股整数权重(bootstrap)对同一组的全部条目是同一个倍数,上面的逐格恒等式乘上它仍精确成立。

    向量化:分组用一次 np.lexsort(档号向量也进排序键,重复的 v 因此相邻);帕累托按组大小分桶、
    包含-排斥按 k 分桶,都在桶内整批做,不逐组循环(真实长表里绝大多数组只有 1~3 行)。
    """
    n, P = V.shape
    if n == 0:
        z = np.zeros(0, np.int64)
        return z, z, np.zeros((0, 4), np.int64), z, np.zeros((0, P), V.dtype), np.zeros(0, np.int8)
    order = np.lexsort([V[:, j] for j in range(P - 1, -1, -1)] + list(reversed(seg_keys)) + [sym, cf])
    cf, sym, V, st = cf[order], sym[order], V[order], st[order]
    seg_keys = [k[order] for k in seg_keys]
    new = np.ones(n, bool)                              # 组内首行
    d = (cf[1:] != cf[:-1]) | (sym[1:] != sym[:-1])
    for k in seg_keys:
        d |= k[1:] != k[:-1]
    new[1:] = d
    bad = np.flatnonzero(~d & (st[1:] != st[:-1]).any(1)) + 1
    if len(bad):
        i = int(bad[0])
        raise ValueError(
            f"买点事件口径:{len(bad)} 处同一买点事件的各行四态不一致(例:symbol 码 {int(sym[i])}、买点事件键 "
            f"{[int(k[i]) for k in seg_keys]}:{st[i - 1].tolist()} vs {st[i].tolist()})。同一买点事件的标签应由买点事件"
            "本身决定,各行必须相同——扫描端按 span 缓存标签的前提被破坏了,或买点事件键列没有唯一确定买点事件。"
        )
    g_rows = np.flatnonzero(new)
    g_cf, g_sym, g_st = cf[g_rows], sym[g_rows], st[g_rows]
    gid = np.cumsum(new) - 1
    uniq = np.ones(n, bool)
    uniq[1:] = ~(~d & (V[1:] == V[:-1]).all(1))         # 同组且档号向量相同 → 重复行
    V, gid = V[uniq], gid[uniq]

    # 帕累托约简:按组大小 m 分桶,桶内 (G, m, m) 两两比较
    start = np.flatnonzero(np.r_[True, gid[1:] != gid[:-1]])
    size = np.diff(np.r_[start, len(gid)])
    alive = np.ones(len(gid), bool)
    for m in np.unique(size[size >= 2]):
        gs = start[size == m]
        step = max(1, _CHUNK_BYTES // int(m * m * max(P, 1)))
        for a in range(0, len(gs), step):
            idx = gs[a:a + step, None] + np.arange(m)
            W = V[idx]                                              # (G, m, P)
            ge = (W[:, None, :, :] >= W[:, :, None, :]).all(-1)     # ge[g, i, j]:行 j 逐分量 ≥ 行 i
            ge[:, np.arange(m), np.arange(m)] = False
            alive[idx[ge.any(-1)]] = False                          # 已去重,≥ 即严格支配
    V, gid = V[alive], gid[alive]

    n_g = len(g_rows)
    k_of = np.bincount(gid, minlength=n_g)
    start = np.r_[0, np.cumsum(k_of)[:-1]]
    ent_g, meets, signs = [], [], []
    for k in np.unique(k_of):
        k = int(k)
        gs = np.flatnonzero(k_of == k)
        rows = start[gs][:, None] + np.arange(k)
        if k == 1:
            ent_g.append(gs); meets.append(V[rows[:, 0]]); signs.append(np.ones(len(gs), np.int8))
        elif k <= SEG_SUBSET_MAX_K:
            n_sub = 1 << k
            pop = np.array([bin(s).count("1") for s in range(1, n_sub)])
            sgn = np.where(pop % 2 == 1, 1, -1).astype(np.int8)     # (-1)^{|S|+1}
            step = max(1, _CHUNK_BYTES // (n_sub * max(P, 1) * V.itemsize))
            for a in range(0, len(gs), step):
                W = V[rows[a:a + step]]                             # (G, k, P)
                M = np.empty((len(W), n_sub, P), V.dtype)           # M[:, s] = 子集掩码 s 的 meet
                M[:, 0, :] = np.iinfo(V.dtype).max                  # 空子集取 +∞,单元素子集 min 后即自身
                for b in range(k):
                    M[:, 1 << b:2 << b, :] = np.minimum(M[:, :1 << b, :], W[:, b:b + 1, :])
                ent_g.append(np.repeat(gs[a:a + step], n_sub - 1))
                meets.append(M[:, 1:, :].reshape(-1, P))
                signs.append(np.tile(sgn, len(W)))
        else:
            n_grid = int(np.prod(pred_shape))
            if n_grid > SEG_GRID_MAX:
                raise ValueError(
                    f"买点事件口径:有买点事件约简后仍有 {k} 行互不可比(> {SEG_SUBSET_MAX_K}),需要在谓词格上做差分,"
                    f"但谓词格有 {n_grid} 格(> {SEG_GRID_MAX}),拒绝计算——请减少谓词轴或档数。"
                )
            step = max(1, _CHUNK_BYTES // (n_grid * 4))
            for a in range(0, len(gs), step):
                W = V[rows[a:a + step]]                             # (G, k, P)
                G = len(W)
                I = np.zeros((G,) + tuple(pred_shape), bool)
                I[(np.repeat(np.arange(G), k),) + tuple(W.reshape(-1, P).T)] = True
                for ax in range(1, P + 1):                          # 后缀或:I[c] = any_i(v_i ≥ c)
                    I = np.flip(np.logical_or.accumulate(np.flip(I, ax), axis=ax), ax)
                mu = I.astype(np.int32)
                for ax in range(1, P + 1):                          # 前向差分:后缀累加的逆
                    nxt = np.zeros_like(mu)
                    src = [slice(None)] * mu.ndim; dst = list(src)
                    src[ax] = slice(1, None); dst[ax] = slice(None, -1)
                    nxt[tuple(dst)] = mu[tuple(src)]
                    mu -= nxt
                nz = np.nonzero(mu)
                val = mu[nz]; rep = np.abs(val)
                ent_g.append(np.repeat(gs[a:a + step][nz[0]], rep))
                meets.append(np.repeat(np.stack(nz[1:], 1).astype(V.dtype), rep, axis=0))
                signs.append(np.repeat(np.sign(val).astype(np.int8), rep))
    return g_cf, g_sym, g_st, np.concatenate(ent_g), np.concatenate(meets), np.concatenate(signs)


def prepare(df: pd.DataFrame, combo_levels: dict, pred_specs: list, fold_col: str, folds: list,
            sym_categories=None, allow_empty: bool = False, segment_cols=None) -> Prepared:
    """把长表离散化为格张量条目,一次性算出每个条目该落进哪个格。

    参数:
        df: 候选长表,至少含 combo_levels 的列(真扫维,精确等于档位值)、pred_specs 的列
            (过滤型/where 维,原始量交给 `pred_level_index`)、fold_col 列、"symbol" 列、
            STATES 四态列;买点事件口径下还要有 segment_cols 各列。
        combo_levels: {列名: 档位列表},组合维,行值须**精确等于**某个档位(用 pd.Categorical
            对齐,不在表里 → codes=-1 → 该行被丢弃)。
        pred_specs: [(列名, op, levels), ...],过滤型/where 维,逐条交给 `pred_level_index`。
        fold_col: fold 列名。
        folds: fold 档位列表(顺序即 fold 轴下标顺序)。
        sym_categories: symbol 的码空间(None = 就地按保留行的唯一值排序编码)。只有
            `prepare_shards()` 会传它——分片处理时各片必须落在同一个码空间里,否则
            同一只股票在不同片会拿到不同码位、bootstrap 的按股重采样就散了。传了它
            以后 n_sym 是码空间长度(可能含未被任何保留行用到的幽灵码位),压实成
            "保留行里第 i 小的 symbol → 码 i" 由 `prepare_shards()` 统一做。
        allow_empty: 允许 0 行保留(只有分片处理会传 True——单个分片全被丢弃是正常的,
            "一行不剩"这条错误由 `prepare_shards()` 在全部分片上统一判)。
        segment_cols: None = 逐行口径(一行一个条目,只给合成测试与逐行核对用);
            列名列表 = 买点事件口径,这些列(整数)与 (检测组合, fold, symbol) 一起构成买点事件的组键,
            如 `["seg_id"]` 或 `["<end_node>.start", "<end_node>.end"]`。同一检测组合内每个买点事件只计一次,
            任一行过某格全部闸,这个买点事件就在该格被计数(见 `_segment_masses`)。

    返回:
        Prepared(字段含义见其类文档)。

    行为:
        任何一个维度(combo/pred/fold)算出 -1(不在档位表 / 不满足任何档)的行会被整行丢弃;
        若丢弃后一行不剩,直接报错而不是静默产出全零张量——常见原因是列名 / 量纲 / dtype 口径
        与 combo_levels / pred_specs 对不上(下游的 `tensor()` 会全零、`score()`/`rank_cells()`
        会全部"无法评估",不报错时这类口径错误极易被当成"确实没有稳健区"而漏检)。
    """
    ci = [pd.Categorical(df[c], categories=lv).codes.astype(np.int64) for c, lv in combo_levels.items()]
    pi = [pred_level_index(df[c].values, op, lv) for c, op, lv in pred_specs]
    fi = pd.Categorical(df[fold_col], categories=folds).codes.astype(np.int64)
    keep = fi >= 0
    for x in ci + pi:
        keep &= x >= 0
    if not np.any(keep) and not allow_empty:
        raise ValueError(
            "prepare(): 0 行保留——combo/pred 列名或量纲与 combo_levels/pred_specs 档位不匹配、"
            "fold 列的值不在 folds 里、或谓词列全为 NaN 都会导致这个结果,请检查输入长表与档位定义。"
        )
    combo_shape = [len(lv) for lv in combo_levels.values()]
    pred_shape = [len(lv) for _, _, lv in pred_specs]
    axes = combo_shape + pred_shape + [len(folds)]
    # 只对保留行编码(复审 M-5),不先对全表 symbol 编码再切片:后者会让被 keep 丢弃行的 symbol
    # 仍占码位("幽灵 symbol"),bootstrap() 的 rng.multinomial(prep.n_sym, uniform) 会把它们纳入
    # 重采样支持集、CI 偏宽。转成 object 再编码,是因为 parquet 读回的 symbol 是 category 类型,
    # 直接 pd.Categorical 会沿用它自带的(含未保留 symbol 的)类别表。
    cat = pd.Categorical(np.asarray(df["symbol"], dtype=object)[keep],
                         **({} if sym_categories is None else {"categories": sym_categories}))
    sym = cat.codes.astype(np.int64)
    if len(sym) and (sym < 0).any():
        raise ValueError(
            f"prepare(): df['symbol'] 在保留行中有 {(sym < 0).sum()} 行为 NaN(pd.Categorical 编码为 -1)。"
            "这些行不会被 keep 掩码丢弃(symbol 不参与 combo/pred/fold 的丢行判定),但下游 "
            "tensor(weights=...) 会用 weights[-1](=weights 数组最后一个元素)给这些行加权,"
            "静默地把它们当成'最后一只股票'——请先清洗长表 symbol 列的 NaN 再调用 prepare()。"
        )
    symbols = np.asarray(cat.categories, dtype=object)
    st_rows = df[STATES].values[keep].astype(np.int64)
    n_kept = int(keep.sum())
    if segment_cols is None:
        flat = np.ravel_multi_index(tuple(x[keep] for x in ci + pi) + (fi[keep],), axes)
        states, sym_codes, seg, n_segments = st_rows, sym, np.ones(n_kept, np.int8), n_kept
    else:
        if not list(segment_cols):
            raise ValueError("prepare(): segment_cols 不能为空列表(逐行口径请传 None)")
        n_f = len(folds)
        cc = (np.ravel_multi_index(tuple(x[keep] for x in ci), combo_shape) if ci
              else np.zeros(n_kept, np.int64))
        V = (np.stack([x[keep] for x in pi], 1) if pi else np.zeros((n_kept, 0), np.int16))
        keys = [_segment_key(df, c, keep) for c in segment_cols]
        g_cf, g_sym, g_st, ent_g, meet, sign = _segment_masses(cc * n_f + fi[keep], sym, keys, V, st_rows, pred_shape)
        e_cf = g_cf[ent_g]
        pflat = np.ravel_multi_index(tuple(meet.T), pred_shape) if pi else 0
        flat = (e_cf // n_f * int(np.prod(pred_shape)) + pflat) * n_f + e_cf % n_f
        states = sign[:, None].astype(np.int64) * g_st[ent_g]
        sym_codes, seg, n_segments = g_sym[ent_g], sign, len(g_cf)
    return Prepared(flat=flat, states=_state_int16(states), sym_codes=sym_codes, n_sym=len(symbols),
                    shape=tuple(axes) + (4,), n_combo_axes=len(combo_levels), n_pred_axes=len(pred_specs),
                    fold_axis=len(axes) - 1, combo_levels=combo_levels, pred_specs=pred_specs, folds=folds,
                    row_keep=keep, seg=seg, symbols=symbols, n_rows_raw=n_kept, n_segments=n_segments)


def prepare_shards(shards, combo_levels: dict, pred_specs: list, fold_col: str, folds: list,
                   segment_cols=None, fold_from=None) -> Prepared:
    """逐片读 parquet 分片 → prepare → 拼接,结果与"先 concat 全部分片再 prepare 一次"的格张量相同。

    参数:
        shards: parquet 分片路径序列(顺序即拼接顺序)。
        segment_cols: 同 `prepare()`。
        fold_from: None = 折取自 fold_col 列;(源列名, fn) = 派生折——逐片读源列,fn(pd.Series) 返回
            等长的折标签(字符串)序列,不读 fold_col。`folds` 仍是显式档位表,标签不在表里的行被丢弃。
            用于长表里没有现成列的折,如时间窗号 (buy_date − 训练窗起点).days // 窗宽。
        其余参数同 `prepare()`。

    为什么要分片:`prepare()` 之后,下游只用 flat / states / sym_codes / seg 这几个数组——明细列
    再没人回头查。整表读入却要按**全部列**付内存(2026-09-07 实测 396B/行),而条目数组只要
    约 15B/条目。分片读让峰值只剩"一片 + 结果数组"。

    分片之间 symbol 必须不相交(扫描端按股票批次落盘,天然满足),相交直接报错:买点事件口径的分组
    在片内做,同一只股票跨片会把同一个买点事件拆进两片、各计一次;逐行口径虽不受影响,但相交本身
    说明分片不是同一次扫描按股票切出来的。

    symbol 码空间:先扫一遍各片的 symbol 列建全局表(只读一列,便宜),各片用同一码空间编码,
    最后把实际用到的码位压实。压实后的语义与 `prepare()` 单表路径完全一致——两者都是
    "保留行里第 i 小的 symbol → 码 i"(`pd.Categorical` 无 categories 时按排序后的唯一值编码,
    `np.unique` 同样有序,故 `searchsorted` 重映射后逐元素相等)。不压实则会留下幽灵码位,
    `bootstrap()` 的 `rng.multinomial(n_sym, uniform)` 会把它们纳入重采样支持集、让 CI 偏宽。
    """
    shards = list(shards)
    if not shards:
        raise ValueError("prepare_shards(): 没有任何分片")
    fold_src = fold_col if fold_from is None else fold_from[0]
    fold_name = fold_col if fold_from is None else _DERIVED_FOLD
    cols = (list(combo_levels) + [c for c, _, _ in pred_specs] + [fold_src, "symbol"] + STATES
            + list(segment_cols or []))
    cols = list(dict.fromkeys(cols))            # 去重且保序(fold_col 可能与某个轴同名)
    seen = set()
    for sp in shards:
        s = set(pd.read_parquet(sp, columns=["symbol"])["symbol"].unique())
        both = seen & s
        if both:
            raise ValueError(f"prepare_shards(): 分片 {sp} 与前面的分片有共同的 symbol {sorted(both)[:5]}"
                             f"(共 {len(both)} 只)——分片之间 symbol 必须不相交")
        seen |= s
    all_syms = np.array(sorted(seen), dtype=object)

    n_cells_total = int(np.prod([len(lv) for lv in combo_levels.values()]
                                + [len(lv) for _, _, lv in pred_specs] + [len(folds)]))
    flat_dt = np.int32 if n_cells_total < 2 ** 31 else np.int64
    sym_dt = np.int16 if len(all_syms) < 2 ** 15 else np.int32
    flats, states_l, syms_l, segs_l, keeps = [], [], [], [], []
    n_segments = 0
    for sp in shards:
        df = pd.read_parquet(sp, columns=cols)
        if fold_from is not None:
            lab = fold_from[1](df[fold_src])
            if len(lab) != len(df):
                raise ValueError(f"prepare_shards(): fold_from 的 fn 返回 {len(lab)} 个标签,分片 {sp} 有 {len(df)} 行")
            df[_DERIVED_FOLD] = np.asarray(lab, dtype=object)
        pr = prepare(df, combo_levels, pred_specs, fold_name, folds,
                     sym_categories=all_syms, allow_empty=True, segment_cols=segment_cols)
        # 逐片就把 dtype 压到够用为止再攒:这几个数组是全程唯一的常驻大件。取值范围都是硬边界:
        # flat < 格数、states 已是 int16(构造时断言过)、seg 是 ±1、sym_codes < 股票数。
        flats.append(pr.flat.astype(flat_dt)); states_l.append(pr.states); segs_l.append(pr.seg)
        syms_l.append(pr.sym_codes.astype(sym_dt)); keeps.append(pr.row_keep)
        n_segments += pr.n_segments
        del df, pr
    flat = np.concatenate(flats); del flats
    states = np.concatenate(states_l); del states_l
    seg = np.concatenate(segs_l); del segs_l
    sym_raw = np.concatenate(syms_l); del syms_l
    row_keep = np.concatenate(keeps); del keeps
    if not len(flat):
        raise ValueError(
            "prepare_shards(): 全部分片合计 0 行保留——combo/pred 列名或量纲与 combo_levels/"
            "pred_specs 档位不匹配、fold 列的值不在 folds 里、或谓词列全为 NaN 都会导致这个结果。"
        )
    used = np.unique(sym_raw)
    sym = np.searchsorted(used, sym_raw).astype(sym_dt)
    axes = [len(lv) for lv in combo_levels.values()] + [len(lv) for _, _, lv in pred_specs] + [len(folds)]
    return Prepared(flat=flat, states=states, sym_codes=sym, n_sym=len(used),
                    shape=tuple(axes) + (4,), n_combo_axes=len(combo_levels),
                    n_pred_axes=len(pred_specs), fold_axis=len(axes) - 1,
                    combo_levels=combo_levels, pred_specs=pred_specs, folds=folds, row_keep=row_keep,
                    seg=seg, symbols=all_syms[used], n_rows_raw=int(row_keep.sum()), n_segments=n_segments)



def prepare_frames(frames, combo_levels: dict, pred_specs: list, fold_col: str, folds: list,
                   segment_cols=None) -> Prepared:
    """逐片 DataFrame → prepare → 拼接,结果与把这些片写成分片再 `prepare_shards` 相同。

    给不落成分片、边读边接的数据用(如延迟标签模式的扫描结果逐片接上补算的标签)。frames 只遍历一次:
    各片先按本片保留行各自编码 symbol,最后并成全局码表再重映射——保留行里第 i 小的 symbol → 码 i,
    与 `prepare_shards` 压实后的编码一致。分片之间 symbol 必须不相交(理由同 `prepare_shards`),相交直接报错。
    其余参数同 `prepare()`。
    """
    seen, pieces = set(), []
    for df in frames:
        s = set(pd.unique(np.asarray(df["symbol"], dtype=object)))
        both = seen & s
        if both:
            raise ValueError(f"prepare_frames(): 这一片与前面的片有共同的 symbol {sorted(both)[:5]}"
                             f"(共 {len(both)} 只)——片之间 symbol 必须不相交")
        seen |= s
        pieces.append(prepare(df, combo_levels, pred_specs, fold_col, folds, allow_empty=True,
                              segment_cols=segment_cols))
        del df
    if not pieces or not sum(len(pr.flat) for pr in pieces):
        raise ValueError(
            "prepare_frames(): 全部片合计 0 行保留——combo/pred 列名或量纲与 combo_levels/pred_specs 档位不匹配、"
            "fold 列的值不在 folds 里、或谓词列全为 NaN 都会导致这个结果。"
        )
    used = np.unique(np.concatenate([pr.symbols for pr in pieces]).astype(object))
    sym_dt = np.int16 if len(used) < 2 ** 15 else np.int32
    sym = np.concatenate([np.searchsorted(used, pr.symbols)[pr.sym_codes].astype(sym_dt) for pr in pieces])
    axes = [len(lv) for lv in combo_levels.values()] + [len(lv) for _, _, lv in pred_specs] + [len(folds)]
    return Prepared(flat=np.concatenate([pr.flat for pr in pieces]),
                    states=np.concatenate([pr.states for pr in pieces]), sym_codes=sym, n_sym=len(used),
                    shape=tuple(axes) + (4,), n_combo_axes=len(combo_levels), n_pred_axes=len(pred_specs),
                    fold_axis=len(axes) - 1, combo_levels=combo_levels, pred_specs=pred_specs, folds=folds,
                    row_keep=np.concatenate([pr.row_keep for pr in pieces]),
                    seg=np.concatenate([pr.seg for pr in pieces]), symbols=used,
                    n_rows_raw=int(sum(pr.n_rows_raw for pr in pieces)),
                    n_segments=int(sum(pr.n_segments for pr in pieces)))

def _entry_weights(prep: Prepared, weights, fn: str):
    """按股整数权重 → 逐条目权重(None 原样返回)。非整数直接拒绝:内部 np.rint 逐格取整会让分数权重漂移。"""
    if weights is None:
        return None
    weights = np.asarray(weights, dtype=float)
    if not np.allclose(weights, np.rint(weights)):
        raise ValueError(
            f"{fn}(): weights 必须是整数计数(如按股 bootstrap 次数);非整数权重会被内部 "
            "np.rint 逐格取整产生有偏漂移,这里直接拒绝而不是静默取整。"
        )
    return weights[prep.sym_codes]


def _pred_suffix_cumsum(T: np.ndarray, prep: Prepared) -> np.ndarray:
    """沿全部 pred 轴做后缀累加:落在紧档的质量也属于所有更松的档(下标 0 = 最松)。"""
    for ax in range(prep.n_combo_axes, prep.n_combo_axes + prep.n_pred_axes):
        T = np.flip(np.cumsum(np.flip(T, axis=ax), axis=ax), axis=ax)
    return T


def tensor(prep: Prepared, weights=None) -> np.ndarray:
    """把 Prepared 的条目一次 bincount 成四态格张量,再沿 pred 轴做后缀累加。

    参数:
        prep: `prepare()` 的输出。
        weights: 按 symbol 索引的**整数计数**(如按股 bootstrap 的重采样次数),形状 (prep.n_sym,);
            None = 全 1(不加权)。必须是整数——内部用 `np.rint` 逐格取整,分数权重(如 Bayesian
            bootstrap 的连续权重)会被取整成有偏结果,这里直接拒绝非整数权重而不是让它静默漂移。

    返回:
        形状 = prep.shape 的 int64 张量,最后一维 = 四态(fp_up/fp_down/fp_both/fp_none)计数。
        combo 轴、fold 轴是精确计数(不做累加);**pred 轴做后缀累加**——下标 j(更紧的档)的
        计数会被加进下标 < j(更松的档)的格,因为满足紧档的行天然也满足所有更松的档
        (下标 0 = 最松,已含全部满足任一档的行)。买点事件口径下条目带负质量,后缀累加后逐格精确
        抵消成「每个买点事件计一次」(见 `_segment_masses`);bincount 的浮点和在这个量级上是精确整数。
    """
    n_cells = int(np.prod(prep.shape[:-1]))
    w = _entry_weights(prep, weights, "tensor")
    T = np.empty((n_cells, 4), dtype=np.int64)
    for s in range(4):
        col = prep.states[:, s].astype(float)
        T[:, s] = np.rint(np.bincount(prep.flat, weights=col if w is None else col * w, minlength=n_cells)).astype(np.int64)
    return _pred_suffix_cumsum(T.reshape(prep.shape), prep)


def segment_tensor(prep: Prepared, weights=None) -> np.ndarray:
    """每格的买点事件数张量:形状 prep.shape[:-1](combo + pred + fold),pred 轴后缀累加,int64。

    与 `tensor()` 同一套条目与后缀累加,只是质量换成条目的买点事件计数 `seg`。买点事件口径下 = 过该格全部闸
    的买点事件个数(同一买点事件多行只计一次);逐行口径下 = 行数。`weights` 同 `tensor()`。
    """
    n_cells = int(np.prod(prep.shape[:-1]))
    w = _entry_weights(prep, weights, "segment_tensor")
    col = prep.seg.astype(float)
    S = np.rint(np.bincount(prep.flat, weights=col if w is None else col * w, minlength=n_cells)).astype(np.int64)
    return _pred_suffix_cumsum(S.reshape(prep.shape[:-1]), prep)


def stock_sums(prep: Prepared, cells, fold_mode: str = "per_fold"):
    """逐股、逐格的四态汇总,供筛选 / 验证 / 学习端做按股去簇的误差与按股 bootstrap。

    参数:
        prep: `prepare()` / `prepare_shards()` 的输出。
        cells: 格坐标元组的列表,坐标 = combo 档号... + pred 档号...(不含 fold)。
        fold_mode: "per_fold" = 各折分开;"pooled" = 各折合并。

    返回:
        (U, D, N),形状均为 (n_sym, len(cells), F) 的 int64,F = n_folds("per_fold")或 1("pooled")。
        U = up 和;D = up+down+both 和(首次穿越率的分母);N = 四态和。对全部股求和即等于
        `tensor()` 在该格的对应量。

    算法:条目按 flat 排序一次。flat 以 combo 码为最高位,所以一个检测组合的全部条目在排序后连成
    一段,用 searchsorted 取出;段内拆出 pred 档号与 fold,做「每条 pred 轴档号 ≥ 格的档号」掩码
    (等价于后缀累加:质量落在更紧档的条目也属于这个格),再按 symbol(× fold)bincount。
    """
    if fold_mode not in ("per_fold", "pooled"):
        raise ValueError(f"stock_sums(): fold_mode 须为 'per_fold' 或 'pooled',实际 {fold_mode!r}")
    nc, npd = prep.n_combo_axes, prep.n_pred_axes
    combo_shape, pred_shape = prep.shape[:nc], prep.shape[nc:nc + npd]
    n_f = len(prep.folds)
    n_pred_cells = int(np.prod(pred_shape))
    F = n_f if fold_mode == "per_fold" else 1
    cells = [tuple(int(x) for x in c) for c in cells]
    U = np.zeros((prep.n_sym, len(cells), F), np.int64)
    D = np.zeros_like(U); N = np.zeros_like(U)
    order = np.argsort(prep.flat, kind="stable")
    sflat = prep.flat[order].astype(np.int64)
    for j, c in enumerate(cells):
        if len(c) != nc + npd:
            raise ValueError(f"stock_sums(): 格坐标 {c} 的维数应为 {nc + npd}(combo+pred,不含 fold)")
        cc = int(np.ravel_multi_index(c[:nc], combo_shape)) if nc else 0
        lo_flat = cc * n_pred_cells * n_f
        lo, hi = np.searchsorted(sflat, [lo_flat, lo_flat + n_pred_cells * n_f])
        rest = sflat[lo:hi] - lo_flat
        m = np.ones(hi - lo, bool)
        if npd:
            for p, lv in zip(np.unravel_index(rest // n_f, pred_shape), c[nc:]):
                m &= p >= lv
        rows = order[lo:hi][m]
        key = prep.sym_codes[rows].astype(np.int64) * F + ((rest[m] % n_f) if F > 1 else 0)
        st = prep.states[rows].astype(float)
        size = prep.n_sym * F
        up = np.bincount(key, weights=st[:, 0], minlength=size)
        den = up + np.bincount(key, weights=st[:, 1] + st[:, 2], minlength=size)
        tot = den + np.bincount(key, weights=st[:, 3], minlength=size)
        U[:, j, :] = np.rint(up).astype(np.int64).reshape(prep.n_sym, F)
        D[:, j, :] = np.rint(den).astype(np.int64).reshape(prep.n_sym, F)
        N[:, j, :] = np.rint(tot).astype(np.int64).reshape(prep.n_sym, F)
    return U, D, N


def degenerate_mask(seg_T: np.ndarray, prep: Prepared) -> np.ndarray:
    """退化格掩码:形状 combo + pred(不含 fold)的布尔张量。

    某格在任一 pred 轴上档号 j > 0,且它各折的买点事件数与同轴 j-1 档(其余坐标相同)逐折全等 → True。
    含义:这道闸从 j-1 档收紧到 j 档,在这个格上一个买点事件都没筛掉,紧档与松档是同一批样本——
    它不是一个独立的格,联合识别时不该当成另一个候选去参与挑选。

    参数:
        seg_T: `segment_tensor(prep)` 的输出,形状 prep.shape[:-1](最后一维是 fold)。
        prep: 同一份 Prepared(提供 combo / pred 轴的位置)。
    """
    if seg_T.shape != prep.shape[:-1]:
        raise ValueError(f"degenerate_mask(): seg_T 形状 {seg_T.shape} 应为 {prep.shape[:-1]}")
    out = np.zeros(seg_T.shape[:-1], bool)
    for ax in range(prep.n_combo_axes, prep.n_combo_axes + prep.n_pred_axes):
        same = (np.diff(seg_T, axis=ax) == 0).all(axis=-1)          # 位置 j-1 处比较的是 j 与 j-1
        pad_shape = list(same.shape); pad_shape[ax] = 1
        out |= np.concatenate([np.zeros(pad_shape, bool), same], axis=ax)
    return out


def fp_count(T: np.ndarray):
    """从四态计数张量算首次穿越率(FP)与分母(去掉最后的四态维)。

    FP = up / (up+down+both)(**none 不进分母**);分母为 0 → FP = NaN(该格该 fold 无样本可判)。

    返回:
        (fp, count):count = 四态之和(含 none),用于功效线判定;fp 用于算 delta/score。
    """
    den = T[..., 0] + T[..., 1] + T[..., 2]
    with np.errstate(invalid="ignore", divide="ignore"):
        fp = np.where(den > 0, T[..., 0] / np.maximum(den, 1), np.nan)
    return fp, T.sum(-1)


def score(fp, count, ref_index: tuple, min_count: int):
    """算每格相对参照格的"每 fold 增量"、fold 最小值、以及可评估性。

    参数:
        fp: `fp_count()` 的第一个返回值,形状 = combo+pred 轴 + (n_folds,)(**不含**四态轴)。
        count: `fp_count()` 的第二个返回值,同形状。
        ref_index: 参照格坐标,**不含 fold 轴**(维度数 = combo 轴数 + pred 轴数,用来索引
            fp/count 除最后一维 fold 外的所有轴,取出的 `fp[ref_index]` 形状是 (n_folds,))。
        min_count: 功效线,单格单 fold 的四态计数和 < 此值 → 该 (格,fold) 不可评估。

    返回:
        s: 形状 = fp.shape[:-1],每格在所有 fold 上 delta 的最小值(悲观口径);不可评估 → NaN。
        evaluable: 同形状布尔,要求**所有** fold 都满足 count>=min_count 且 fp 有限。
        delta: 形状同 fp,delta[..., f] = fp[..., f] - fp[ref_index][f]。

    要求:
        参照格必须在**所有** fold 上 fp 有限,否则直接 `ValueError`。放过这种参照格的后果是
        静默的:该 fold 的 delta 会对**全体格**变 NaN,`nanmin` 会把"对所有 fold 取 min"悄悄
        退化成"只在 ref 有定义的 fold 上取 min",而 `evaluable` 完全不反映这个退化——ref 全部
        fold 都 NaN 时甚至会让所有满足计数门槛的格都被判定"可评估"、`s` 却全是 +inf。
    """
    ref_fp = fp[ref_index]                                  # 形状 (n_folds,)
    bad_folds = np.where(~np.isfinite(ref_fp))[0]
    if bad_folds.size:
        raise ValueError(
            f"参照格 ref_index={ref_index} 在 fold {bad_folds.tolist()} 上 fp=NaN"
            f"(该 fold 上 up+down+both=0,即该格在该 fold 全为 none 态,分母为 0)。"
            f"参照格必须在所有 fold 上都可计算 fp,请换一个参照格。"
        )
    delta = fp - ref_fp
    evaluable = (count >= min_count).all(-1) & np.isfinite(fp).all(-1)
    # 把非 ref 引起的 NaN(格自身某 fold 分母为 0)换成 +inf 再 nanmin,避免不可评估格的
    # 全 NaN 行触发 "All-NaN slice" 警告——这些格的 s 值本来就会被下面的 np.where 掩掉。
    with np.errstate(invalid="ignore"):
        safe = np.where(np.isfinite(delta), delta, np.inf)
    s = np.where(evaluable, np.nanmin(safe, axis=-1), np.nan)
    return s, evaluable, delta


def neighbor_min(s, evaluable, axes):
    """r=1 曼哈顿邻域(每次只在一个轴移一档)取 s 的最小值,只在**可评估的邻居**间生效。

    参数:
        s: 任意形状的分数张量(通常是 `score()` 的 s)。
        evaluable: 同形状布尔;不可评估的格既不参与自身的 s_nb(直接 NaN),也不作为任何
            其它格的邻居(即使数值上存在,也不会被别的格拿去取 min)。
        axes: 参与取邻域的轴下标列表(通常是 combo+pred 全部轴,不含 fold——fold 已经在
            `score()` 里被 min 掉了)。

    返回:
        s_nb: 同形状,可评估格 = 自身与所有可评估邻居的 min(抑制孤立尖峰);不可评估格 = NaN。
        n_eval_nb: 同形状 int64,实际参与取 min 的可评估邻居个数(网格边界外没有邻居,不做
            任何 padding——边/角格的邻居数天然小于内部格)。**不完整**读法是"0 表示这个格
            没有任何可评估邻居"——`take = evaluable & nb_ok` 同时要求**中心格自身**可评估,
            所以中心格自身不可评估时 n_eval_nb 恒为 0,即使周围确实存在可评估邻居;0 因此
            混合了"自身不可评估"和"自身可评估但邻居都不可评估"两种情况,不能单独当"邻居
            是否存在"的判据。
    """
    s_nb = np.where(evaluable, s, np.nan)
    n_eval = np.zeros(s.shape, dtype=np.int64)
    for ax in axes:
        for shift in (1, -1):
            nb = np.roll(s, shift, axis=ax)
            nb_ok = np.roll(evaluable, shift, axis=ax).copy()
            edge = [slice(None)] * s.ndim
            edge[ax] = 0 if shift == 1 else -1
            nb_ok[tuple(edge)] = False                         # 绕回的邻居不存在(无 pad)
            take = evaluable & nb_ok
            s_nb = np.where(take, np.fmin(s_nb, nb), s_nb)
            n_eval += take
    return s_nb, n_eval


def _boundary_dist(shape):
    """每格到网格边界的曼哈顿意义最小距离(内部格更大,边/角格为 0),供 `rank_cells` 末位平局键用。"""
    grids = np.indices(shape)
    d = np.min([np.minimum(g, (n - 1) - g) for g, n in zip(grids, shape)], axis=0)
    return d


def rank_cells(s_nb, n_eval_nb) -> np.ndarray:
    """把 s_nb/n_eval_nb 展平并按"推荐优先级"排序,返回扁平索引的降序排列。

    参数:
        s_nb / n_eval_nb: `neighbor_min()` 的两个返回值,形状 = combo+pred 轴(**不含** fold 轴,
            这个扁平空间与 `Prepared.flat` 所在的空间不是同一个,见模块文档)。

    排序键(从高到低优先级):
        1. 是否有可评估邻居(`n_eval_nb >= 1`)——0 邻居的格排到所有有邻居的格之后。
           一个没有任何可评估邻居的格,它的"邻域分"在方法论上不存在(不是真的"分数最高"),
           不该靠邻居数量偶然为 0 就赢过邻域内真的有支撑的格(**此条推翻 spec §4.2 第 7 步
           字面上"仅在并列时看 n_eval_nb"的排序,原因是浮点 s_nb 几乎不会精确并列,该字面
           排序在实践中会让 0 邻居的孤立尖峰系统性夺冠,与 spec §8"邻域分最高"的方法立意相悖)。
        2. s_nb 降序(分数越高越靠前;不可评估 = NaN 视作 -inf,排最后)。
        3. n_eval_nb 降序(同分时邻居越多、支撑越强越靠前)。
        4. 离边界距离降序(同分同邻居数时,内部格优先于边界格)。

    返回:
        扁平索引数组(对应 s_nb.shape 的 np.ravel_multi_index 意义下标),按上述键降序排列;
        用 `cell_coords()` 把某个扁平索引翻回可读坐标。
    """
    return rank_order(s_nb.ravel(), n_eval_nb.ravel(), _boundary_dist(s_nb.shape).ravel())


def rank_order(s_nb, n_eval_nb, boundary) -> np.ndarray:
    """`rank_cells` 的排序键作用在一维数组上(同下标的三个数组描述同一批格),返回下标的降序排列。

    格可以来自不同形状的网格(如联合识别里联合网格的格与筛选补充的格拼在一起排),
    离边界距离由调用方按各自网格算好(`boundary_dist`)。键的含义与优先级见 `rank_cells`。
    """
    s = np.asarray(s_nb, float)
    n = np.asarray(n_eval_nb)
    key_s = np.where(np.isfinite(s), s, -np.inf)
    no_neighbor = (n == 0).astype(np.int64)           # 硬前置键:0 可评估邻居的格排到有邻居的格之后
    return np.lexsort((-np.asarray(boundary), -n, -key_s, no_neighbor))


def boundary_dist(shape) -> np.ndarray:
    """每格到网格边界的最小距离(形状 = shape),供 `rank_order` 的末位平局键用。"""
    return _boundary_dist(shape)


def tolerance(s_nb, center: tuple) -> dict:
    """从 center 出发,沿每个轴双向数"s_nb 仍为正"的连续档数(容错跨度)。

    参数:
        s_nb: `neighbor_min()` 的输出,形状 = combo+pred 轴(**不含** fold 轴)。
        center: 中心格坐标,维度数与 s_nb.ndim 一致(**不含** fold 轴,与 `rank_cells` 返回的
            扁平索引 unravel 后的坐标是同一个空间)。

    返回:
        {轴下标: (向下连续档数, 向上连续档数)}——沿该轴从 center 往两边走,每一步要求
        s_nb 有限且 > 0 才计入,遇到不满足(含 NaN/≤0)或越界立即停止。
    """
    out = {}
    for ax in range(s_nb.ndim):
        down = up = 0
        idx = list(center)
        for i in range(center[ax] - 1, -1, -1):
            idx[ax] = i
            if np.isfinite(s_nb[tuple(idx)]) and s_nb[tuple(idx)] > 0:
                down += 1
            else:
                break
        for i in range(center[ax] + 1, s_nb.shape[ax]):
            idx[ax] = i
            if np.isfinite(s_nb[tuple(idx)]) and s_nb[tuple(idx)] > 0:
                up += 1
            else:
                break
        out[ax] = (down, up)
    return out


def save_cells_npz(path, R: dict, shape: tuple, folds, study_fingerprint: str = "", *,
                   count_unit: str | None = None) -> None:
    """把全量格级结果存成压缩 npz —— **这是识别端的全量产物,`cells.csv` 只是它的前 N 行摘要。**

    为什么不再写全量 CSV:`analyze_tensor` 的七个数组就是全部信息(本轮 265 万格约 230MB),
    而把它摊平成每格一行的 CSV 要先建 265 万个 Python dict(约 3~4GB)再写出 490MB 文本。
    代价之外还更难用:按坐标查一个格,张量是直接索引,CSV 得先读完半个 G 再逐列浮点匹配
    (2026-09-07 那轮做 40 次单闸切片正是这么凑的)。查询走 `cell_index` + `cell_metrics`。

    轴名与各轴档位**刻意不存**:它们已经是 `classification.json` 的内容,由
    `study_io.derived_axes()` 单源重建,存第二份只会引入不一致。**fold 档位反过来必须存**——
    它是 run 级口径(`Settings.folds`)、不在 classification 里,不存就只能靠读取端传对,
    那等于把口径正确性外包给调用方。`study_fingerprint` 供读取端核对同源性。
    定长 unicode 存 folds 是为了让 `np.load` 不需要 `allow_pickle`。
    `count_unit` 给出时另存一个同名键,标明 count 的计数口径(如买点事件口径 "event");不给则不存。
    """
    extra = {} if count_unit is None else {"count_unit": np.array(count_unit)}
    np.savez_compressed(
        path, fp=R["fp"], count=R["count"], s=R["s"], evaluable=R["evaluable"], delta=R["delta"],
        s_nb=R["s_nb"], n_eval_nb=R["n_eval_nb"], order=np.asarray(R["order"]),
        shape=np.asarray(shape, dtype=np.int64), folds=np.array(list(folds), dtype="U32"),
        study_fingerprint=np.array(study_fingerprint), **extra,
    )


def load_cells_npz(path) -> dict:
    """读 `save_cells_npz` 的产物。返回 {键: 数组},键同 `analyze_tensor` 的返回加 shape /
    study_fingerprint。不含轴信息——轴由 `study_io.derived_axes(classification)` 重建。"""
    with np.load(path) as z:
        return {k: z[k] for k in z.files}


def cell_index(combo_levels: dict, pred_specs: list, levels: dict) -> tuple:
    """档位值 → 格坐标(combo+pred 空间,不含 fold)。`cell_coords` 的逆。

    参数:
        combo_levels / pred_specs: `study_io.derived_axes()` 的两个返回值。
        levels: {轴名: 档位值},键与 `cell_coords()` 的输出键一致(combo 轴用参数名、
            pred 轴用长表列名);值必须**精确等于**该轴档位表里的某个元素(None 也可以)。
            缺任何一轴直接报错——少给一轴就不是一个格,静默当 0 档会悄悄查错格子。
    """
    axes = [(c, lv) for c, lv in combo_levels.items()] + [(c, lv) for c, _op, lv in pred_specs]
    missing = [c for c, _ in axes if c not in levels]
    extra = [c for c in levels if c not in {c for c, _ in axes}]
    if missing or extra:
        raise ValueError(f"cell_index(): 缺轴 {missing};不认识的键 {extra}(轴名以 cell_coords 的键为准)")
    idx = []
    for c, lv in axes:
        if levels[c] not in lv:
            raise ValueError(f"cell_index(): 轴 {c} 的值 {levels[c]!r} 不在档位表 {lv} 里")
        idx.append(lv.index(levels[c]))
    return tuple(idx)


def cell_metrics(cells: dict, idx: tuple, folds) -> dict:
    """读某个格的全部指标。`cells` = `load_cells_npz()` 的返回,`idx` = `cell_index()` 的返回。"""
    shape = tuple(int(x) for x in cells["shape"])
    out = dict(flat=int(np.ravel_multi_index(idx, shape)),
               evaluable=bool(cells["evaluable"][idx]), s=float(cells["s"][idx]),
               s_nb=float(cells["s_nb"][idx]), n_eval_nb=int(cells["n_eval_nb"][idx]))
    for f, fold in enumerate(folds):
        out[f"count_{fold}"] = int(cells["count"][idx + (f,)])
        out[f"fp_{fold}"] = float(cells["fp"][idx + (f,)])
        out[f"delta_{fold}"] = float(cells["delta"][idx + (f,)])
    return out


def cell_coords(prep: Prepared, flat_index: int) -> dict:
    """把 combo+pred 空间(不含 fold)的扁平索引翻回 {列名: 档位原值} 的可读坐标。

    参数:
        prep: `prepare()` 的输出(用它的 combo_levels/pred_specs/n_combo_axes 做映射)。
        flat_index: `rank_cells()` 返回的扁平索引(np.ravel_multi_index 意义下,对应形状
            prep.shape[:-2],即剥掉了 fold 轴与四态轴)。

    返回:
        {列名: 档位值} 字典,combo 列给档位表里的原始值;pred 列给该维档位表里对应下标的
        档位值(即判定该行落入这一档的阈值 / None,不是原始行的量)。
    """
    idx = np.unravel_index(int(flat_index), prep.shape[:-2])
    out = {}
    for (c, lv), i in zip(prep.combo_levels.items(), idx[: prep.n_combo_axes]):
        out[c] = lv[i]
    for (c, _op, lv), i in zip(prep.pred_specs, idx[prep.n_combo_axes:]):
        out[c] = lv[i]
    return out


# ---------------------------------------------------------------- 打分管线 / bootstrap / 校正
def analyze_tensor(prep: Prepared, ref_index: tuple, min_count: int, axes, weights=None, *,
                   min_segments: int | None = None) -> dict:
    """一次打分管线:格张量 → fp/count → score → 邻域最小 → 排序,打包成一个 dict。

    参数:
        prep: `prepare()` 的输出。
        ref_index: 传给 `score()` 的参照格坐标(不含 fold 轴)。
        min_count: 传给 `score()` 的功效线。
        axes: 传给 `neighbor_min()` 的邻域轴列表。
        weights: 传给 `tensor()` 的按 symbol 整数权重(None = 不加权,原始数据)。
        min_segments: None = 可评估只看 `score()` 的计数门槛(逐行口径的旧判据)。给出时(买点事件口径)
            可评估另要求:每折买点事件数 ≥ min_segments,且不是退化格(`degenerate_mask`:收紧一档一个
            买点事件都没多筛掉,与松一档是同一批样本)。不可评估的格 s 为 NaN、不作任何格的邻居。

    返回:
        dict,键 `fp/count`(`fp_count()` 的两个返回值)、`s/evaluable/delta`(`score()` 的三个
        返回值,evaluable 已并入上面的附加条件)、`s_nb/n_eval_nb`(`neighbor_min()` 的两个返回值)、
        `order`(`rank_cells()` 的排序结果,扁平索引数组,同 combo+pred 扁平空间,不含 fold 轴)。
        给了 min_segments 时另有 `segments`(`segment_tensor` 输出)与 `degenerate`(退化格掩码)。
    """
    fp, count = fp_count(tensor(prep, weights))
    s, ev, delta = score(fp, count, ref_index, min_count)
    extra = {}
    if min_segments is not None:
        seg_T = segment_tensor(prep, weights)
        degen = degenerate_mask(seg_T, prep)
        ev = ev & (seg_T >= min_segments).all(-1) & ~degen
        s = np.where(ev, s, np.nan)
        extra = dict(segments=seg_T, degenerate=degen)
    s_nb, n_eval = neighbor_min(s, ev, axes)
    return dict(fp=fp, count=count, s=s, evaluable=ev, delta=delta, s_nb=s_nb, n_eval_nb=n_eval,
                order=rank_cells(s_nb, n_eval), **extra)


def _neighbors_flat(shape, flat_index: int, axes) -> set:
    """把 `analyze_tensor` 扁平空间(combo+pred,不含 fold)里某格的 r=1 邻域(含自身)展开成扁平索引集合。"""
    idx = list(np.unravel_index(flat_index, shape))
    out = {flat_index}
    for ax in axes:
        for d in (-1, 1):
            j = list(idx); j[ax] += d
            if 0 <= j[ax] < shape[ax]:
                out.add(int(np.ravel_multi_index(j, shape)))
    return out


def bootstrap(prep: Prepared, ref_index: tuple, min_count: int, axes, B: int, seed: int, top_n: int) -> dict:
    """按 symbol 的 multinomial 重采样估计推荐格的选择稳定性与选择后 optimism 偏差。

    参数:
        prep / ref_index / min_count / axes: 同 `analyze_tensor`。
        B: bootstrap 重复次数。
        seed: `np.random.default_rng` 的种子。
        top_n: `top_freq` 统计"入选前 top_n"时的截断名次。

    算法:
        先在原始数据(weights=None)上跑一遍拿到中心格 ĉ(`order[0]`)。每次重采样按
        `rng.multinomial(prep.n_sym, uniform)` 生成整数权重(相当于对 symbol 做有放回重采样),
        重跑整条打分管线拿到该次的中心格 ĉ_b 与 s_nb_b。

    返回:
        dict:
            center: 原始数据的中心格扁平索引(combo+pred 空间)。
            stability: 落在 ĉ 的 r=1 邻域(含自身)内的比例——分母是 `n_valid`(**不是** B),
                即 B 次里"该次重采样自己选中的格 ĉ_b 本身可评估"的次数;某次重采样若选出的
                ĉ_b 不可评估(该次 `continue` 跳过),既不计入分子也不计入分母,避免"重采样
                后大量副本无可评估中心格"时系统性低估 stability。ĉ 本身不可评估、或 B 次
                重采样里没有任何一次可评估(n_valid==0)时都直接返回 stability=nan(复审
                M-6:"无法估计"与"极不稳定"是两码事,不能用 0/0 混进 0.0 这个和"稳定性
                真的很低"读起来一样的数字——`stability:.2f` 会直接打出具有误导性的
                "0.00",而 `n_valid==0` 本身已经足够说明"没有可评估的样本"这件事)。
            n_valid: 上述 stability 分母,B 次里 ĉ_b 可评估的副本数(<= B);连同 stability
                一并报出,方便判断 stability 是基于多少个有效副本算出来的。
            ci: `s_nb_b(ĉ)`(**固定看原始中心格**,不是每次的 ĉ_b)在 B 次里的 2.5/97.5 百分位,
                只用有限值。
            optimism: mean_b[s_nb_b(ĉ_b) − s_nb_original(ĉ_b)]——每次重采样"选中格在本次重采样
                数据上的分数"减去"同一个格在原始数据上的分数",衡量选择过程本身带来的乐观偏差
                (原始数据上的最优格,换一批重采样数据后分数系统性回落多少)。**符号不保证非正**,
                但也**不是 ≈0**:无结构/纯噪声数据上期望值本身就 >=0(见
                `test_bootstrap_null_low_stability_and_optimism_nonneg` 的单边下界断言
                `optimism >= -1e-9`)——这正是选择偏差/winner's curse 本体,不是噪声:实测同一
                null 场景加大 B(40→400→1200)optimism 收敛到一个**稳定为正**的值(≈+0.0054),
                距 0 有 10+ 个 `optimism_se`。**B 增大收敛的是 `optimism_se`(估计的不确定性),
                不是 optimism 的期望值本身**——数据里若有真实结构(如稳定平台),optimism 的
                期望值本身可以稳定地为负,B 增大同样只会让 `optimism_se` 更小、更确信这个
                非零值,不会把它推向 0。调用方应连同 `optimism_se` 一起展示这个数字,用
                |optimism| 相对 `optimism_se` 的量级判断它是否与 0 可区分,不要孤立解读符号或
                大小,也不要指望单纯加大 B 就能把 optimism 拉回 0——它收敛到的是真值本身
                (可能非零,可正可负),不是 0。
            optimism_se: `opt` 样本(参与 optimism 均值计算的那些有限差值,数量 = n_opt)的标准误
                (`std(ddof=1) / sqrt(n_opt)`),量化 optimism 本身的蒙特卡洛不确定性;n_opt<=1 时
                为 nan。
            n_opt: 参与 optimism 均值/标准误计算的有效副本数(<= n_valid,进一步要求该副本选中格
                在原始数据上的 s_nb 也有限)。
            top_freq: {扁平索引: 在 B 次里进入过 order 前 top_n 的次数},只统计有限分数。
    """
    base = analyze_tensor(prep, ref_index, min_count, axes)
    shape = base["s_nb"].shape
    c_hat = int(base["order"][0])
    if not np.isfinite(base["s_nb"].ravel()[c_hat]):
        return dict(center=c_hat, stability=float("nan"), n_valid=0, ci=(float("nan"), float("nan")),
                    optimism=float("nan"), optimism_se=float("nan"), n_opt=0, top_freq={})
    nb_hat = _neighbors_flat(shape, c_hat, axes)
    rng = np.random.default_rng(seed)
    hits, n_valid, s_at_hat, opt, top_freq = 0, 0, [], [], {}
    s0 = base["s_nb"].ravel()
    for _ in range(B):
        w = rng.multinomial(prep.n_sym, np.full(prep.n_sym, 1.0 / prep.n_sym))
        r = analyze_tensor(prep, ref_index, min_count, axes, weights=w)
        sb = r["s_nb"].ravel(); cb = int(r["order"][0])
        if not np.isfinite(sb[cb]):
            continue                                      # 该副本选中格不可评估:不计入分子也不计入分母
        n_valid += 1
        hits += cb in nb_hat
        s_at_hat.append(sb[c_hat])
        if np.isfinite(s0[cb]):
            opt.append(sb[cb] - s0[cb])
        for i in r["order"][:top_n]:
            if np.isfinite(sb[i]):
                top_freq[int(i)] = top_freq.get(int(i), 0) + 1
    s_at_hat = np.array([x for x in s_at_hat if np.isfinite(x)])
    opt_arr = np.array(opt, dtype=float)
    return dict(center=c_hat, stability=(hits / n_valid) if n_valid else float("nan"), n_valid=n_valid,
                ci=(float(np.percentile(s_at_hat, 2.5)), float(np.percentile(s_at_hat, 97.5))) if len(s_at_hat) else (float("nan"),) * 2,
                optimism=float(opt_arr.mean()) if len(opt_arr) else float("nan"),
                optimism_se=float(opt_arr.std(ddof=1) / np.sqrt(len(opt_arr))) if len(opt_arr) > 1 else float("nan"),
                n_opt=len(opt_arr), top_freq=top_freq)


def split_half(prep: Prepared, ref_index: tuple, min_count: int, axes, seed: int, *,
               min_segments: int | None = None) -> float:
    """按 symbol 随机对半分:一半选格(取其 ĉ)、另一半独立评分(取其 s_nb(ĉ)),双向平均。

    参数:
        prep / ref_index / min_count / axes: 同 `analyze_tensor`。
        seed: 划分随机种子(`rng.random(prep.n_sym) < 0.5`)。
        min_segments: 同 `analyze_tensor`。

    算法:
        两个方向各做一次"一半选格、另一半打分"(互换角色),各自要求选格半的 ĉ 本身可评估、
        评分半在该格上的分数有限,才计入平均;两个方向都失败则返回 NaN。

    返回:
        两个方向的 `s_nb(ĉ)` 均值(float);全无有效方向时为 NaN。
    """
    rng = np.random.default_rng(seed)
    half = rng.random(prep.n_sym) < 0.5
    vals = []
    for sel_mask in (half, ~half):
        w_sel = sel_mask.astype(float); w_eval = (~sel_mask).astype(float)
        a = analyze_tensor(prep, ref_index, min_count, axes, weights=w_sel, min_segments=min_segments)
        b = analyze_tensor(prep, ref_index, min_count, axes, weights=w_eval, min_segments=min_segments)
        c = int(a["order"][0])
        v = b["s_nb"].ravel()[c]
        if np.isfinite(a["s_nb"].ravel()[c]) and np.isfinite(v):
            vals.append(v)
    return float(np.mean(vals)) if vals else float("nan")


def split_half_multi(prep: Prepared, ref_index: tuple, min_count: int, axes, seeds, *,
                     min_segments: int | None = None) -> dict:
    """多种子跑 split_half,报均值与标准误。

    为什么必须多种子:单次对半分的结果对种子极敏感——真实长表实测 18 个有效种子
    sd=0.0762、极差 0.274(-0.3083 ~ -0.0346),而同一份报告里 optimism 自身的
    MC SE 只有 0.0062。用单种子的四位小数当"下界"是假精确:换个种子,同一份数据的
    下界能从 -0.03 变成 -0.31。

    参数:
        prep / ref_index / min_count / axes / min_segments: 同 `split_half`。
        seeds: 种子序列(如 range(20))。

    返回:
        {"mean","sd","se","n_valid","n_nan","values"};全部种子失效时
        mean/sd/se 为 nan、n_valid=0。sd 用 ddof=1;n_valid==1 时 sd/se 为 nan。
        "values" 是按 seeds 顺序的原始全序列(含失效种子的 NaN,不是过滤后的 finite),
        供诊断用——想看某个具体种子是否失效,直接对齐 seeds 下标即可。
    """
    vals = [split_half(prep, ref_index, min_count, axes, int(s), min_segments=min_segments) for s in seeds]
    finite = [v for v in vals if np.isfinite(v)]
    n = len(finite)
    if n == 0:
        return {"mean": float("nan"), "sd": float("nan"), "se": float("nan"),
                "n_valid": 0, "n_nan": len(vals), "values": vals}
    mean = float(np.mean(finite))
    sd = float(np.std(finite, ddof=1)) if n > 1 else float("nan")
    se = float(sd / np.sqrt(n)) if n > 1 else float("nan")
    return {"mean": mean, "sd": sd, "se": se, "n_valid": n, "n_nan": len(vals) - n, "values": vals}


def order_rows_by_rank(rows: list, order) -> list:
    """把逐格构造的行字典列表按 `rank_cells()` 的 order 重排,而不是让展示层自行按某个数值列再排一遍。

    背景:
        `rank_cells()` 的 order 不是单纯的 s_nb 数值降序——它有一条硬前置键(0 可评估邻居的
        孤立尖峰排到所有有邻居支撑的格之后,见其文档),这条键推不出用任何单一数值列
        `sort_values` 复现。如果展示层(如 region_find.py 的 cells.csv / 报告前 N 格表格)
        绕开 order、自己按 s_nb 数值重新排序,会出现"报告说推荐格是 ĉ
        (=order[0]),表格首行却是另一个孤立高分格"的不一致,并可能让 ĉ 本身挤出 TOP_N。

    参数:
        rows: 每格一个 dict 的列表,每个 dict 至少含整数键 'flat'(该格在 order 所在扁平
            空间下的下标)。
        order: `rank_cells()` 的输出,扁平索引数组,已按推荐优先级从高到低排好。

    返回:
        按 order 顺序重排后的新列表(不修改入参 rows)。要求 rows 覆盖 order 里的每个索引
        恰好一次,否则 KeyError(缺失)。
    """
    pos = {int(f): i for i, f in enumerate(order)}
    return sorted(rows, key=lambda r: pos[int(r["flat"])])


VERDICT_CANDIDATE = "candidate"                  # naive > 0 且校正后仍正(或校正不可估)
VERDICT_CORRECTED_NEGATIVE = "corrected_negative"  # naive > 0,但按 optimism 校正后翻负
VERDICT_NO_NAIVE = "no_naive"                    # naive <= 0(或非有限):可评估面上本无正邻域分


def verdict(naive: float, optimism: float, split_half: float) -> str:
    """按 SKILL.md 红线("naive 只作参考;optimism 校正当上界,split-half 不是稳定的界、
    按多种子均值 ± SE 报")给出三档判词,供 region_find.py 决定报告标题(复审 I-3)。

    背景:
        原判据 `has_region = bool(np.isfinite(naive) and naive > 0)` 只看 naive,与红线
        直接冲突——2026-08-25 bb_v1 真实运行就撞上:naive s_nb = 0.0705(正),但 optimism
        校正后 corrected = naive − optimism = -0.0557(负)、split-half = -0.1319(负),
        报告仍打出"## 推荐格"标题,首次真实使用即误导("找到了东西"的假象)。

    三档(返回值为下面三个常量之一,不是格式化好的中文——中文措辞由调用方按档位选择,
    避免把展示文案耦合进这个纯判据函数):
        VERDICT_CANDIDATE:          naive > 0 且(optimism 不可估,或按 Efron 口径
                                     corrected = naive − optimism > 0)。
        VERDICT_CORRECTED_NEGATIVE: naive > 0,但 optimism 是有效上界(optimism >= 0)
                                     且 corrected <= 0——按 optimism 校正翻负。
        VERDICT_NO_NAIVE:           naive <= 0(或非有限)——可评估面上邻域分本身就没有
                                     正区域,连"未校正"的门槛都没过。

    split_half 的角色:
        红线要求三口径"并报、不折中"——split-half 是独立于 optimism 的另一条估计
        (不是稳定的界,对种子高度敏感,按多种子均值 ± SE 报),不参与这里的三档分支
        (揉进单一判据会掩盖"两条独立证据其中一条为负"这类
        需要读者自行权衡的情形)。当前签名保留该参数只为把"该不该在报告里对 split-half
        为负单独示警"这个决策点固定在同一处签名下。**本函数不消费 split_half**
        (形参保留只为固定签名、留出后续接入点);当前 region_find.py 也没有按
        `split_half < 0` 产出的条件警示行,它无条件并报三口径。

    optimism 为何只在 `optimism >= 0` 时才用于降级 VERDICT_CANDIDATE:
        与 region_find.py 里 `opt_line` 的既有论证一致——optimism < 0 意味着"本次未观测
        到选择偏差(或被蒙特卡洛噪声掩盖)",此时 corrected 不构成保守上界,只是同一公式
        算出的另一个数字,不能据此把一个 naive 为正的格判定为"翻负"。
    """
    if not (np.isfinite(naive) and naive > 0):
        return VERDICT_NO_NAIVE
    # 注:走到这里 naive > 0 已成立,故 optimism < 0 时 (naive - optimism) > naive > 0,
    # 下面的 `<= 0` 本就不可能成立——`optimism >= 0` 是**冗余的意图声明**(算术上恒等价),
    # 保留它是为了让"只在 optimism >= 0 时才降级"这条语义在代码里显式可读,而不是靠读者
    # 自行推演算术。删掉它不改变任何返回值(复审 N-2 已用变异检验坐实)。
    if np.isfinite(optimism) and optimism >= 0 and (naive - optimism) <= 0:
        return VERDICT_CORRECTED_NEGATIVE
    return VERDICT_CANDIDATE
