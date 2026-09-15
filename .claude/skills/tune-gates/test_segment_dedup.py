# -*- coding: utf-8 -*-
"""买点事件口径(同一检测组合内同一买点事件只计一次)的格张量聚合测试。

合成性质测试常规跑:uv run pytest .claude/skills/tune-gates/test_segment_dedup.py -q
golden 读现存 bb_v1 main 长表,要显式打开:TUNE_GOLDEN=1 uv run pytest .claude/skills/tune-gates/test_segment_dedup.py -q
"""
import itertools
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

HERE = Path(__file__).parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE))
import region_core as RC  # noqa: E402
from region_core import (STATES, analyze_tensor, bootstrap, cell_index, degenerate_mask,  # noqa: E402
                         prepare, prepare_shards, segment_tensor, split_half, stock_sums, tensor)

COMBO = {"g": [4, 8], "K": [0, 1, 2]}
PREDS = [("a", ">=", [0, 1, 2, 3, 4]), ("b", ">=", [0, 10, 20, 30, 40]), ("c", "<", [None, 0.8, 0.6, 0.4, 0.2])]
FOLDS = ["2024", "2025"]
SEG = ["x.start", "x.end"]
_C_OF_LEVEL = [0.9, 0.7, 0.5, 0.3, 0.1]          # c 取这些值时恰好落在 "<" 档位的第 j 档
_LAYER = [v for v in itertools.product(range(5), repeat=3) if sum(v) == 6]   # 19 个两两不可比的档号向量


def _synth(seed, n_groups=500, n_sym=12):
    """随机买点事件组:每组 k∈1..14 行,档号向量或随机(含重复、被支配)或取自同一「层」(两两不可比,
    约简后仍有 k 行,k>10 时走谓词格差分)。组内四态相同、取 0..299(越过 int8 值域)。
    另混入会被档位过滤丢掉的行:谓词 NaN、检测参数不在档位表、fold 不在 folds 里。"""
    rng = np.random.default_rng(seed)
    rows, used = [], set()
    for _ in range(n_groups):
        sym = f"S{int(rng.integers(n_sym)):02d}"
        g, K = int(rng.choice(COMBO["g"])), int(rng.choice(COMBO["K"]))
        fold = str(rng.choice(FOLDS + ["2023"]))
        while True:                                # 同一 (symbol, 组合, fold) 内买点事件键唯一;跨组合可撞键
            s = int(rng.integers(0, 25)); e = s + int(rng.integers(1, 4))
            if (sym, g, K, fold, s, e) not in used:
                used.add((sym, g, K, fold, s, e)); break
        k = int(rng.integers(1, 15))
        if rng.random() < 0.35:
            vs = [_LAYER[i] for i in rng.choice(len(_LAYER), size=k, replace=False)]
        else:
            vs = [tuple(int(x) for x in rng.integers(0, 5, size=3)) for _ in range(k)]
            if k > 1 and rng.random() < 0.3:
                vs[-1] = vs[0]
        st = rng.integers(0, 300, size=4)
        for v in vs:
            rows.append({"symbol": sym, "g": g, "K": K, "fold": fold, "a": float(v[0]),
                         "b": float(10 * v[1] + rng.integers(0, 10)), "c": _C_OF_LEVEL[v[2]],
                         "x.start": s, "x.end": e, **dict(zip(STATES, (int(x) for x in st)))})
    df = pd.DataFrame(rows)
    noise = rng.choice(len(df), size=len(df) // 10, replace=False)
    df.loc[noise[0::3], "b"] = np.nan              # 谓词 NaN:任何格都不过
    df.loc[noise[1::3], "g"] = 99                  # 检测参数不在档位表
    df.loc[noise[2::3], "c"] = np.nan              # c 的最松档不过滤:NaN 只过最松档
    return df


def _pass_masks(df):
    """逐谓词逐档的「行过闸」掩码,直接按阈值比较(不经 pred_level_index)。"""
    out = []
    for col, op, lv in PREDS:
        x = df[col].to_numpy(float)
        with np.errstate(invalid="ignore"):
            out.append([np.ones(len(df), bool) if t is None else (x >= t) if op == ">=" else (x < t) for t in lv])
    return out


def _brute(df, w_by_sym):
    """直白版:逐格「行过滤 → 按 (symbol, fold, 买点事件键) 去重 → 按股权重求和」。返回 (四态张量, 买点事件数张量)。"""
    pred_shape = tuple(len(lv) for _, _, lv in PREDS)
    shape = tuple(len(lv) for lv in COMBO.values()) + pred_shape + (len(FOLDS),)
    T = np.zeros(shape + (4,), np.int64); S = np.zeros(shape, np.int64)
    gid = pd.factorize(pd.MultiIndex.from_frame(df[["symbol", "fold"] + SEG]))[0]
    w = df["symbol"].map(w_by_sym).fillna(0).to_numpy(np.int64)
    st = df[STATES].to_numpy(np.int64)
    passes = _pass_masks(df)
    for (gi, g), (ki, K), (fi, fold) in itertools.product(enumerate(COMBO["g"]), enumerate(COMBO["K"]), enumerate(FOLDS)):
        base = (df["g"].to_numpy() == g) & (df["K"].to_numpy() == K) & (df["fold"].to_numpy() == fold)
        for p in itertools.product(*(range(n) for n in pred_shape)):
            m = base.copy()
            for j, lvl in enumerate(p):
                m &= passes[j][lvl]
            rows = np.flatnonzero(m)
            _, first = np.unique(gid[rows], return_index=True)
            r = rows[first]
            T[(gi, ki) + p + (fi,)] = (st[r] * w[r, None]).sum(0)
            S[(gi, ki) + p + (fi,)] = w[r].sum()
    return T, S


def _pareto_sizes(df):
    """每个买点事件约简后互不可比的行数(只用来确认合成数据真的覆盖到 k>10)。"""
    lv = np.stack([RC.pred_level_index(df[c].values, op, levels) for c, op, levels in PREDS], 1)
    ok = (lv >= 0).all(1) & df["g"].isin(COMBO["g"]).to_numpy() & df["fold"].isin(FOLDS).to_numpy()
    sizes = []
    for _, idx in df[ok].groupby(["symbol", "g", "K", "fold"] + SEG).indices.items():
        v = np.unique(lv[ok][idx], axis=0)
        dominated = [(np.all(v >= v[i], 1) & np.any(v > v[i], 1)).any() for i in range(len(v))]
        sizes.append(int(len(v) - sum(dominated)))
    return np.array(sizes)


@pytest.mark.parametrize("max_k", [RC.SEG_SUBSET_MAX_K, 0, 14])
@pytest.mark.parametrize("seed", [0, 1])
def test_segment_mode_matches_brute_force(monkeypatch, seed, max_k):
    """全格逐位相等:四态、买点事件数,不加权与随机整数按股权重各一遍。

    max_k 参数化让同一份数据分别走「默认分流」「全部谓词格差分」「全部子集包含-排斥」三条路。"""
    monkeypatch.setattr(RC, "SEG_SUBSET_MAX_K", max_k)
    df = _synth(seed)
    if max_k == RC.SEG_SUBSET_MAX_K == 10:
        assert _pareto_sizes(df).max() > 10          # 默认分流下两条路都真的走到了
    prep = prepare(df, COMBO, PREDS, "fold", FOLDS, segment_cols=SEG)
    assert set(np.unique(prep.seg)) <= {-1, 1} and prep.states.dtype == np.int16
    assert len(prep.flat) == len(prep.states) == len(prep.sym_codes) == len(prep.seg)
    kept = df[prep.row_keep]
    assert prep.n_rows_raw == len(kept)
    assert prep.n_segments == len(kept.drop_duplicates(["symbol", "g", "K", "fold"] + SEG))

    rng = np.random.default_rng(seed + 100)
    for w in (np.ones(prep.n_sym, np.int64), rng.integers(0, 4, size=prep.n_sym)):
        T_b, S_b = _brute(df, dict(zip(prep.symbols, w)))
        assert np.array_equal(tensor(prep, weights=w), T_b)
        assert np.array_equal(segment_tensor(prep, weights=w), S_b)


def test_row_mode_is_unchanged_and_counts_rows():
    """逐行口径:每行一个条目、买点事件计数全 1;segment_tensor = 过格的行数。"""
    df = _synth(3)
    prep = prepare(df, COMBO, PREDS, "fold", FOLDS)
    assert (prep.seg == 1).all() and len(prep.flat) == prep.n_rows_raw == prep.n_segments == int(prep.row_keep.sum())
    S = segment_tensor(prep)
    passes = _pass_masks(df)
    m = (df["g"].to_numpy() == 8) & (df["K"].to_numpy() == 2) & (df["fold"].to_numpy() == "2025")
    m &= passes[0][2] & passes[1][1] & passes[2][3]
    assert S[1, 2, 2, 1, 3, 1] == m.sum()
    assert tensor(prep)[1, 2, 2, 1, 3, 1].tolist() == df.loc[m, STATES].sum().tolist()


def test_stock_sums_matches_brute_and_tensor():
    df = _synth(4)
    prep = prepare(df, COMBO, PREDS, "fold", FOLDS, segment_cols=SEG)
    rng = np.random.default_rng(7)
    cells = [tuple(int(rng.integers(n)) for n in prep.shape[:-2]) for _ in range(12)] + [(1, 1, 0, 0, 0)]
    U, D, N = stock_sums(prep, cells)
    assert U.shape == (prep.n_sym, len(cells), len(FOLDS)) and U.dtype == np.int64
    T = tensor(prep)
    for j, c in enumerate(cells):
        assert np.array_equal(U[:, j].sum(0), T[c][:, 0])
        assert np.array_equal(D[:, j].sum(0), T[c][:, :3].sum(-1))
        assert np.array_equal(N[:, j].sum(0), T[c].sum(-1))
    Up, Dp, Np_ = stock_sums(prep, cells, fold_mode="pooled")
    assert Up.shape == (prep.n_sym, len(cells), 1)
    assert np.array_equal(Up[..., 0], U.sum(-1)) and np.array_equal(Dp[..., 0], D.sum(-1))
    assert np.array_equal(Np_[..., 0], N.sum(-1))
    # 逐股直白版:行过滤 → 去重 → 按 symbol 分组求和
    passes = _pass_masks(df)
    sym_code = {s: i for i, s in enumerate(prep.symbols)}
    for j, c in enumerate(cells):
        m = (df["g"].to_numpy() == COMBO["g"][c[0]]) & (df["K"].to_numpy() == COMBO["K"][c[1]])
        for p, lvl in enumerate(c[2:]):
            m &= passes[p][lvl]
        for f, fold in enumerate(FOLDS):
            sub = df[m & (df["fold"].to_numpy() == fold)].drop_duplicates(["symbol", "fold"] + SEG)
            exp = np.zeros(prep.n_sym, np.int64)
            for s, up in sub.groupby("symbol")["fp_up"].sum().items():
                exp[sym_code[s]] = up
            assert np.array_equal(U[:, j, f], exp)
    with pytest.raises(ValueError, match="fold_mode"):
        stock_sums(prep, cells, fold_mode="both")


def test_degenerate_mask_definition():
    df = _synth(5, n_groups=150)
    prep = prepare(df, COMBO, PREDS, "fold", FOLDS, segment_cols=SEG)
    seg_T = segment_tensor(prep)
    mask = degenerate_mask(seg_T, prep)
    assert mask.shape == prep.shape[:-2] and mask.dtype == bool
    exp = np.zeros(mask.shape, bool)
    for idx in itertools.product(*(range(n) for n in mask.shape)):
        for ax in range(prep.n_combo_axes, prep.n_combo_axes + prep.n_pred_axes):
            if idx[ax] > 0:
                lo = list(idx); lo[ax] -= 1
                exp[idx] |= bool(np.array_equal(seg_T[idx], seg_T[tuple(lo)]))
    assert np.array_equal(mask, exp)
    assert mask.any() and not mask.all()
    assert not mask[(slice(None),) * prep.n_combo_axes + (0,) * prep.n_pred_axes].any()   # 全部 pred 轴最松档不可能退化
    with pytest.raises(ValueError, match="形状"):
        degenerate_mask(seg_T[..., :1], prep)


def test_prepare_shards_segment_equals_whole_table(tmp_path):
    df = _synth(6)
    syms = sorted(df["symbol"].unique())
    shards = []
    for i, part in enumerate((syms[:5], syms[5:6], syms[6:])):
        q = tmp_path / f"part-{i:04d}.parquet"
        df[df["symbol"].isin(part)].to_parquet(q, index=False)
        shards.append(q)
    whole = prepare(df, COMBO, PREDS, "fold", FOLDS, segment_cols=SEG)
    sh = prepare_shards(shards, COMBO, PREDS, "fold", FOLDS, segment_cols=SEG)
    assert list(whole.symbols) == list(sh.symbols) and whole.n_sym == sh.n_sym
    assert (whole.n_rows_raw, whole.n_segments) == (sh.n_rows_raw, sh.n_segments)
    w = np.random.default_rng(0).integers(0, 3, size=whole.n_sym)
    assert np.array_equal(tensor(whole, weights=w), tensor(sh, weights=w))
    assert np.array_equal(segment_tensor(whole, weights=w), segment_tensor(sh, weights=w))
    assert sh.states.dtype == np.int16 and sh.seg.dtype == np.int8 and sh.flat.dtype == np.int32


def test_prepare_shards_rejects_shared_symbols(tmp_path):
    df = _synth(7, n_groups=60)
    a, b = tmp_path / "part-0000.parquet", tmp_path / "part-0001.parquet"
    df.iloc[: len(df) // 2].to_parquet(a, index=False)
    df.iloc[len(df) // 4:].to_parquet(b, index=False)
    with pytest.raises(ValueError, match="symbol"):
        prepare_shards([a, b], COMBO, PREDS, "fold", FOLDS, segment_cols=SEG)



def test_prepare_frames_equals_prepare_shards(tmp_path):
    """逐片 DataFrame 路径(边读边接、不落成分片)与分片路径逐位相同;片之间共用 symbol 报错。"""
    df = _synth(9)
    syms = sorted(df["symbol"].unique())
    shards = []
    for i, part in enumerate((syms[:4], syms[4:5], syms[5:])):
        q = tmp_path / f"part-{i:04d}.parquet"
        df[df["symbol"].isin(part)].to_parquet(q, index=False)
        shards.append(q)
    sh = prepare_shards(shards, COMBO, PREDS, "fold", FOLDS, segment_cols=SEG)
    fr = RC.prepare_frames((pd.read_parquet(q) for q in shards), COMBO, PREDS, "fold", FOLDS, segment_cols=SEG)
    assert list(fr.symbols) == list(sh.symbols) and fr.n_sym == sh.n_sym
    assert (fr.n_rows_raw, fr.n_segments) == (sh.n_rows_raw, sh.n_segments)
    w = np.random.default_rng(1).integers(0, 3, size=sh.n_sym)
    assert np.array_equal(tensor(fr, weights=w), tensor(sh, weights=w))
    assert np.array_equal(segment_tensor(fr, weights=w), segment_tensor(sh, weights=w))
    cells = [(0, 1, 2, 0, 3), (1, 0, 0, 4, 1)]
    assert all(np.array_equal(a, b) for a, b in zip(stock_sums(fr, cells), stock_sums(sh, cells)))
    with pytest.raises(ValueError, match="symbol"):
        RC.prepare_frames([df.iloc[: len(df) // 2], df.iloc[len(df) // 4:]], COMBO, PREDS, "fold", FOLDS,
                          segment_cols=SEG)

def test_inconsistent_states_within_segment_raises():
    df = _synth(8, n_groups=80)
    kept = df[df["g"].isin(COMBO["g"]) & df["fold"].isin(FOLDS) & df["b"].notna()]
    key = ["symbol", "g", "K", "fold"] + SEG
    multi = kept[kept.duplicated(key, keep=False)].index
    df.loc[multi[0], "fp_down"] += 1
    with pytest.raises(ValueError, match="四态不一致"):
        prepare(df, COMBO, PREDS, "fold", FOLDS, segment_cols=SEG)


def test_segment_key_columns_validated():
    df = _synth(9, n_groups=40)
    with pytest.raises(ValueError, match="不在长表"):
        prepare(df, COMBO, PREDS, "fold", FOLDS, segment_cols=["seg_id"])
    df2 = df.assign(**{"x.start": df["x.start"].astype(float)})
    with pytest.raises(ValueError, match="整数列"):
        prepare(df2, COMBO, PREDS, "fold", FOLDS, segment_cols=SEG)


def test_grid_path_rejects_oversized_predicate_grid():
    """约简后 k>10 要在谓词格上差分;谓词格 6^7 格超上限时报错,而不是悄悄吃掉几 GB。"""
    preds = [(f"p{i}", ">=", [0, 1, 2, 3, 4, 5]) for i in range(7)]
    vecs = [v for v in itertools.combinations(range(7), 2)][:11]      # 两个分量取 5、其余 0:两两不可比
    rows = [{"symbol": "S", "g": 4, "K": 0, "fold": "2024", "x.start": 1, "x.end": 2,
             **{f"p{i}": (5 if i in v else 0) for i in range(7)}, **dict.fromkeys(STATES, 1)} for v in vecs]
    with pytest.raises(ValueError, match="谓词格"):
        prepare(pd.DataFrame(rows), COMBO, preds, "fold", FOLDS, segment_cols=SEG)


def test_state_overflow_rejected():
    df = _synth(10, n_groups=20)
    df.loc[df.index[0], "fp_none"] = 2 ** 15
    with pytest.raises(ValueError, match="int16"):
        prepare(df, COMBO, PREDS, "fold", FOLDS)


def test_bootstrap_and_split_half_on_segment_prep():
    """负质量条目经 bincount + 后缀累加后,任何按股整数权重下的计数都不为负;下游管线照常跑。"""
    df = _synth(11, n_groups=800, n_sym=40)
    prep = prepare(df, COMBO, PREDS, "fold", FOLDS, segment_cols=SEG)
    rng = np.random.default_rng(1)
    for _ in range(5):
        w = rng.multinomial(prep.n_sym, np.full(prep.n_sym, 1 / prep.n_sym))
        assert tensor(prep, weights=w).min() >= 0 and segment_tensor(prep, weights=w).min() >= 0
    ref, axes = (0, 0, 0, 0, 0), list(range(5))
    R = analyze_tensor(prep, ref, 1, axes)
    assert np.isfinite(R["s_nb"]).any()
    bs = bootstrap(prep, ref, 1, axes, B=5, seed=0, top_n=3)
    assert 0 <= bs["n_valid"] <= 5
    assert isinstance(split_half(prep, ref, 1, axes, seed=0), float)


# ---------------------------------------------------------------- golden:现存 bb_v1 main 长表
LT = REPO / "outputs/tune_gates/bb_v1/main/longtable"
CELLS_NPZ = REPO / "outputs/tune_gates/bb_v1/main/cells.npz"
golden = pytest.mark.skipif(os.environ.get("TUNE_GOLDEN") != "1" or not LT.exists(),
                            reason="golden:需 TUNE_GOLDEN=1 且存在 outputs/tune_gates/bb_v1/main/longtable")

G_COMBO = {"bo.exceed_threshold": [0.0015, 0.003, 0.0045, 0.0075], "bo.min_relative_height": [0.1, 0.2, 0.3, 0.5],
           "burst.gap_max": [4, 8, 12, 20], "tb.max_rise_k": [0.75, 1.5, 2.25, 3.75],
           "tb.max_span": [10, 20, 30, 50], "tb.stop_confirm_bars": [1, 2, 3, 4]}
G_PREDS = [("burst.count", ">=", [1, 2, 3, 4]), ("burst.distinct_pk", ">=", [1, 3, 5]),
           ("burst.first_drought", ">=", [0, 40, 80]), ("burst.peak_age_max", ">=", [0, 60, 120]),
           ("burst.max_bar_vol_ratio", ">=", [0, 3, 6]), ("tb.max_day_drop", "<", [None, 0.2])]
G_FOLDS = ["2024", "2025"]
G_SEG = ["tb.start", "tb.end"]               # bb_v1 的回踩键
G_REF = {"bo.exceed_threshold": 0.003, "bo.min_relative_height": 0.2, "burst.gap_max": 8, "tb.max_rise_k": 1.5,
         "tb.max_span": 20, "tb.stop_confirm_bars": 1, "burst.count": 1, "burst.distinct_pk": 1,
         "burst.first_drought": 0, "burst.peak_age_max": 0, "burst.max_bar_vol_ratio": 0, "tb.max_day_drop": None}
G_PROD = {**G_REF, "burst.distinct_pk": 3, "burst.first_drought": 40, "burst.peak_age_max": 60,
          "burst.max_bar_vol_ratio": 3, "tb.max_day_drop": 0.2}
G_NINE = {"ref": G_REF, "refC": {**G_REF, "bo.exceed_threshold": 0.0075},
          "prod": G_PROD, "prodC": {**G_PROD, "bo.exceed_threshold": 0.0075},
          "del_peak": {**G_PROD, "burst.peak_age_max": 0}, "del_vol": {**G_PROD, "burst.max_bar_vol_ratio": 0},
          "del_fd": {**G_PROD, "burst.first_drought": 0}, "del_pk": {**G_PROD, "burst.distinct_pk": 1},
          "del_mdd": {**G_PROD, "tb.max_day_drop": None}}


def _golden_cells():
    """附录定义的 9 个格 + 固定种子随机抽的 11 个格(combo+pred 坐标)。"""
    nine = [cell_index(G_COMBO, G_PREDS, lv) for lv in G_NINE.values()]
    shape = [len(lv) for lv in G_COMBO.values()] + [len(lv) for _, _, lv in G_PREDS]
    rng = np.random.default_rng(20260913)
    return nine + [tuple(int(rng.integers(n)) for n in shape) for _ in range(11)]


def _straight_counts(shards, cells):
    """直白版:逐片读需要的列,逐格「行过滤 → 按 (symbol, fold_Y, tb.start, tb.end) 去重」。

    返回形状 (格数, 折数, 5) 的 int64:up、定向(up+down+both)、四态总计、回踩数、行数。"""
    cols = list(G_COMBO) + [c for c, _, _ in G_PREDS] + ["symbol", "fold_Y"] + G_SEG + STATES
    out = np.zeros((len(cells), len(G_FOLDS), 5), np.int64)
    for sp in shards:
        df = pd.read_parquet(sp, columns=cols)
        df[STATES] = df[STATES].astype(np.int64)
        fold = df["fold_Y"].astype(str).to_numpy()
        for j, c in enumerate(cells):
            m = np.ones(len(df), bool)
            for (col, lv), i in zip(G_COMBO.items(), c[:len(G_COMBO)]):
                m &= df[col].to_numpy() == lv[i]
            for (col, op, lv), i in zip(G_PREDS, c[len(G_COMBO):]):
                if lv[i] is not None:
                    x = df[col].to_numpy(float)
                    with np.errstate(invalid="ignore"):
                        m &= (x >= lv[i]) if op == ">=" else (x < lv[i])
            for f, fy in enumerate(G_FOLDS):
                sub = df[m & (fold == fy)]
                dd = sub.drop_duplicates(["symbol", "fold_Y"] + G_SEG)
                s = dd[STATES].sum()
                out[j, f] += [s["fp_up"], s["fp_up"] + s["fp_down"] + s["fp_both"], s.sum(), len(dd), len(sub)]
    return out


@pytest.fixture(scope="module")
def golden_run():
    shards = sorted(LT.glob("part-*.parquet"))
    cells = _golden_cells()
    prep = prepare_shards(shards, G_COMBO, G_PREDS, "fold_Y", G_FOLDS, segment_cols=G_SEG)
    T, S = tensor(prep), segment_tensor(prep)
    seg = dict(T=np.stack([T[c] for c in cells]), S=np.stack([S[c] for c in cells]),
               sums=stock_sums(prep, cells), n_rows_raw=prep.n_rows_raw, n_segments=prep.n_segments)
    del prep, T, S
    prep = prepare_shards(shards, G_COMBO, G_PREDS, "fold_Y", G_FOLDS)
    T, S = tensor(prep), segment_tensor(prep)
    row = dict(count=np.stack([T[c].sum(-1) for c in cells[:9]]), rows=np.stack([S[c] for c in cells[:9]]),
               n_rows_raw=prep.n_rows_raw)
    del prep, T, S
    return dict(cells=cells, seg=seg, row=row, straight=_straight_counts(shards, cells))


@golden
def test_golden_segment_counts_match_straight_dedup(golden_run):
    st, seg = golden_run["straight"], golden_run["seg"]
    assert np.array_equal(seg["T"][..., 0], st[..., 0])
    assert np.array_equal(seg["T"][..., :3].sum(-1), st[..., 1])
    assert np.array_equal(seg["T"].sum(-1), st[..., 2])
    assert np.array_equal(seg["S"], st[..., 3])
    U, D, N = seg["sums"]
    assert np.array_equal(U.sum(0), st[..., 0]) and np.array_equal(D.sum(0), st[..., 1])
    assert np.array_equal(N.sum(0), st[..., 2])
    assert seg["n_rows_raw"] == golden_run["row"]["n_rows_raw"]
    assert st[:9, :, 3].min() > 0                    # 九个格每折都有回踩,比较不是空对空


@golden
def test_golden_row_mode_counts_match_cells_npz(golden_run):
    with np.load(CELLS_NPZ) as z:
        count = z["count"]
    row = golden_run["row"]
    for j, c in enumerate(golden_run["cells"][:9]):
        assert np.array_equal(row["count"][j], count[c])
    assert np.array_equal(row["rows"], golden_run["straight"][:9, :, 4])


@golden
def test_golden_rows_per_segment_ratio(golden_run):
    st = golden_run["straight"][:9].sum(1)           # 两折合并
    names = list(G_NINE)
    ratio = {n: round(float(st[i, 4] / st[i, 3]), 2) for i, n in enumerate(names)}
    assert (ratio["ref"], ratio["prod"], ratio["prodC"]) == (1.42, 1.28, 1.24)
