"""因果闸端到端测试:_eval_ticker 拒绝买点早于事件确认 bar(confirm_idx)的 match。

依据 11_path2_causal_gate_guide.md:retrospective 事件(burst/trend/platform)
confirm_idx=end,若误用其 start_idx 当买点是前瞻,因果闸须 raise。
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pytest

from path2.core import Event
from path2.dag.result import PatternMatch, AnalysisResult
from path2_web import eval_runner

APP = "path2_apps.bottom_burst"


@dataclass(frozen=True)
class _RetroEvent(Event):
    """retrospective 事件:成立在 end(confirm_idx=end > start_idx)。"""


def _gate_violation_res():
    """违规 match:end_node event start_idx=5 < confirm_idx=10(用 start 当买点是前瞻)。"""
    retro = _RetroEvent(start_idx=5, end_idx=10, confirm_idx=10,
                        node_id="end", instance_id="r1")
    m = PatternMatch(
        match_id="m1", start_idx=5, end_idx=10, confirm_idx=10,
        pattern_id="fake", node_index={"end": retro}, children=(retro,))
    return AnalysisResult(events=(retro,), matches=(m,), spec=None)


def _gate_ok_res():
    """合法 match:end_node event start_idx==confirm_idx(确认类,如 tb)。"""
    ev = _RetroEvent(start_idx=7, end_idx=10, confirm_idx=7,
                     node_id="end", instance_id="ok1")
    m = PatternMatch(
        match_id="mok", start_idx=7, end_idx=10, confirm_idx=7,
        pattern_id="fake", node_index={"end": ev}, children=(ev,))
    return AnalysisResult(events=(ev,), matches=(m,), spec=None)


def _write_df(tmp_path):
    n = 100
    df = pd.DataFrame({
        "open": np.arange(n, dtype=float),
        "high": np.arange(n, dtype=float) + 1,
        "low": np.arange(n, dtype=float) - 1,
        "close": np.arange(n, dtype=float),
        "volume": [1000.0] * n,
    }, index=pd.date_range("2025-01-01", periods=n, freq="D", name="date"))
    p = tmp_path / "GATE.pkl"
    df.to_pickle(p)
    return str(p)


def test_causal_gate_rejects_buypoint_before_confirm(monkeypatch, tmp_path):
    """start_idx < confirm_idx → 因果闸 raise → err 含'因果闸',rows 空。"""
    monkeypatch.setattr(eval_runner, "_dag_analyze",
                        lambda spec, win, params: _gate_violation_res())
    symbol, rows, err = eval_runner._eval_ticker(
        _write_df(tmp_path), APP, "2025-01-01", "2025-12-31",
        horizons=(2,), end_node="end", head_buffer_trading_days=63,
        param_overrides=None)
    assert err is not None and "因果闸" in err
    assert rows == []


def test_causal_gate_passes_when_buypoint_at_confirm(monkeypatch, tmp_path):
    """start_idx == confirm_idx(确认类)→ 因果闸放行,正常产 rows。"""
    monkeypatch.setattr(eval_runner, "_dag_analyze",
                        lambda spec, win, params: _gate_ok_res())
    symbol, rows, err = eval_runner._eval_ticker(
        _write_df(tmp_path), APP, "2025-01-01", "2025-12-31",
        horizons=(2,), end_node="end", head_buffer_trading_days=63,
        param_overrides=None)
    assert err is None
    assert len(rows) >= 1
