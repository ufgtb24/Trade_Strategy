"""serialize_per_pattern_result — 单股单 pattern 投影,加 max_forward_return / min_forward_drawdown。"""
from pathlib import Path
import pandas as pd
import pytest

from path2_web.serialize import serialize_per_pattern_result
from path2_apps.bottom_breakout_burst import build_pattern, Params, eval_meta
from path2_apps.bottom_breakout_burst.dag_spec import analyze as dag_analyze
from path2.dag.engine import analyze as engine_analyze
from tests.path2.fixtures.positive_case import positive_case


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
    """返回字典含 summary/analysis/max_forward_return/min_forward_drawdown/match_fp_counts 五键。"""
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
    assert set(out.keys()) == {"summary", "analysis", "max_forward_return", "min_forward_drawdown", "match_fp_counts"}
    assert isinstance(out["summary"], dict)
    assert isinstance(out["analysis"], dict)
    assert out["max_forward_return"] is None or isinstance(out["max_forward_return"], float)
    assert out["min_forward_drawdown"] is None or isinstance(out["min_forward_drawdown"], float)
    assert isinstance(out["match_fp_counts"], dict)


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
    assert out["min_forward_drawdown"] is None


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


# ---------------------------------------------------------------------------
# min_low(mfr 下行镜像)注入 + 聚合 —— 用合成 positive_case 驱动(不依赖 datasets/pkls)。
# ---------------------------------------------------------------------------

def _synth_win_with_date():
    """复用合成 positive case,补 date 列(serialize_per_pattern_result 读 win['date'])。"""
    df, params = positive_case()
    df = df.copy()
    df["date"] = pd.date_range("2020-01-01", periods=len(df), freq="D")
    spec = build_pattern(params)
    res = dag_analyze(df, params)
    assert len(res.matches) >= 1, "合成 positive case 应至少 1 命中"
    return df, res, params


def test_forward_drawdown_injected_and_min_aggregated():
    """每条 match 注入 forward_drawdown(与 forward_return 并列);
    min_forward_drawdown = min(非 None)(与 max_forward_return 的 max 对仗)。
    单 match → min = 该 match 的 forward_drawdown,且与 mfr 一同算出。"""
    win, res, _ = _synth_win_with_date()
    meta = eval_meta()
    start_ts = win["date"].iat[0]
    end_ts = win["date"].iat[-1]
    out = serialize_per_pattern_result(res, end_node=meta["end_node"],
                                       label_horizon=5, win=win,
                                       start_ts=start_ts, end_ts=end_ts)
    matches = out["analysis"]["matches"]
    assert matches, "窗内应有 match"
    md = matches[0]
    # per-match:两 label 并列注入
    assert "forward_return" in md and "forward_drawdown" in md
    assert md["forward_return"] is not None and md["forward_drawdown"] is not None
    # 结构不变量:同买点窗 max(high) ≥ min(low) ⟹ forward_return ≥ forward_drawdown
    # (drawdown 可正可负:正=无下行波动、负=有回撤;符号取决于走势,不强制)
    assert md["forward_return"] >= md["forward_drawdown"]
    # 单 match:min_forward_drawdown == 该 match 的 forward_drawdown
    assert out["min_forward_drawdown"] == md["forward_drawdown"]
    # max_forward_return 同时仍正确(未被 drawdown 改动影响)
    assert out["max_forward_return"] == md["forward_return"]


def test_min_forward_drawdown_is_min_across_matches():
    """min_forward_drawdown 取所有非 None drawdown 的 min(最差下行),
    与单 match 的 forward_drawdown 是同一字段名(serialize/scan 收集口径一致)。"""
    from path2_web.eval_runner import _summarize_flat
    win, res, _ = _synth_win_with_date()
    meta = eval_meta()
    out = serialize_per_pattern_result(res, end_node=meta["end_node"],
                                       label_horizon=5, win=win,
                                       start_ts=win["date"].iat[0],
                                       end_ts=win["date"].iat[-1])
    dds = [m["forward_drawdown"] for m in out["analysis"]["matches"]
           if m["forward_drawdown"] is not None]
    expected = min(dds) if dds else None
    assert out["min_forward_drawdown"] == expected
    # 收集字段名 = forward_drawdown(供 scan.py 全宇宙聚合对齐)
    assert all("forward_drawdown" in m for m in out["analysis"]["matches"])


# ---------------------------------------------------------------------------
# 首次穿越方向(集合级四态计数;enabled 开关 + 几何对称 k 参数) —— 合成 positive_case 驱动。
# ---------------------------------------------------------------------------


def test_first_passage_disabled_omits_key():
    """enabled=False → MatchDict 不含 first_passage 键(向后兼容)。"""
    win, res, _ = _synth_win_with_date()
    meta = eval_meta()
    out = serialize_per_pattern_result(
        res, end_node=meta["end_node"], label_horizon=5, win=win,
        start_ts=win["date"].iat[0], end_ts=win["date"].iat[-1],
        first_passage_enabled=False)
    assert out["analysis"]["matches"], "窗内应有 match"
    for m in out["analysis"]["matches"]:
        assert "first_passage" not in m


def test_match_fp_counts_single_group():
    """out["match_fp_counts"] 单组 {up,down,both,none}(不再按 pair_key 分);
    至少计 1 买点日;k 参数透传到 match_first_passage(几何对称阈值)。"""
    win, res, _ = _synth_win_with_date()
    meta = eval_meta()
    out = serialize_per_pattern_result(
        res, end_node=meta["end_node"], label_horizon=5, win=win,
        start_ts=win["date"].iat[0], end_ts=win["date"].iat[-1], first_passage_k=2.0)
    matches = out["analysis"]["matches"]
    assert matches, "窗内应有 match"
    complete = [m for m in matches if m["forward_return"] is not None]
    assert complete, "应至少 1 条窗口完整的 match"
    # match 自身不再注入 first_passage 字段
    for m in complete:
        assert "first_passage" not in m
    # match_fp_counts 单组四态、至少计了 1 个买点日
    fp = out["match_fp_counts"]
    assert set(fp) == {"up", "down", "both", "none"}
    assert sum(fp.values()) > 0
