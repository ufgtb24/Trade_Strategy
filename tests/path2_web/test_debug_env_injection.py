"""/diagnose handler:partial-bar-params 分支 · env 不写入。

历史:v1 (spec 2026-07-14-path2-web-debug-breakpoints) 的
`test_time_scope_sets_debug_bar_range` / `test_overall_diag_does_not_touch_env`
/ `test_time_scope_overwrites_previous_range` 断言 handler 写入 env 后**不清**、
overall diag 保留上次 range;此假设被 v2 (spec 2026-07-15-path2-web-event-debug-multi-anchor)
契约 #7 明确推翻(handler `try/finally` 结束必 pop),此三项已迁至
`tests/path2_web/test_diagnose_finally_pop.py` 作 v2 语义覆盖。

本文件仅保留与 v2 兼容的 partial-bar 分支断言:start_bar 或 end_bar 单一 → 不写 env。
"""
import json
import os
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from path2_web.app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("DEBUG_BAR_RANGE", raising=False)   # 每 test 起点无残留

    data = tmp_path / "data"
    data.mkdir()
    n = 200
    pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n),
        "open": [10.0] * n, "high": [11.0] * n, "low": [9.0] * n,
        "close": [10.5] * n, "volume": [100.0] * n,
    }).to_pickle(data / "AAA.pkl")

    outputs = tmp_path / "out"
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({
        "dataset_dir": str(data),
        "scan": {"start_date": "2024-01-01", "end_date": "2024-07-01",
                 "workers": 1, "ticker_regex": None, "label_horizon": 20},
        "last_selected_pattern": "bo_only",
    }))
    return TestClient(create_app(config_path=cfg_path, outputs_root=str(outputs),
                                  use_thread_pool=True))


def test_partial_bar_params_do_not_set_env(client, monkeypatch):
    """只有 start_bar 或只有 end_bar → env 不写(需两者都非 None)。"""
    monkeypatch.delenv("DEBUG_BAR_RANGE", raising=False)

    r = client.get("/diagnose", params={
        "pattern_id": "bo_only", "symbol": "AAA",
        "start": "2024-01-01", "end": "2024-07-01",
        "scope": "time", "start_bar": 50,   # end_bar 缺
    })
    # scope=time 但 end_bar 缺可能被 handler 视为不完整 · env 应保持未设
    assert os.environ.get("DEBUG_BAR_RANGE") is None


def test_partial_bar_params_start_missing_do_not_set_env(client, monkeypatch):
    """只有 end_bar(start_bar 缺)→ env 不写。对称补齐 end_bar 缺的 case。"""
    monkeypatch.delenv("DEBUG_BAR_RANGE", raising=False)

    r = client.get("/diagnose", params={
        "pattern_id": "bo_only", "symbol": "AAA",
        "start": "2024-01-01", "end": "2024-07-01",
        "scope": "time", "end_bar": 80,   # start_bar 缺
    })
    assert os.environ.get("DEBUG_BAR_RANGE") is None
