"""bo_only pattern 烟雾测试 — 单节点 dag 能扫小数据集出 bo events 与 matches。"""
import pandas as pd

from path2_apps.bo_only import (
    PATTERN_DAG, build_pattern, analyze, matches, eval_meta, Params, load_params,
)


def test_pattern_dag_bo_and_pk_nodes_no_edges():
    """PATTERN_DAG 是 bo + pk 两节点(共享同一 detector)+ 零边。"""
    spec = PATTERN_DAG
    assert spec.pattern_id == "bo_only"
    assert [n.node_id for n in spec.nodes] == ["bo", "pk"]
    assert spec.nodes[0].detector is spec.nodes[1].detector   # 兄弟机制:一次 detect 填满两流
    assert spec.nodes[1].solve is False   # pk 孤立显示 node
    assert spec.edges == ()


def test_build_pattern_returns_consistent_spec():
    """build_pattern 与 PATTERN_DAG 同结构(模块级常量 = build_pattern(default))。"""
    spec = build_pattern(Params.default())
    assert spec.pattern_id == "bo_only"
    assert [n.node_id for n in spec.nodes] == ["bo", "pk"]


def test_eval_meta_protocol():
    """eval_meta 协议:end_node=bo, head_buffer=max(vol_baseline_period, total_window)."""
    meta = eval_meta()
    assert meta["end_node"] == "bo"
    p = Params.default()
    assert meta["head_buffer_trading_days"] == max(p.bo.vol_baseline_period, p.bo.total_window)


def test_load_params_uses_yaml(tmp_path, monkeypatch):
    """load_params 从同目录 params.yaml 读 — 实测 default 值与 yaml 一致。"""
    p = load_params()
    # yaml 内 bo.total_window=20(从我们写的 yaml 推),非 BoParams 默认 10
    assert p.bo.total_window == 20


def test_analyze_runs_without_error_on_synthetic_df():
    """analyze 能在合成 df 上跑完不抛(无论是否检出 events)。"""
    n = 100
    df = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n),
        "open":  [10.0] * n, "high": [11.0] * n,
        "low":   [9.0]  * n, "close":[10.5] * n,
        "volume":[100.0]* n,
    })
    res = analyze(df)
    assert hasattr(res, "events") and hasattr(res, "matches")


def test_matches_bool_wrapper():
    """matches() 是 analyze().matches 非空的 bool。"""
    n = 50
    df = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n),
        "open":  [10.0] * n, "high": [10.5] * n,
        "low":   [9.5]  * n, "close":[10.0] * n,
        "volume":[100.0]* n,
    })
    assert isinstance(matches(df), bool)
