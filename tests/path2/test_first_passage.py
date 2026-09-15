"""path2/eval.py:首次穿越方向(first-passage)计算函数的测试。

覆盖:
  - 常量 / 辅助:DEFAULT_FP_K、_ticker_seed(md5 跨进程稳定)
  - _first_passage_at:几何对称单 k + 波动率尺度 M,四态(up/down/both/none)+ 越界
  - match_first_passage:per-match 入口,单组四态计数(内算 M)
  - random_day_first_passage:随机日基线(Task 3 重写后的测试由 Task 3 落地)
  - spans_first_passage:区间入口;match_first_passage 改由它实现后与逐 event 逐买点日
    直白版逐位对拍(合成数据、覆写 sample_bar_indices 的容器、positive_case fixture)
  - daily_first_passage:逐日一行的向量化实现与逐日调 _first_passage_at 的直白版逐位对拍
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from path2.core import Event
from path2.dag.result import PatternMatch, PredicateTrace
from path2.calc.atr import rolling_atr_pct_nanmedian
from path2.eval import (  # noqa: F401 —— 后续批次扩展导入
    DEFAULT_FP_K,
    FIRST_PASSAGE_SEED,
    RANDOM_DAY_K,
    _first_passage_at,
    _index_runs,
    _resolve_end_events,
    _ticker_seed,
    daily_first_passage,
    match_first_passage,
    random_day_first_passage,
    spans_first_passage,
)


# ---- 测试用 Event / PatternMatch 桩(与 test_eval.py 同口径) -------------------

class Ev(Event):
    pass


def _ev(s, e):
    return Ev(start_idx=s, end_idx=e, confirm_idx=s)


def _match(binding, node="tb"):
    members = binding if isinstance(binding, tuple) else (binding,)
    return PatternMatch(
        start_idx=members[0].start_idx,
        end_idx=members[-1].end_idx,
        confirm_idx=members[0].start_idx,
        pattern_id="p",
        node_index={node: binding},
        children=members,
        predicate_trace=PredicateTrace(where_results={}, edge_results={}),
    )


# ---------------------------------------------------------------------------
# 常量与辅助:DEFAULT_FP_K / _ticker_seed
# ---------------------------------------------------------------------------

def test_default_fp_k_constant():
    """默认几何对称阈值参数 k=5.0(波动率标准化后,单一参数取代旧多对百分比阈值)。"""
    assert DEFAULT_FP_K == 5.0
    assert RANDOM_DAY_K == 3
    assert FIRST_PASSAGE_SEED == 777


def test_ticker_seed_md5_formula():
    """_ticker_seed 等价于 md5 公式:(int(md5_hex,16) % 2**32) ^ seed。"""
    ticker, seed = "AAPL", 777
    expected = (int(hashlib.md5(ticker.encode()).hexdigest(), 16) % 2 ** 32) ^ seed
    assert _ticker_seed(ticker, seed) == expected


def test_ticker_seed_different_tickers_differ():
    """不同 ticker → 不同 seed(md5 抗碰撞,实际必然不等)。"""
    assert _ticker_seed("AAAA", 777) != _ticker_seed("ZZZZ", 777)


def test_ticker_seed_default_seed_arg():
    """seed 缺省 = FIRST_PASSAGE_SEED。"""
    ticker = "MSFT"
    assert _ticker_seed(ticker) == _ticker_seed(ticker, FIRST_PASSAGE_SEED)


def test_ticker_seed_cross_process_stable():
    """md5 修正:跨进程(PYTHONHASHSEED 不同)_ticker_seed 逐字相等。

    内建 hash(str) 受 PYTHONHASHSEED 影响会跨进程漂移;md5 不受。
    本测试在两个不同 PYTHONHASHSEED 的子进程里各算一次,断言相等 —— 直接
    坐实"改 md5"这一修正相对"内建 hash"的差别。
    """
    snippet = (
        "from path2.eval import _ticker_seed; "
        "print(_ticker_seed('AAPL', 777))"
    )
    env_base = {**os.environ}
    # 显式清掉可能继承的 PYTHONHASHSEED,再分别设两个不同值
    env0 = {**env_base, "PYTHONHASHSEED": "0"}
    env1 = {**env_base, "PYTHONHASHSEED": "1"}
    r0 = subprocess.run(
        [sys.executable, "-c", snippet], capture_output=True, text=True, env=env0,
    )
    r1 = subprocess.run(
        [sys.executable, "-c", snippet], capture_output=True, text=True, env=env1,
    )
    assert r0.returncode == 0, f"子进程0失败: {r0.stderr}"
    assert r1.returncode == 0, f"子进程1失败: {r1.stderr}"
    assert r0.stdout.strip() == r1.stdout.strip()
    # 再对照 md5 公式直接定值
    expected = (int(hashlib.md5(b"AAPL").hexdigest(), 16) % 2 ** 32) ^ 777
    assert int(r0.stdout.strip()) == expected


# ---------------------------------------------------------------------------
# _first_passage_at:单点首次穿越方向(几何对称单参数 k + 波动率尺度 M)。
# 上行线 = c0*(1+k*M[t]);下行线 = c0/(1+k*M[t])(相乘≈1,可逆对称)。
# M[t] 非有限(样本不足)→ None(跳过);t+n 越界 → None。
# ---------------------------------------------------------------------------

def _fp_arrays(closes, highs, lows, M_val=0.03):
    """造 hi/lo/cl/M 四数组(M 恒定 M_val,长度补齐)。"""
    n = len(closes)
    return (
        np.array([float(x) for x in highs]),
        np.array([float(x) for x in lows]),
        np.array([float(x) for x in closes]),
        np.full(n, float(M_val)),   # M 恒定,聚焦阈值几何语义
    )


def test_first_passage_at_up():
    """M=0.03、k=2:上行线=100*(1+0.06)=106;high[1]=116 触上行 → up。"""
    hi, lo, cl, M = _fp_arrays([100, 100, 100, 100, 100],
                               [100, 116, 100, 100, 100],
                               [100, 99, 100, 100, 100])
    assert _first_passage_at(hi, lo, cl, M, t=0, n=3, k=2.0) == "up"


def test_first_passage_at_down():
    """M=0.03、k=2:下行线=100/(1.06)=94.34;low[1]=93 触下行 → down。"""
    hi, lo, cl, M = _fp_arrays([100, 100, 100, 100, 100],
                               [100, 101, 100, 100, 100],
                               [100, 93, 100, 100, 100])
    assert _first_passage_at(hi, lo, cl, M, t=0, n=3, k=2.0) == "down"


def test_first_passage_at_geometric_symmetry():
    """几何对称判别:上行 +kM、下行不是 -kM 而是 -kM/(1+kM)。M=0.10、k=1:
    上行线=110;几何下行线=100/1.1=90.909(算术下行线=90)。取 low[1]=90.5 ∈ (90, 90.909]:
    几何实现 → 90.5 ≤ 90.909 触下行 → "down";算术实现 → 90.5 > 90 不触 → "none"。
    high[1]=105 < 110 不触上行。故该测试对「下行线写法」有判别力(守住几何对称性)。"""
    hi, lo, cl, M = _fp_arrays([100, 100, 100], [100, 105, 100], [100, 90.5, 100], M_val=0.10)
    assert _first_passage_at(hi, lo, cl, M, t=0, n=2, k=1.0) == "down"


def test_first_passage_at_nan_M_returns_none():
    """M[t]=nan(样本不足)→ None(跳过该买点日)。"""
    hi, lo, cl, M = _fp_arrays([100, 116, 100, 100], [100, 116, 100, 100], [100, 99, 100, 100])
    M[0] = np.nan
    assert _first_passage_at(hi, lo, cl, M, t=0, n=2, k=2.0) is None


def test_first_passage_at_out_of_range():
    """t+n 越界 → None。"""
    hi, lo, cl, M = _fp_arrays([100, 100, 100, 100, 100], [100, 100, 100, 100, 100], [100, 100, 100, 100, 100])
    assert _first_passage_at(hi, lo, cl, M, t=3, n=2, k=2.0) is None   # 3+2>=5


# ---------------------------------------------------------------------------
# match_first_passage:end_node event span 全买点日计数,单组 {up,down,both,none}。
# 内算 M(rolling_atr_pct_nanmedian, period=20)。M[t]=nan 的买点日跳过。
# ---------------------------------------------------------------------------

def _fp_df(closes, highs, lows, dates="2024-01-01"):
    import pandas as pd
    n = len(closes)
    return pd.DataFrame({
        "date": pd.date_range(dates, periods=n, freq="D"),
        "close": [float(c) for c in closes],
        "high": [float(h) for h in highs],
        "low": [float(l) for l in lows],
    })


def test_match_first_passage_single_buyday_up():
    """单买点日 ev=[20,20]、M 恒定(造 df 使 TR/close 恒定):high[21] 触上行 → up=1。

    buyday 放在 idx=20(period=20 warm-up 后首个非 NaN M 处):close 恒 100、
    high-low 恒 3 → TR/close=0.03 恒定,M[20]=0.03。horizon=3 → 检查 high[21..23]。
    """
    df = _fp_df([100]*30, [103]*30, [100]*30)
    df.loc[21, "high"] = 116   # 第 21 根冲高触上行(上行线=100*1.06=106)
    m = _match(_ev(20, 20))
    out = match_first_passage(m, "tb", df, horizon=3, k=2.0)
    assert out == {"up": 1, "down": 0, "both": 0, "none": 0}


def test_match_first_passage_spans_all_buydays():
    """span 全买点日计数:ev=[20,22] 三日均 up → up=3(M 在 period=20 warm-up 后非空)。"""
    df = _fp_df([100]*30, [103]*30, [100]*30)
    for i in (21, 22, 23):
        df.loc[i, "high"] = 116   # 三根均触上行(覆盖三买点日的 horizon 窗口)
    m = _match(_ev(20, 22))
    out = match_first_passage(m, "tb", df, horizon=3, k=2.0)
    assert out["up"] == 3


def test_match_first_passage_missing_node_raises():
    df = _fp_df([100]*30, [103]*30, [100]*30)
    m = _match(_ev(20, 20))
    with pytest.raises(KeyError):
        match_first_passage(m, "nope", df, horizon=3, k=2.0)


# ---------------------------------------------------------------------------
# random_day_first_passage:全宇宙随机日基线,单组 {up,down,both,none} 计数。
# 内算 M(rolling_atr_pct_nanmedian, period=20);seed 由 ticker md5 派生、跨进程稳定。
# ---------------------------------------------------------------------------

def _rand_df(n_days=60):
    """造可分辨穿越模式的 df:close 恒 100、high=103/low=100 → TR/close 恒 0.03,
    period=20 warm-up 后 M 恒 0.03。up_line=106、dn_line=94.34 全程不触 → 四态健全。"""
    return pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n_days, freq="D"),
        "close": [100.0] * n_days,
        "high": [103.0] * n_days,
        "low": [100.0] * n_days,
    })


def test_random_day_first_passage_counts_single_group():
    """counts 单组 {up,down,both,none}(不再按 pair_key 分);n_sampled == sum(counts)。"""
    df = _rand_df(n_days=60)
    out = random_day_first_passage(
        "AAA", df, df["date"].iat[25], df["date"].iat[40], horizon=3, k=2.0,
    )
    assert set(out["counts"]) == {"up", "down", "both", "none"}
    assert sum(out["counts"].values()) == out["n_sampled"]


def test_random_day_first_passage_no_candidates():
    """候选日为空(horizon >= n_bars,所有 i 都不满足 i+horizon<n_bars)→ n_sampled=0、
    counts 四态零(键齐全)。"""
    df = _rand_df(n_days=60)
    out = random_day_first_passage(
        "AAA", df, df["date"].iat[0], df["date"].iat[59], horizon=60, k=2.0,
    )
    assert out["n_sampled"] == 0
    assert out["counts"] == {"up": 0, "down": 0, "both": 0, "none": 0}


# ---------------------------------------------------------------------------
# spans_first_passage + match_first_passage 改造:match_first_passage 现在把各 event 的
# sample_bar_indices() 压成连续段交给 spans_first_passage。对拍基准 = 改造前的逐 event、
# 逐买点日直白版(_legacy_match_first_passage),要求四态计数逐位相等。
# ---------------------------------------------------------------------------

_FIXTURE_CSV = Path(__file__).resolve().parent / "fixtures" / "aapl_vol_slice.csv"
_STATES = ("up", "down", "both", "none")


def _legacy_match_first_passage(match, end_node, df, horizon, k, sample_window=None, M=None):
    """改造前 match_first_passage 的直白版:逐 event、逐 sample_bar_indices() 买点日调
    _first_passage_at 累计四态。"""
    events = _resolve_end_events(match, end_node)
    if M is None:
        M = rolling_atr_pct_nanmedian(df["high"], df["low"], df["close"], 20).values
    hi, lo, cl = df["high"].values, df["low"].values, df["close"].values
    counts = {s: 0 for s in _STATES}
    for ev in events:
        for t in ev.sample_bar_indices():
            if sample_window is not None and not (sample_window[0] <= t <= sample_window[1]):
                continue
            state = _first_passage_at(hi, lo, cl, M, t, horizon, k)
            if state is not None:
                counts[state] += 1
    return counts


def _walk_df(n, seed):
    """几何随机游走 OHLC + 交易日日期。约 5% 的根振幅放大 6 倍,使同根上下双触(both)
    也能出现;其余根的影线幅度随机,四态在 k=1~2 时都有样本。"""
    rng = np.random.default_rng(seed)
    close = 50.0 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    span = np.abs(rng.normal(0, 0.015, n)) + 0.002
    span[rng.random(n) < 0.05] *= 6
    return pd.DataFrame({
        "date": pd.bdate_range("2024-01-02", periods=n),
        "close": close,
        "high": close * (1 + span * rng.random(n)),
        "low": close * (1 - span * rng.random(n)),
    })


@dataclass(frozen=True)
class _Scattered(Event):
    """覆写 sample_bar_indices 的容器桩:买点日乱序、跳号、含重复。"""
    picks: tuple = ()

    def sample_bar_indices(self):
        return self.picks


@dataclass(frozen=True)
class _Holder(Event):
    """带 segments 槽的容器桩,供 'tb.segments' 路径解析出多个 child。"""
    segs: tuple = ()

    def child_slots(self):
        return {"segments": self.segs}


def test_index_runs_expands_back_to_original_sequence():
    """压段后逐段展开 == 原序列(顺序、跳号、重复、倒序全保留)。"""
    seqs = [
        [], [7], list(range(3, 9)), [5, 6, 7, 10, 11, 3, 3, 4, 2, 1],
        [np.int64(4), np.int64(5), np.int64(9)],
    ]
    for seq in seqs:
        runs = _index_runs(seq)
        assert [t for a, b in runs for t in range(a, b + 1)] == [int(t) for t in seq]
    assert _index_runs([5, 6, 7, 10, 11, 3, 3, 4]) == [(5, 7), (10, 11), (3, 3), (3, 4)]


def test_match_first_passage_equals_legacy_on_random_spans():
    """合成随机游走 + 随机 span(含热身期 M=NaN 段与尾部 horizon 越界段)× sample_window
    × 内算/外传 M × 多组 horizon/k:match_first_passage、spans_first_passage 与直白版三方逐位相等。"""
    df = _walk_df(260, seed=11)
    M_ext = rolling_atr_pct_nanmedian(df["high"], df["low"], df["close"], 20).values
    rng = np.random.default_rng(5)
    seen = {s: 0 for s in _STATES}
    for _ in range(120):
        s0 = int(rng.integers(0, 250))
        e0 = int(min(259, s0 + rng.integers(0, 40)))
        horizon = int(rng.choice([1, 5, 20]))
        k = float(rng.choice([1.0, 2.0, 5.0]))
        lo_w = int(rng.integers(0, 200))
        sw = None if rng.random() < 0.4 else (lo_w, lo_w + int(rng.integers(0, 60)))
        M = None if rng.random() < 0.5 else M_ext
        m = _match(_ev(s0, e0))
        ref = _legacy_match_first_passage(m, "tb", df, horizon, k, sw, M)
        assert match_first_passage(m, "tb", df, horizon, k, sw, M) == ref
        assert spans_first_passage(df, [(s0, e0)], horizon, k, sw, M) == ref
        for st in _STATES:
            seen[st] += ref[st]
    assert all(v > 0 for v in seen.values()), seen   # 四态都有样本,对拍才有牙齿


def test_match_first_passage_equals_legacy_with_overridden_sample_bar_indices():
    """end_node 为 'tb.segments':child 混合普通 span 与覆写 sample_bar_indices 的容器
    (乱序/跳号/重复);另测 end_node 直接指向覆写容器。均与直白版逐位相等。"""
    df = _walk_df(200, seed=3)
    picks = (40, 41, 42, 60, 44, 44, 43, 190, 199, 21, 22, 22)
    scattered = _Scattered(start_idx=21, end_idx=199, confirm_idx=21, picks=picks)
    holder = _Holder(start_idx=20, end_idx=199, confirm_idx=20,
                     segs=(_ev(30, 55), scattered, _ev(50, 70), _ev(185, 199)))
    m_slot = _match(holder)
    m_direct = _match(scattered)
    total = 0
    for horizon, k in [(1, 1.0), (5, 2.0), (12, 1.0)]:
        for sw in (None, (25, 60), (44, 44)):
            ref = _legacy_match_first_passage(m_slot, "tb.segments", df, horizon, k, sw)
            assert match_first_passage(m_slot, "tb.segments", df, horizon, k, sw) == ref
            total += sum(ref.values())
            ref_d = _legacy_match_first_passage(m_direct, "tb", df, horizon, k, sw)
            assert match_first_passage(m_direct, "tb", df, horizon, k, sw) == ref_d
    assert total > 0


def test_match_first_passage_equals_legacy_on_positive_case_fixture():
    """共享 fixture(bottom_burst 合成正例)跑出真实 match,end_node 取 eval_meta 的
    'tb.segments'(多 child)与 'tb'(容器整 span):与直白版逐位相等。"""
    from path2.dag.engine import analyze
    from path2_apps.bottom_burst.dag_spec import build_pattern, eval_meta
    from tests.path2.fixtures.positive_case import positive_case

    df, params = positive_case()
    res = analyze(build_pattern(params), df, params)
    assert res.matches, "positive_case fixture 应至少命中一个 match"
    end_node = eval_meta(params)["end_node"]
    total = 0
    for m in res.matches:
        for node in (end_node, "tb"):
            for horizon in (5, 10, 40):
                for sw in (None, (270, 295)):
                    ref = _legacy_match_first_passage(m, node, df, horizon, 2.0, sw)
                    assert match_first_passage(m, node, df, horizon, 2.0, sw) == ref
                    total += sum(ref.values())
    assert total > 0


def test_spans_first_passage_duplicate_spans_counted_twice():
    """重复 span 重复计数(去重归调用方);空 spans → 四态零。"""
    df = _walk_df(120, seed=8)
    one = spans_first_passage(df, [(30, 50)], 5, 1.0)
    two = spans_first_passage(df, [(30, 50), (30, 50)], 5, 1.0)
    assert sum(one.values()) > 0
    assert two == {s: 2 * v for s, v in one.items()}
    assert spans_first_passage(df, [], 5, 1.0) == {s: 0 for s in _STATES}


def test_spans_first_passage_skips_warmup_and_tail():
    """span 覆盖热身期(M=NaN,下标 <19)与尾部越界(t+horizon>=len):只数中间合格日。"""
    df = _walk_df(60, seed=2)
    out = spans_first_passage(df, [(0, 59)], horizon=10, k=1.0)
    assert sum(out.values()) == 49 - 19 + 1   # 合格 t ∈ [19, 49]


def test_spans_first_passage_M_length_mismatch_raises():
    df = _walk_df(60, seed=2)
    M = rolling_atr_pct_nanmedian(df["high"], df["low"], df["close"], 20).values
    with pytest.raises(ValueError):
        spans_first_passage(df, [(20, 30)], 5, 1.0, M=M[:-1])


# ---------------------------------------------------------------------------
# daily_first_passage:逐日一行。对拍基准 = 逐日调 _first_passage_at 的直白版
# (_daily_reference),列顺序、dtype、取值全部逐位相等。
# ---------------------------------------------------------------------------

def _daily_reference(df, start_ts, end_ts, horizon, k, M=None):
    """逐日直白版:区间内每个 i 调 _first_passage_at,非 None 即合格日、写一行 one-hot。"""
    if M is None:
        M = rolling_atr_pct_nanmedian(df["high"], df["low"], df["close"], 20).values
    hi, lo, cl = df["high"].values, df["low"].values, df["close"].values
    dates = pd.to_datetime(df["date"])
    rows = {c: [] for c in ("idx", "date", "close", "M", *_STATES)}
    for i in range(len(df)):
        if not (start_ts <= dates.iat[i] <= end_ts):
            continue
        state = _first_passage_at(hi, lo, cl, M, i, horizon, k)
        if state is None:
            continue
        rows["idx"].append(i)
        rows["date"].append(dates.iat[i])
        rows["close"].append(cl[i])
        rows["M"].append(M[i])
        for st in _STATES:
            rows[st].append(1 if st == state else 0)
    return pd.DataFrame({
        "idx": np.array(rows["idx"], dtype=np.int64),
        "date": np.array(rows["date"], dtype="datetime64[ns]"),
        "close": np.array(rows["close"], dtype=np.float64),
        "M": np.array(rows["M"], dtype=np.float64),
        **{st: np.array(rows[st], dtype=np.int8) for st in _STATES},
    })


def _assert_daily_equal(got, ref):
    assert list(got.columns) == ["idx", "date", "close", "M", "up", "down", "both", "none"]
    pd.testing.assert_frame_equal(got, ref, check_exact=True)


def test_daily_first_passage_equals_reference_synthetic():
    """合成随机游走 + 外传 M(注入 NaN / 0 / 负数 / inf 使 M 无效)× 多组 horizon/k ×
    窗口边界(恰落在交易日上 / 落在两日之间 / 覆盖尾部越界段):与逐日直白版逐位相等。"""
    df = _walk_df(300, seed=21)
    M = rolling_atr_pct_nanmedian(df["high"], df["low"], df["close"], 20).values
    M[[40, 41, 90]] = np.nan
    M[120] = 0.0
    M[121] = -0.01
    M[150] = np.inf
    d = df["date"]
    half_day = pd.Timedelta(hours=12)
    windows = [
        (d.iat[0], d.iat[299]),                        # 全程(含热身与尾部越界)
        (d.iat[40], d.iat[121]),                       # 边界恰为交易日(双端含,且边界日 M 无效)
        (d.iat[60] + half_day, d.iat[200] - half_day), # 边界落在两日之间 → 60、200 均不入
        (d.iat[250], d.iat[299] + pd.Timedelta(days=30)),  # 尾部:i+horizon 越界被剔
        (d.iat[100], d.iat[100]),                      # 单日窗口
    ]
    seen = {s: 0 for s in _STATES}
    for horizon, k in [(1, 1.0), (7, 2.0), (30, 1.0), (30, 5.0)]:
        for s0, e0 in windows:
            ref = _daily_reference(df, s0, e0, horizon, k, M)
            _assert_daily_equal(daily_first_passage(df, s0, e0, horizon, k, M), ref)
            for st in _STATES:
                seen[st] += int(ref[st].sum())
    assert all(v > 0 for v in seen.values()), seen


def test_daily_first_passage_window_boundaries_inclusive():
    """start/end 恰为交易日时两端都入选;落在两日之间时相邻日不入。"""
    df = _walk_df(120, seed=4)
    d = df["date"]
    got = daily_first_passage(df, d.iat[30], d.iat[40], horizon=5, k=1.0)
    assert got["idx"].tolist() == list(range(30, 41))
    half_day = pd.Timedelta(hours=12)
    got = daily_first_passage(df, d.iat[30] + half_day, d.iat[40] - half_day, horizon=5, k=1.0)
    assert got["idx"].tolist() == list(range(31, 40))


def test_daily_first_passage_one_hot_and_internal_M():
    """内算 M 与外传同一 M 结果相同;每行 one-hot 恰一个 1。"""
    df = _walk_df(200, seed=9)
    M = rolling_atr_pct_nanmedian(df["high"], df["low"], df["close"], 20).values
    s0, e0 = df["date"].iat[0], df["date"].iat[199]
    a = daily_first_passage(df, s0, e0, 10, 2.0)
    b = daily_first_passage(df, s0, e0, 10, 2.0, M=M)
    pd.testing.assert_frame_equal(a, b, check_exact=True)
    assert (a[list(_STATES)].sum(axis=1) == 1).all()
    assert len(a) == 189 - 19 + 1   # 合格 i ∈ [19, 189](i+10<200)


def test_daily_first_passage_empty_keeps_schema():
    """无合格日(horizon >= len 或区间无交易日)→ 空表,列与 dtype 不变。"""
    df = _walk_df(50, seed=1)
    d = df["date"]
    ref = _daily_reference(df, d.iat[0], d.iat[49], 50, 1.0)
    assert len(ref) == 0
    _assert_daily_equal(daily_first_passage(df, d.iat[0], d.iat[49], 50, 1.0), ref)
    future = d.iat[49] + pd.Timedelta(days=10)
    _assert_daily_equal(daily_first_passage(df, future, future, 5, 1.0), ref)


def test_daily_first_passage_M_length_mismatch_raises():
    df = _walk_df(60, seed=2)
    M = rolling_atr_pct_nanmedian(df["high"], df["low"], df["close"], 20).values
    with pytest.raises(ValueError):
        daily_first_passage(df, df["date"].iat[0], df["date"].iat[59], 5, 1.0, M=M[:-1])


def test_daily_first_passage_equals_reference_on_real_prices():
    """真实价格 fixture(aapl_vol_slice.csv,2024-03 起约 320 根)内算 M:与逐日直白版逐位相等。"""
    df = pd.read_csv(_FIXTURE_CSV, parse_dates=["date"])
    s0, e0 = df["date"].iat[0], df["date"].iat[len(df) - 1]
    for horizon, k in [(10, 2.0), (40, 5.0)]:
        ref = _daily_reference(df, s0, e0, horizon, k)
        assert len(ref) > 0
        _assert_daily_equal(daily_first_passage(df, s0, e0, horizon, k), ref)
