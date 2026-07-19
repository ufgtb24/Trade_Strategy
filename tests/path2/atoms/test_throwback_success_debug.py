"""Task 1 · throwback 成功链路 4 处 debug_break 埋点回归测试。

每处 debug_break 参数必须与即将 return / event 字段的 bar 值对齐(v2 契约 #4):
  - evaluate_throwback 入口 → bo_idx
  - _find_start_idx return trough_idx 前 → trough_idx
  - _find_end_idx return i - 1 前 → i - 1(⚠ 不是 i)
  - _find_end_idx return end_scan 前 → end_scan
"""
from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd

from path2.atoms.breakout import BOEvent
from path2.atoms.throwback import evaluate_throwback


def _make_df(n: int = 100, seed: int = 0) -> pd.DataFrame:
    """构造一段 OHLC · 有单调爬升 + 中段回踩 + 大涨的形态,让 tb 能跑到 4 处成功路径。"""
    rng = np.random.default_rng(seed)
    close = np.cumsum(rng.normal(0.5, 1.0, n)) + 100.0
    high = close + 1.0
    low = close - 1.0
    open_ = close - 0.2
    return pd.DataFrame({
        'open': open_, 'high': high, 'low': low, 'close': close,
        'volume': np.ones(n) * 1000.0,
    })


def _fixture_bo(df: pd.DataFrame, idx: int) -> BOEvent:
    """构造一个 BO event 指向 df 里第 idx 根 bar 作 breakout。"""
    return BOEvent(start_idx=idx, end_idx=idx, event_id=f"bo_test_{idx}")


def test_evaluate_throwback_calls_debug_break_at_entry():
    """arch2 v2 · L244 埋点:evaluate_throwback 入口(bo_idx = bo.end_idx 之后)"""
    df = _make_df(n=100)
    bo = _fixture_bo(df, idx=30)
    with patch('path2.atoms.throwback.debug_break') as mock_break:
        evaluate_throwback(bo, df, max_start_gap=5, max_window=5)
    calls = [c.args[0] for c in mock_break.call_args_list]
    assert 30 in calls, f"expected bo_idx=30 in debug_break calls, got {calls}"


def test_find_start_idx_calls_debug_break_before_return_trough():
    """arch2 v2 · L163 埋点:_find_start_idx return trough_idx 前(与 event.start_idx 对齐)

    构造一段: bo 后 low 单调下降到 trough,然后 low 抬头(_has_stop_signal)+ 高深度回撤,
    使 _find_start_idx 走成功路径 return trough_idx。

    ⚠ fixture 修正(非 brief 原样):anchor = measure_at(bo_idx-1, "high"),若 bo 紧跟在单调
    上涨的最高点之后(如原始 [0..30] 涨到 130 后 31 即 bo),anchor 本身就是全程最高价,
    随后任何回踩(即使很浅)都会立即破位(measured_support < anchor → phase1_break →
    提前 return None),trough 成功路径永远不可达,与实现是否正确无关(实测验证:见
    Task 1 report)。修正为「bo 处跳空突破」形态:[0..30] 温和爬升到 108(锚点仅 108.5),
    31 跳空至 128(真正的突破动作),[32..40] 从跳空高点回落到 114(比锚点 108.5 高出充分
    余量,不破位),[41,42] 抬头确认止跌 → trough_idx=40,与原断言区间 [40,45] 保持一致。
    """
    n = 100
    close = np.linspace(100, 108, 31).tolist()        # [0..30] 温和爬升至 108(锚点低)
    close += [128.0]                                   # [31] bo 跳空突破
    close += np.linspace(127, 114, 9).tolist()          # [32..40] 从跳空高点回落到 114
    close += [115.0, 117.0]                             # [41,42] 抬头止跌
    close += np.linspace(118, 150, n - 43).tolist()    # [43..] 继续爬
    close = np.array(close[:n])
    low = close - 0.5
    high = close + 0.5
    df = pd.DataFrame({
        'open': close - 0.1, 'high': high, 'low': low, 'close': close,
        'volume': np.ones(n) * 1000.0,
    })
    bo = _fixture_bo(df, idx=31)
    with patch('path2.atoms.throwback.debug_break') as mock_break:
        evaluate_throwback(bo, df, max_start_gap=15, max_window=15,
                            pullback_min_atr=0.1)  # 放宽 gate 让 trough 通过
    calls = [c.args[0] for c in mock_break.call_args_list]
    # trough_idx 应落在 [40, 45](实测 trough_idx=40)
    trough_candidates = [c for c in calls if 40 <= c <= 45]
    assert trough_candidates, f"expected trough_idx in [40,45], got calls={calls}"


def test_find_end_idx_calls_debug_break_with_i_minus_1_on_rise():
    """arch2 v2 · L215 埋点:_find_end_idx return i - 1 前(大涨触发)

    ⚠ 参数必须 i - 1 不是 i(与 event.end_idx 对齐 · v2 契约 #4 R11)
    构造大涨形态: bo → trough → 从 trough 起某根 high - base_min >= big_rise_k * atr。

    ⚠ fixture 修正(非 brief 原样,同 test_find_start_idx_calls_debug_break_before_return_trough
    的 anchor-破位 根因):改用「bo 处跳空突破」形态避免 trough 提前破位。
    另需注意:trough_idx(本例=36)必须落在断言区间 [40,50] 之外 —— 否则 debug_break(trough_idx)
    (L163,与本测试目标 L215 无关)会与本测试的范围断言重叠,导致 L215 即使未实现该测试也会
    误报通过(实测验证:trough 若落在 40-42,pre-L215 状态下 calls 仍会含 40-42,让本该 FAIL 的
    RED 步骤提前 PASS)。故本 fixture 特意让 trough 更早出现(缩短回落段至 5 根,trough_idx=36),
    并把触发大涨的那根推迟到 45(i=45→end=44),确保只有 L215 真正实现后 44 才会出现在 calls 里。
    """
    n = 100
    close = np.linspace(100, 108, 31).tolist()          # [0..30] 温和爬升至 108(锚点低)
    close += [128.0]                                     # [31] bo 跳空突破
    close += np.linspace(127, 118, 5).tolist()            # [32..36] 回落到 118 → trough_idx=36
    close += [118.1, 118.2]                               # [37,38] 抬头止跌
    # [39..44] 低波动横盘(远低于 big_rise_k*atr 阈值,不提前触发大涨)
    close += [118.15, 118.05, 118.1, 118.0, 117.95, 118.05]
    close += [140.0]                                      # [45] 大涨触发,i=45 → end=44
    close += np.linspace(141, 180, n - 46).tolist()
    close = np.array(close[:n])
    low = close - 0.5
    high = close + 0.5
    df = pd.DataFrame({
        'open': close - 0.1, 'high': high, 'low': low, 'close': close,
        'volume': np.ones(n) * 1000.0,
    })
    bo = _fixture_bo(df, idx=31)
    with patch('path2.atoms.throwback.debug_break') as mock_break:
        evaluate_throwback(bo, df, max_start_gap=15, max_window=15,
                            pullback_min_atr=0.1, big_rise_k=1.5)
    calls = [c.args[0] for c in mock_break.call_args_list]
    # end = i - 1;i=45 触发大涨,end 应为 44(实测:trough_idx=36 落在区间外,不干扰本断言)
    rise_end_candidates = [c for c in calls if 40 <= c <= 50]
    assert rise_end_candidates, f"expected rise_end (i-1) in [40,50], got calls={calls}"
    # 验证参数 i - 1 不是 i:如果是 i,end 会落在 45;如果是 i - 1(正确),end 落在 44
    assert 45 not in calls, f"debug_break should fire with i-1=44, not i=45; got calls={calls}"


def test_find_end_idx_calls_debug_break_with_end_scan_on_timeout():
    """arch2 v2 · L219 埋点:_find_end_idx return end_scan 前(timeout · 无大涨无破位)

    构造 trough 后一段 low-volatility(既不破位也不大涨),扫满 max_window 触发 timeout。

    ⚠ fixture 修正(非 brief 原样,同组另两个 test 的 anchor-破位 根因):改用「bo 处跳空突破」
    形态避免 trough 提前破位;trough_idx=40,max_window=15 → end_scan=55,与原断言区间
    [55,65] 保持一致。
    """
    n = 100
    close = np.linspace(100, 108, 31).tolist()          # [0..30] 温和爬升至 108(锚点低)
    close += [128.0]                                     # [31] bo 跳空突破
    close += np.linspace(127, 114, 9).tolist()            # [32..40] 回落到 114 → trough_idx=40
    close += [114.1, 114.2]                               # [41,42] 抬头止跌
    # [43..56] low-volatility:小幅波动,不破 anchor(108.5),不大涨(big_rise_k=100 阻断)
    close += [114.15, 114.25, 114.1, 114.3, 114.2, 114.35, 114.25,
              114.4, 114.3, 114.45, 114.35, 114.5, 114.4, 114.55]
    close += np.linspace(close[-1] + 1, 150, n - len(close)).tolist()
    close = np.array(close[:n])
    low = close - 0.5
    high = close + 0.5    # high - low = 1.0,不会大涨
    df = pd.DataFrame({
        'open': close - 0.1, 'high': high, 'low': low, 'close': close,
        'volume': np.ones(n) * 1000.0,
    })
    bo = _fixture_bo(df, idx=31)
    with patch('path2.atoms.throwback.debug_break') as mock_break:
        evaluate_throwback(bo, df, max_start_gap=15, max_window=15,
                            pullback_min_atr=0.1, big_rise_k=100.0)  # 大 k 阻大涨
    calls = [c.args[0] for c in mock_break.call_args_list]
    # end_scan = start_idx + max_window;trough=40,+15=55(实测)
    timeout_end_candidates = [c for c in calls if 55 <= c <= 65]
    assert timeout_end_candidates, f"expected end_scan (timeout end) in [55,65], got calls={calls}"
