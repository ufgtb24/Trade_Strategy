"""契约测试:handler 按 scope 分派 detector pass · 每 scope 请求下 `_dag_diagnose` 与
`_dag_analyze_engine` 各被调 0 或 1 次(总数 = 1 · 消双 pause bug)。

A' 修法(见 docs/research/2026-07-18_debug-double-pause-analysis/final_report.md §3.1):
- scope=nodes → 只调 _dag_diagnose(diag=1, analyze=0)
- scope=time  → 只调 _dag_analyze_engine + attach_and_collect(diag=0, analyze=1)
- scope=pair  → 同 scope=time(diag=0, analyze=1)
- scope=None(legacy) → 走 diagnose_symbol · 与本文件断言无关(保留字节等价)

Spy 挂在 `path2_web.api` 模块的两个 import 别名上(handler 里通过别名调) · 计数后
delegate 到真实实现(保 handler 后续 attach_and_collect / derive_response 路径可跑通)。

Fixture 复用 test_diagnose_anchor_kind_env.py 已验证的 peak→pullback→breakout 形态
(BODetector 有 1 个 BO event · tb detector 会 evaluate · debug_break 会 fire)。
"""
import json
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import path2_web.api as api_mod
from path2_web.app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    """带真实数据的 test client(复用 test_diagnose_anchor_kind_env.py 同构 fixture)。"""
    monkeypatch.delenv("DEBUG_BAR_RANGE", raising=False)
    monkeypatch.delenv("DEBUG_ANCHOR_KIND", raising=False)

    data = tmp_path / "data"
    data.mkdir()
    n = 300
    # peak→pullback→breakout 形态(见 test_diagnose_anchor_kind_env.py::_make_ohlcv 注释)
    dates = pd.date_range("2024-01-01", periods=n)
    close = np.concatenate([
        np.full(200, 10.0),
        np.array([12.0]),
        np.full(10, 10.0),
        np.array([13.0]),
        np.full(n - 212, 10.0),
    ])
    df = pd.DataFrame({
        "date": dates, "open": close, "high": close + 0.5,
        "low": close - 0.5, "close": close, "volume": [100.0] * n,
    }).set_index("date")
    df.to_pickle(data / "AAA.pkl")

    outputs = tmp_path / "out"
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({
        "dataset_dir": str(data),
        "scan": {"start_date": "2024-01-01", "end_date": "2024-10-01",
                 "workers": 1, "ticker_regex": None, "label_horizon": 20},
        "last_selected_pattern": "bottom_burst",
    }))
    return TestClient(create_app(config_path=cfg_path, outputs_root=str(outputs),
                                 use_thread_pool=True))


@pytest.fixture
def spy_passes(monkeypatch):
    """Spy on _dag_diagnose / _dag_analyze_engine · 计数后 delegate。返回 {'diag': int, 'analyze': int}。"""
    counts = {"diag": 0, "analyze": 0}
    orig_diag = api_mod._dag_diagnose
    orig_analyze = api_mod._dag_analyze_engine

    def spy_diag(*a, **kw):
        counts["diag"] += 1
        return orig_diag(*a, **kw)

    def spy_analyze(*a, **kw):
        counts["analyze"] += 1
        return orig_analyze(*a, **kw)

    monkeypatch.setattr(api_mod, "_dag_diagnose", spy_diag)
    monkeypatch.setattr(api_mod, "_dag_analyze_engine", spy_analyze)
    return counts


def test_scope_nodes_only_calls_diagnose_pass(client, spy_passes):
    """scope=nodes 请求下 · 只 _dag_diagnose · 不 _dag_analyze_engine(消 analyze pass 冗余)。"""
    r = client.get(
        "/diagnose?pattern_id=bottom_burst&symbol=AAA"
        "&start=2024-01-01&end=2024-10-01"
        "&scope=nodes&src_node=bo&dst_node=tb"
    )
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text}"
    assert spy_passes == {"diag": 1, "analyze": 0}, (
        f"scope=nodes 应只跑 diagnose pass · got {spy_passes}"
    )


def test_scope_time_only_calls_analyze_pass(client, spy_passes):
    """scope=time 请求下 · 只 _dag_analyze_engine · 不 _dag_diagnose(消 diagnose pass 冗余)。"""
    r = client.get(
        "/diagnose?pattern_id=bottom_burst&symbol=AAA"
        "&start=2024-01-01&end=2024-10-01"
        "&scope=time&start_bar=0&end_bar=280"
    )
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text}"
    assert spy_passes == {"diag": 0, "analyze": 1}, (
        f"scope=time 应只跑 analyze pass · got {spy_passes}"
    )


def test_scope_pair_only_calls_analyze_pass(client, spy_passes):
    """scope=pair 请求下 · 只 _dag_analyze_engine · 不 _dag_diagnose(消 diagnose pass 冗余)。

    src/dst_event_id 用未存在的 dummy id · derive_response 会返 invalid_reason='event_not_found'
    · 但 detector 已经跑过 · 计数依然正确。断言 status_code ∈ {200, 400}(不同 event id 不存在时
    不同分支 · 都算 handler 正常返回)。"""
    r = client.get(
        "/diagnose?pattern_id=bottom_burst&symbol=AAA"
        "&start=2024-01-01&end=2024-10-01"
        "&scope=pair&src_event_id=dummy_src&dst_event_id=dummy_dst"
    )
    assert r.status_code in (200, 400), f"unexpected status {r.status_code}: {r.text}"
    assert spy_passes == {"diag": 0, "analyze": 1}, (
        f"scope=pair 应只跑 analyze pass · got {spy_passes}"
    )
