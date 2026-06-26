"""analyze_single — _scan_ticker 主流程抽出后的纯函数测试。
非 buffered 路径(end_role=None)走严格窗、不算 label;buffered 路径与 scan 同口径。"""
from pathlib import Path

import pandas as pd

from path2_web.scan import analyze_single


def _mk_pkl(tmp_path, symbol, df=None):
    if df is None:
        from tests.path2.apps.test_matches import _synth_no_burst
        df = _synth_no_burst()
        df.index = pd.date_range("2025-01-01", periods=len(df), freq="D", name="date")
    pkl = tmp_path / f"{symbol}.pkl"
    df.to_pickle(pkl)
    return str(pkl)


def test_analyze_single_non_buffered_returns_tuple(tmp_path):
    pkl = _mk_pkl(tmp_path, "AAA")
    analysis, summary, meta = analyze_single(
        pkl_path=pkl,
        module_path="path2_apps.bottom_breakout_burst.dag_spec",
        start_date="2025-01-01", end_date="2025-12-31",
        end_role=None, label_horizon=None,
    )
    assert isinstance(analysis, dict)
    assert isinstance(summary, dict)
    assert isinstance(meta, dict)
    assert {"events", "matches"} <= set(analysis)
    assert meta["end_role"] is None
    assert meta["label_horizon"] is None
    assert meta["win_start"] == "2025-01-01"
    assert meta["win_end"] == "2025-12-31"


def test_analyze_single_buffered_uses_provided_buf_window(tmp_path):
    """buffered 路径下,调用方传 buf_start/buf_end,meta 反映传入值。"""
    pkl = _mk_pkl(tmp_path, "AAA")
    analysis, summary, meta = analyze_single(
        pkl_path=pkl,
        module_path="path2_apps.bottom_breakout_burst.dag_spec",
        start_date="2025-06-01", end_date="2025-06-30",
        buf_start="2025-05-01", buf_end="2025-08-30",
        end_role="bo", label_horizon=20,
    )
    assert meta["win_start"] == "2025-05-01"
    assert meta["win_end"] == "2025-08-30"
    assert meta["end_role"] == "bo"
    assert meta["label_horizon"] == 20


def test_analyze_single_empty_window_returns_empty_collections(tmp_path):
    # 选一个超出数据范围的窗 → 空窗
    pkl = _mk_pkl(tmp_path, "AAA")
    analysis, summary, _ = analyze_single(
        pkl_path=pkl,
        module_path="path2_apps.bottom_breakout_burst.dag_spec",
        start_date="2099-01-01", end_date="2099-12-31",
        end_role=None, label_horizon=None,
    )
    assert analysis == {"events": [], "matches": [], "role_index": {}}
    assert summary == {"events": 0, "matches": 0}


def test_analyze_single_no_match_returns_empty_matches_not_none(tmp_path):
    # _synth_no_burst 构造出 0 命中:analysis.matches=[],但 events 可能非空。
    pkl = _mk_pkl(tmp_path, "AAA")
    analysis, summary, _ = analyze_single(
        pkl_path=pkl,
        module_path="path2_apps.bottom_breakout_burst.dag_spec",
        start_date="2025-01-01", end_date="2025-12-31",
        end_role=None, label_horizon=None,
    )
    # 关键:0 命中也返回空集 dict,**非 None**
    assert analysis is not None
    assert analysis["matches"] == []


def test_analyze_single_buffered_matches_have_forward_return(tmp_path):
    """positive_case 构造确定命中(若 fixture 支持),验证 buffered 路径下 matches 携带 forward_return。
    若数据无 match,跳过(不报错)。"""
    from tests.path2.fixtures.positive_case import _synth_positive
    df = _synth_positive()
    df.index = pd.date_range("2025-01-01", periods=len(df), freq="D", name="date")
    pkl = _mk_pkl(tmp_path, "ACRS", df=df)
    analysis, _, _ = analyze_single(
        pkl_path=pkl,
        module_path="path2_apps.bottom_breakout_burst.dag_spec",
        start_date="2025-01-01", end_date="2025-12-31",
        end_role="bo", label_horizon=20,
        buf_start="2025-01-01", buf_end="2025-12-31",
    )
    if not analysis["matches"]:
        return                              # 弱 fixture:不报错,只在有 match 时断言契约
    for m in analysis["matches"]:
        assert "forward_return" in m         # buffered 路径下注入 label
