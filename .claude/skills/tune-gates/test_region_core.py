# -*- coding: utf-8 -*-
"""region_core 合成数据单测(显式路径跑):uv run pytest .claude/skills/tune-gates/test_region_core.py -q"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from region_core import (cell_coords, fp_count, neighbor_min, pred_level_index, prepare,  # noqa: E402
                         rank_cells, score, tensor, tolerance)

COMBO = {"g": [4, 8, 12], "K": [0, 1, 2]}
PREDS = [("count", ">=", [1, 2, 3]), ("fd", ">=", [0, 20])]
FOLDS = ["2024", "2025"]


def _synth(seed=0, n_sym=400, plateau=None, base_p=0.5, n_per=6):
    """每股每 (g,K) 组合 n_per 行;count/fd 随机;up 概率 = base_p (+ plateau 增量在指定格子集)。"""
    rng = np.random.default_rng(seed)
    rows = []
    for sym in range(n_sym):
        eff = rng.normal(0, 0.03)                     # 按股随机效应
        for g in COMBO["g"]:
            for K in COMBO["K"]:
                for _ in range(n_per):
                    cnt = rng.integers(1, 4); fd = rng.choice([0, 10, 25, 40]); year = rng.choice(FOLDS)
                    p = base_p + eff
                    if plateau and (g, K) in plateau["cells"] and fd >= plateau.get("fd_min", 0):
                        p += plateau["delta"]
                    up = rng.random() < p
                    rows.append(dict(symbol=f"S{sym}", g=g, K=K, count=cnt, fd=fd, fold=year,
                                     fp_up=int(up), fp_down=int(not up), fp_both=0, fp_none=0))
    return pd.DataFrame(rows)


def test_pred_level_index_nested_and_none():
    v = np.array([0.0, 15.0, 25.0, np.nan])
    assert pred_level_index(v, ">=", [0, 20]).tolist() == [0, 0, 1, -1]
    assert pred_level_index(np.array([0.1, 0.3, np.nan]), "<", [None, 0.2]).tolist() == [1, 0, 0]
    with pytest.raises(ValueError):
        pred_level_index(v, ">=", [20, 0])          # 紧→松:非嵌套


def test_pred_level_index_structural_check_catches_what_data_cannot_witness():
    # 全部行都满足两档(25/30/100 >= 20 且 >= 0),数据侧逐行检查测不出"紧→松写反"，
    # 必须靠结构性校验(不看数据、只看 levels 本身单调性)才能抓到。
    v = np.array([25.0, 30.0, 100.0])
    with pytest.raises(ValueError):
        pred_level_index(v, ">=", [20, 0])           # 紧→松,数据全满足两档、无见证
    with pytest.raises(ValueError):
        pred_level_index(v, ">=", [0, 0])            # 重复档(非严格单调)
    with pytest.raises(ValueError):
        pred_level_index(v, ">=", [0, None])         # None 不在下标 0


def test_tensor_suffix_cumsum_counts():
    df = _synth(n_sym=20)
    prep = prepare(df, COMBO, PREDS, "fold", FOLDS)
    T = tensor(prep)
    assert T.shape == (3, 3, 3, 2, 2, 4)
    # 最松档 (count>=1, fd>=0) 的总数 == 全部行数(去掉 fold 不在 FOLDS 的,这里没有)
    assert T[:, :, 0, 0, :, :].sum() == len(df)
    # count>=2 的行数手算
    sub = df[df["count"] >= 2]
    assert T[:, :, 1, 0, :, :].sum() == len(sub)
    # 某一格手算:g=8,K=1,count>=3,fd>=20,2024,up
    m = (df.g == 8) & (df.K == 1) & (df["count"] >= 3) & (df.fd >= 20) & (df.fold == "2024")
    assert T[1, 1, 2, 1, 0, 0] == df.loc[m, "fp_up"].sum()


def test_score_and_evaluable():
    df = _synth(n_sym=200)
    prep = prepare(df, COMBO, PREDS, "fold", FOLDS)
    fp, cnt = fp_count(tensor(prep))
    ref = (1, 1, 0, 0)                                 # g=8,K=1,最松
    s, ev, delta = score(fp, cnt, ref, min_count=100)
    assert ev[ref]
    # 功效线:把 min_count 抬到超过任何格 → 全不可评估
    s2, ev2, _ = score(fp, cnt, ref, min_count=10 ** 6)
    assert not ev2.any() and np.isnan(s2).all()


def test_score_delta_matches_hand_calc_at_non_ref_cell():
    # delta[ref]==0 是恒真(对任何 ref_index 都成立),抓不到"取错参照格/轴"这类错;
    # 这里直接手算非 ref 格的 delta,锁住 fp - fp[ref] 这条真实计算路径。
    fp = np.array([[0.5, 0.6], [0.2, 0.3]])            # 形状 (2 格, 2 fold)
    count = np.full((2, 2), 1000)
    s, ev, delta = score(fp, count, ref_index=(0,), min_count=10)
    assert delta[1, 0] == pytest.approx(0.2 - 0.5)
    assert delta[1, 1] == pytest.approx(0.3 - 0.6)
    assert s[1] == pytest.approx(min(0.2 - 0.5, 0.3 - 0.6))
    assert ev[1] and ev[0]


def test_score_raises_when_ref_not_finite_on_some_fold():
    # ref 格只在 fold1 上 fp=NaN(该 fold 分母为 0);若不校验,delta[...,1] 会对全体格变 NaN,
    # nanmin 会悄悄退化成"只在 fold0 上取 min",而 evaluable 仍判 True——静默削弱评估口径。
    fp = np.array([[[0.3, np.nan], [0.4, 0.5]],
                    [[0.2, 0.6], [0.1, 0.7]]])          # 形状 (2, 2, 2) = (ax0, ax1, fold)
    count = np.full((2, 2, 2), 1000)
    with pytest.raises(ValueError, match=r"fold \[1\]"):
        score(fp, count, ref_index=(0, 0), min_count=10)


def test_score_raises_when_ref_all_folds_nan():
    fp = np.array([[np.nan, np.nan], [0.2, 0.6]])       # 形状 (2 格, 2 fold),ref 全 fold NaN
    count = np.full((2, 2), 1000)
    with pytest.raises(ValueError):
        score(fp, count, ref_index=(0,), min_count=10)


def test_neighbor_min_spike_and_boundary():
    s = np.full((3, 3), -0.02)
    s[1, 1] = 0.05                                      # 中心尖峰
    # 中心的 4 个正交邻居互不相同,真 min 唯一可判别(此前 4 邻居同值 -0.02,任何"取到非自身值"
    # 的实现都会凑巧得出 -0.02,抓不出"到底取没取邻居的真 min"这条真判别)。
    s[0, 1], s[1, 0], s[1, 2], s[2, 1] = -0.03, -0.04, -0.01, -0.02
    ev = np.ones((3, 3), bool)
    s_nb, n = neighbor_min(s, ev, axes=[0, 1])
    assert s_nb[1, 1] == pytest.approx(-0.04) and n[1, 1] == 4     # 邻居真 min(-0.04),非自身 0.05
    assert n[0, 0] == 2 and n[0, 1] == 3                # 角 2 邻、边 3 邻(无 pad)
    ev[0, 1] = False; s[0, 1] = np.nan
    s_nb, n = neighbor_min(s, ev, axes=[0, 1])
    assert np.isnan(s_nb[0, 1]) and n[0, 0] == 1 and n[1, 1] == 3   # 不可评估格不作邻居、自身缺失


def test_rank_and_tolerance():
    s_nb = np.array([[0.01, 0.03, 0.03], [np.nan, 0.02, -0.01]])
    n = np.array([[2, 3, 2], [0, 4, 3]])
    order = rank_cells(s_nb, n)
    assert order[0] == 1                                  # (0,1):0.03 且 n=3 胜 (0,2)
    tol = tolerance(np.array([[-0.1, 0.1, 0.2, 0.1, -0.1]]), center=(0, 2))
    assert tol[1] == (1, 1) and tol[0] == (0, 0)


def test_rank_cells_zero_neighbor_spike_loses_to_plateau_center():
    # 控制方裁定推翻 spec 字面排序:0 可评估邻居的孤立尖峰不该赢过有邻居支撑的格。
    # 1D 网格 7 格:index [1,2,3] 三格互为邻居、s=0.03(真 plateau);index 5 孤立(两侧邻居
    # 均不可评估)、s=0.09 更高但 n_eval_nb=0。旧排序(仅 s_nb 降序)会让 index5 夺冠。
    evaluable = np.array([False, True, True, True, False, True, False])
    s = np.array([np.nan, 0.03, 0.03, 0.03, np.nan, 0.09, np.nan])
    s_nb, n = neighbor_min(s, evaluable, axes=[0])
    assert n[5] == 0 and s_nb[5] == pytest.approx(0.09)    # 孤立尖峰确实还在、但零邻居
    order = rank_cells(s_nb, n)
    assert order[0] == 2                                    # plateau 中心(邻居最多)胜出,不是 index5


def test_rank_cells_boundary_tiebreak_is_reachable():
    # 前两键(s_nb/n_eval_nb)全并列时,第三键(离边界距离)才会决定顺序——
    # 3x3 网格里只有中心 (1,1) 的 boundary_dist=1、其余全 0,必须是它胜出。
    s_nb = np.full((3, 3), 0.05)
    n = np.full((3, 3), 3, dtype=np.int64)
    order = rank_cells(s_nb, n)
    assert order[0] == np.ravel_multi_index((1, 1), (3, 3))


def test_prepare_raises_on_zero_rows_kept():
    # combo 列值全不在档位表里 → 三路 keep 全 False → 0 行保留;此前会静默产出全零张量。
    df = _synth(n_sym=5)
    df["g"] = 999
    with pytest.raises(ValueError):
        prepare(df, COMBO, PREDS, "fold", FOLDS)


def test_tensor_rejects_non_integer_weights_accepts_integer():
    df = _synth(n_sym=10)
    prep = prepare(df, COMBO, PREDS, "fold", FOLDS)
    with pytest.raises(ValueError):
        tensor(prep, weights=np.full(prep.n_sym, 0.5))     # 分数权重:np.rint 逐格取整会漂移
    w_int = np.full(prep.n_sym, 2, dtype=int)
    T_w = tensor(prep, weights=w_int)
    T_plain = tensor(prep)
    assert np.array_equal(T_w, T_plain * 2)                 # 整数权重=精确按倍数缩放,无取整漂移


def test_plateau_recovered_end_to_end():
    plat = {"cells": {(8, 1), (8, 2), (12, 1), (12, 2)}, "delta": 0.08, "fd_min": 20}
    df = _synth(seed=1, n_sym=600, plateau=plat)
    prep = prepare(df, COMBO, PREDS, "fold", FOLDS)
    fp, cnt = fp_count(tensor(prep))
    s, ev, _ = score(fp, cnt, ref_index=(1, 1, 0, 0), min_count=100)
    s_nb, n = neighbor_min(s, ev, axes=list(range(4)))
    best = rank_cells(s_nb, n)[0]
    c = cell_coords(prep, best)
    assert (c["g"], c["K"]) in plat["cells"] and c["fd"] == 20


from region_core import (VERDICT_CANDIDATE, VERDICT_CORRECTED_NEGATIVE, VERDICT_NO_NAIVE,  # noqa: E402
                         analyze_tensor, bootstrap, order_rows_by_rank, split_half,
                         split_half_multi, verdict)


def test_bootstrap_null_low_stability_and_optimism_nonneg():
    df = _synth(seed=2, n_sym=500)                       # 无结构
    prep = prepare(df, COMBO, PREDS, "fold", FOLDS)
    axes = list(range(4))
    bs = bootstrap(prep, ref_index=(1, 1, 0, 0), min_count=100, axes=axes, B=40, seed=0, top_n=5)
    assert 0.0 <= bs["stability"] <= 0.6
    assert bs["optimism"] >= -1e-9
    assert bs["ci"][0] <= bs["ci"][1]
    # 大 N(500 只股票 × 6 行/(g,K))下,任何一次重采样的中心格计数都远超 min_count=100,
    # 经验上 n_valid 恒为 B(=40)——这是有牙的等式断言(修复轮1锁的 `0<=n_valid<=40` 对
    # `n_valid` 每轮至多 +1、共 B 轮这个不变量恒真,不管 evaluable 判定对不对都过,见 M-2);
    # evaluable 判定若回归出漏洞,会在这里表现为 n_valid < 40。partial-invalid 场景见
    # test_bootstrap_partial_valid_replicates。
    assert bs["n_valid"] == 40


def test_bootstrap_plateau_center_stable():
    plat = {"cells": {(8, 1), (8, 2), (12, 1), (12, 2)}, "delta": 0.10, "fd_min": 0}
    df = _synth(seed=3, n_sym=800, plateau=plat)
    prep = prepare(df, COMBO, PREDS, "fold", FOLDS)
    bs = bootstrap(prep, ref_index=(1, 1, 0, 0), min_count=100, axes=list(range(4)), B=40, seed=0, top_n=5)
    assert bs["stability"] >= 0.5
    assert bs["n_valid"] == 40                             # 同上:大 N 场景经验上恒为 B


def test_bootstrap_partial_valid_replicates():
    # M-2:修复轮1加的 `assert 0 <= n_valid <= 40` 是重言式(n_valid 每轮至多 +1、共 B=40
    # 轮,不管 evaluable 判定对不对都恒真),却自称"锁住了"那次修复——比没有断言更危险,会
    # 挡住后来者补真锁。这里构造一个真正会让"部分副本的中心格不可评估"发生的场景:n_sym
    # 压到 10(只有 10 只股票),min_count=30 贴近单格总计数的量级——多项式重采样下,某些
    # 副本会把权重集中到少数股票上,导致另一些股票贡献的格计数跌破 min_count,该副本自己
    # 排出的中心格 order[0] 因此不可评估、被 bootstrap() 的 `continue` 跳过(不计入分子也
    # 不计入分母)。base(全权重)分析本身仍然可评估(否则会走 n_valid=0/stability=nan 的
    # 早退分支,这里断言基线不是那条路径)。数字为固定 seed 下的实测值,非巧合边界:
    # 22/40 留出充分余量,不是精度边界上的偶然。
    df = _synth(seed=0, n_sym=10)
    prep = prepare(df, COMBO, PREDS, "fold", FOLDS)
    bs = bootstrap(prep, ref_index=(1, 1, 0, 0), min_count=30, axes=list(range(4)), B=40, seed=0, top_n=5)
    assert np.isfinite(bs["stability"])                     # 走的是"至少一个有效副本"的正常路径,不是早退
    assert bs["n_valid"] == 22 and bs["n_valid"] < 40        # 真正有牙:部分副本确实被跳过
    # 复审 N-4:上一行只锁住 n_valid 算得对,没锁住它**被当成分母**——而修复轮1改的正是
    # 分母(B → n_valid)。变异检验:把 stability 改回 hits/B 时上一行照样绿。补这条等式后,
    # 分母退回 B=40 会让 stability 从 11/22 变成 11/40,测试立刻红。
    assert bs["stability"] == pytest.approx(11 / 22)        # 分母必须是 n_valid(=22),不是 B(=40)


def test_split_half_more_conservative_than_naive_on_null_data():
    # test_split_half_returns_finite(修复轮1前)只断言 isfinite——把分半机制整个拆掉(选/评用
    # 同一半、甚至不分半直接返回全样本 naive)照样能过。这里换成有牙的断言:无结构数据上,
    # split-half(独立样本外推、更悲观)必须比同一份数据上不分半算出的 naive s_nb 更保守
    # (数值更小)。实测 naive=-0.0100,split_half=-0.0350,余量充足(0.025),不是精度边界上的巧合。
    df = _synth(seed=4, n_sym=600)
    prep = prepare(df, COMBO, PREDS, "fold", FOLDS)
    ref, axes = (1, 1, 0, 0), list(range(4))
    full = analyze_tensor(prep, ref, 50, axes)
    naive = float(full["s_nb"].ravel()[int(full["order"][0])])
    v = split_half(prep, ref_index=ref, min_count=50, axes=axes, seed=0)
    assert np.isfinite(v)
    assert v < naive - 0.01                                 # 明显更保守,留出远大于浮点噪声的余量


def test_order_rows_by_rank_follows_order_not_raw_score_column():
    # 修复轮1 Important 5:region_find.py 曾自行按 s_nb 数值 sort_values,绕开 rank_cells 的
    # 硬前置键(0 可评估邻居的孤立尖峰应排到有邻居支撑的格之后),导致报告表格首行 != ĉ。
    # 这里锁住 order_rows_by_rank 忠实跟随 order、而不是重新按某个数值列排序。
    rows = [dict(flat=0, s_nb=0.90), dict(flat=1, s_nb=0.10), dict(flat=2, s_nb=0.05)]
    order = np.array([1, 2, 0])          # rank_cells 认定:1(有邻居支撑)第一,0(孤立尖峰)最后
    ordered = order_rows_by_rank(rows, order)
    assert [r["flat"] for r in ordered] == [1, 2, 0]
    assert ordered[0]["flat"] != max(rows, key=lambda r: r["s_nb"])["flat"]   # 首行不是纯 s_nb 最高


def test_prepare_raises_on_nan_symbol_in_kept_rows():
    # 修复轮1 Minor 15:symbol 列 NaN 时 pd.Categorical(...).codes 给 -1,该行不会被 combo/pred/fold
    # 的 keep 掩码丢弃,随后 tensor(weights=...) 会用 weights[-1] 静默算成"最后一只股票"的权重。
    df = _synth(n_sym=10)
    df.loc[0, "symbol"] = None
    with pytest.raises(ValueError):
        prepare(df, COMBO, PREDS, "fold", FOLDS)


# ---------------------------------------------------------------- verdict(复审 I-3 / M-3)
# M-3:region_find.py 零测试覆盖是 I-3 漏出去的洞——has_region 的判据与 SKILL.md 红线冲突,
# 四轮 review 加一次真实全宇宙运行都没抓到,因为没有一行测试跑过它。判据抽成这里的纯函数后
# 补三档测试,把"下一次改判据"重新纳入回归网。2026-08-25 bb_v1 真实运行的三个数字
# (naive=0.0705, optimism=0.1263, split_half=-0.1319)在 test_verdict_matches_real_bb_v1_run
# 里逐字复用,直接锁住那次真实误报被修复后的判词。

def test_verdict_candidate_when_naive_and_corrected_positive():
    assert verdict(naive=0.05, optimism=0.01, split_half=0.02) == VERDICT_CANDIDATE


def test_verdict_candidate_when_optimism_not_estimable():
    # optimism 不可估(bootstrap 副本里选中格全不可评估,B 太小或功效线太高)时,不能据此把
    # 一个 naive 为正的格判定为"翻负"——没有校正数据不等于校正后为负。
    assert verdict(naive=0.05, optimism=float("nan"), split_half=float("nan")) == VERDICT_CANDIDATE


def test_verdict_candidate_when_optimism_negative_does_not_downgrade():
    # optimism < 0 意味着"本次未观测到选择偏差(或被蒙特卡洛噪声掩盖)",corrected 在这种
    # 符号下不构成保守上界,不能据此把 naive 为正的格判定为"翻负"(与 region_find.py 的
    # opt_line 既有论证一致)。
    assert verdict(naive=0.05, optimism=-0.02, split_half=-0.01) == VERDICT_CANDIDATE


def test_verdict_corrected_negative_when_optimism_flips_naive_positive():
    # naive 为正,但 optimism 是有效上界(>=0)且 corrected = naive-optimism <= 0——按 Efron
    # 口径校正翻负,不构成"发现稳健区"。
    assert verdict(naive=0.05, optimism=0.08, split_half=-0.01) == VERDICT_CORRECTED_NEGATIVE


def test_verdict_corrected_negative_boundary_at_zero():
    assert verdict(naive=0.05, optimism=0.05, split_half=0.0) == VERDICT_CORRECTED_NEGATIVE  # corrected==0 算翻负,不算候选


def test_verdict_no_naive_when_naive_non_positive_or_nonfinite():
    assert verdict(naive=0.0, optimism=float("nan"), split_half=float("nan")) == VERDICT_NO_NAIVE
    assert verdict(naive=-0.03, optimism=0.01, split_half=-0.02) == VERDICT_NO_NAIVE
    assert verdict(naive=float("nan"), optimism=0.01, split_half=0.0) == VERDICT_NO_NAIVE


def test_verdict_matches_real_bb_v1_run():
    # 2026-08-25 bb_v1 全宇宙真实运行(docs/research/2026-08-25_multivar-bb_v1/region_report.md)
    # 撞上的真实误报场景:naive 为正、optimism 是有效上界、corrected 翻负、split-half 也为负——
    # 旧判据 has_region=bool(naive>0) 会打出"## 推荐格",新判据必须给出 CORRECTED_NEGATIVE。
    assert verdict(naive=0.0705, optimism=0.1263, split_half=-0.1319) == VERDICT_CORRECTED_NEGATIVE


def test_split_half_multi_aggregates_seeds():
    """多种子聚合:n_valid 计数正确、mean 等于有效值的均值、se = sd/sqrt(n)。"""
    from region_core import split_half, split_half_multi
    df = _synth(seed=3, n_sym=400)
    prep = prepare(df, COMBO, PREDS, "fold", FOLDS)
    ref, axes, mc = (1, 1, 0, 0), list(range(4)), 50
    seeds = list(range(6))
    r = split_half_multi(prep, ref, mc, axes, seeds)
    singles = [split_half(prep, ref, mc, axes, s) for s in seeds]
    finite = [v for v in singles if np.isfinite(v)]
    assert r["values"] == singles                      # "values" 是原始全序列(含 NaN),非过滤后的 finite
    assert r["n_valid"] == len(finite)
    assert r["n_nan"] == len(seeds) - len(finite)
    assert r["n_valid"] >= 2                            # 钉住本场景确有 >=2 个有效种子,下面的差分断言不是平凡跳过
    if finite:
        assert r["mean"] == pytest.approx(float(np.mean(finite)), abs=1e-12)
        if len(finite) > 1:
            assert r["se"] == pytest.approx(float(np.std(finite, ddof=1) / np.sqrt(len(finite))), abs=1e-12)


def test_split_half_multi_all_nan_is_safe():
    """全 NaN 时不炸,n_valid=0 且 mean 为 nan。"""
    from region_core import split_half_multi
    df = _synth(seed=4, n_sym=60)
    prep = prepare(df, COMBO, PREDS, "fold", FOLDS)
    r = split_half_multi(prep, (1, 1, 0, 0), 10_000_000, list(range(4)), [0, 1, 2])  # 功效线高到全不可评估
    assert r["n_valid"] == 0
    assert np.isnan(r["mean"])
