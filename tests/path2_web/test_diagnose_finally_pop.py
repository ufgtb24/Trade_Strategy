"""Task 1 · /diagnose handler 加 try/finally,finally 中 pop DEBUG_BAR_RANGE(v2 契约 #7)。

v2 触发频率 3× v1,每 request 结束必清 env,防跨 request 污染(overall diag / scan pool 挂死)。
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from path2_web.main import make_app


@pytest.fixture
def client():
    # 保证 env clean(其他 test 可能残留)
    os.environ.pop("DEBUG_BAR_RANGE", None)
    app = make_app()
    yield TestClient(app)
    os.environ.pop("DEBUG_BAR_RANGE", None)


def _pick_symbol_and_pattern(client):
    """从 /patterns 拿一个真实 pattern_id · 从 dataset_dir 拿一个真实 symbol。"""
    r = client.get("/patterns")
    assert r.status_code == 200, f"/patterns fail: {r.text}"
    patterns = r.json()
    assert patterns, "no patterns registered"
    pid = patterns[0]["pattern_id"]

    cfg_r = client.get("/config")
    assert cfg_r.status_code == 200
    cfg = cfg_r.json()
    from pathlib import Path
    pkls = list(Path(cfg["dataset_dir"]).glob("*.pkl"))
    if not pkls:
        pytest.skip(f"no pkls in {cfg['dataset_dir']} — integration test skipped")
    return pid, pkls[0].stem


def test_diagnose_finally_pops_debug_bar_range_on_success(client):
    """/diagnose 正常 return 后 DEBUG_BAR_RANGE 必须被 pop。"""
    pid, sym = _pick_symbol_and_pattern(client)
    # 用一个 legacy scope=None + start_bar=None → 不写 env(base case)
    r = client.get(f"/diagnose?pattern_id={pid}&symbol={sym}&start=2025-01-01&end=2025-12-31")
    assert r.status_code == 200, f"got {r.status_code}: {r.text[:200]}"
    # 手动预置 env 后请求含 start_bar/end_bar 的 diag,应命中 finally pop
    os.environ["DEBUG_BAR_RANGE"] = "999,999"  # 预置残留
    r = client.get(
        f"/diagnose?pattern_id={pid}&symbol={sym}&start=2025-01-01&end=2025-12-31"
        f"&scope=time&start_bar=50&end_bar=60"
    )
    assert r.status_code == 200
    assert "DEBUG_BAR_RANGE" not in os.environ, "env not popped after success"


def test_diagnose_finally_pops_debug_bar_range_on_exception(client):
    """/diagnose 抛异常时 DEBUG_BAR_RANGE 仍必须被 pop(try/finally 关键点)。"""
    # 用不存在的 pattern_id 触发 404
    os.environ["DEBUG_BAR_RANGE"] = "888,888"
    r = client.get(
        f"/diagnose?pattern_id=NON_EXISTENT_PATTERN&symbol=any&start=2025-01-01&end=2025-12-31"
        f"&scope=time&start_bar=50&end_bar=60"
    )
    assert r.status_code == 404
    assert "DEBUG_BAR_RANGE" not in os.environ, "env not popped after exception"
