"""path2/eval.py:首次穿越方向(first-passage)计算函数的测试。

覆盖:
  - 常量 / 辅助:DEFAULT_FP_K、_ticker_seed(md5 跨进程稳定)
  - _first_passage_at:几何对称单 k + 波动率尺度 M,四态(up/down/both/none)+ 越界
  - match_first_passage:per-match 入口,单组四态计数(内算 M)
  - random_day_first_passage:随机日基线(Task 3 重写后的测试由 Task 3 落地)
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from path2.core import Event
from path2.dag.result import PatternMatch, PredicateTrace
from path2.eval import (  # noqa: F401 —— 后续批次扩展导入
    DEFAULT_FP_K,
    FIRST_PASSAGE_SEED,
    RANDOM_DAY_K,
    _first_passage_at,
    _ticker_seed,
    match_first_passage,
    random_day_first_passage,
)


# ---- 测试用 Event / PatternMatch 桩(与 test_eval.py 同口径) -------------------

class Ev(Event):
    class_id = "test_fp_ev"


def _ev(s, e):
    return Ev(event_id=f"e_{s}_{e}", start_idx=s, end_idx=e, confirm_idx=s)


def _match(binding, node="tb"):
    members = binding if isinstance(binding, tuple) else (binding,)
    return PatternMatch(
        event_id="m",
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
