"""serialize_per_pattern_result — 单股单 pattern 投影,加 max_forward_return。"""
from pathlib import Path
import pandas as pd
import pytest

from path2_web.serialize import serialize_per_pattern_result
from path2_apps.bottom_breakout_burst import build_pattern, Params, eval_meta
from path2.dag.engine import analyze as engine_analyze


PKL_DIR = Path("datasets/pkls")


def _pick_pkl_with_match() -> Path:
    """从 datasets/pkls 找一只 bbb 默认参数下能命中的股(若无,返 None,测试 skip)。"""
    if not PKL_DIR.exists():
        return None
    spec = build_pattern(Params.default())
    for p in sorted(PKL_DIR.glob("*.pkl"))[:200]:    # 限制扫描数避免慢
        df = pd.read_pickle(p)
        if len(df) < 200:
            continue
        win = df.iloc[-300:]
        res = engine_analyze(spec, win, Params.default())
        if len(res.matches) > 0:
            return p
    return None


def test_per_pattern_result_schema():
    """返回字典含 summary/analysis/max_forward_return 三键,分别是 dict/dict/float|None。"""
    p = _pick_pkl_with_match()
    if p is None:
        pytest.skip("no pkl with matches; skip")
    df = pd.read_pickle(p)
    spec = build_pattern(Params.default())
    win = df.iloc[-300:].reset_index()
    res = engine_analyze(spec, win, Params.default())
    meta = eval_meta()
    start_ts = pd.to_datetime(win["date"].iat[len(win) // 2])
    end_ts   = pd.to_datetime(win["date"].iat[-1])
    out = serialize_per_pattern_result(res, end_node=meta["end_node"],
                                       label_horizon=5, win=win,
                                       start_ts=start_ts, end_ts=end_ts)
    assert set(out.keys()) == {"summary", "analysis", "max_forward_return"}
    assert isinstance(out["summary"], dict)
    assert isinstance(out["analysis"], dict)
    assert out["max_forward_return"] is None or isinstance(out["max_forward_return"], float)


def test_per_pattern_events_full_set_kept():
    """events 全集照旧(不按窗过滤),matches 按窗过滤。"""
    p = _pick_pkl_with_match()
    if p is None:
        pytest.skip("no pkl with matches; skip")
    df = pd.read_pickle(p)
    spec = build_pattern(Params.default())
    win = df.iloc[-300:].reset_index()
    res = engine_analyze(spec, win, Params.default())
    meta = eval_meta()
    # 极窄过滤窗:只允许 win 末尾 5 bar 的 match
    start_ts = pd.to_datetime(win["date"].iat[-5])
    end_ts   = pd.to_datetime(win["date"].iat[-1])
    out = serialize_per_pattern_result(res, end_node=meta["end_node"],
                                       label_horizon=5, win=win,
                                       start_ts=start_ts, end_ts=end_ts)
    # events 全集与原 res.events 一致(数量)
    assert len(out["analysis"]["events"]) == len(res.events)
    # matches 是 res.matches 子集
    assert len(out["analysis"]["matches"]) <= len(res.matches)


def test_max_forward_return_null_when_matches_empty():
    """matches 过滤后空 → max_forward_return = None。"""
    p = _pick_pkl_with_match()
    if p is None:
        pytest.skip("no pkl with matches; skip")
    df = pd.read_pickle(p)
    spec = build_pattern(Params.default())
    win = df.iloc[-300:].reset_index()
    res = engine_analyze(spec, win, Params.default())
    meta = eval_meta()
    # 完全在 win 之外的过滤窗 → 0 match 入选
    start_ts = pd.to_datetime("1900-01-01")
    end_ts   = pd.to_datetime("1900-01-02")
    out = serialize_per_pattern_result(res, end_node=meta["end_node"],
                                       label_horizon=5, win=win,
                                       start_ts=start_ts, end_ts=end_ts)
    assert out["analysis"]["matches"] == []
    assert out["max_forward_return"] is None


def test_summary_matches_key_reflects_window():
    """summary['matches'] 是窗内 match 数(非全集)。"""
    p = _pick_pkl_with_match()
    if p is None:
        pytest.skip("no pkl with matches; skip")
    df = pd.read_pickle(p)
    spec = build_pattern(Params.default())
    win = df.iloc[-300:].reset_index()
    res = engine_analyze(spec, win, Params.default())
    meta = eval_meta()
    start_ts = pd.to_datetime("1900-01-01")
    end_ts   = pd.to_datetime("1900-01-02")
    out = serialize_per_pattern_result(res, end_node=meta["end_node"],
                                       label_horizon=5, win=win,
                                       start_ts=start_ts, end_ts=end_ts)
    assert out["summary"]["matches"] == 0
