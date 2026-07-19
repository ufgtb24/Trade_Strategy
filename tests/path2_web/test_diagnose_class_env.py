"""v4 handler class 门 env + finally 三 env pop 测试(mirror v3 test_diagnose_node_env.py)。

覆盖:
- event_class query 写 env DEBUG_EVENT_CLASS(非空)
- 无 event_class query · 不写 DEBUG_EVENT_CLASS env
- 空串 event_class · 不写 DEBUG_EVENT_CLASS env(handler 判据 `if event_class:`)
- finally 无条件 pop 三 env(DEBUG_BAR_RANGE + DEBUG_ANCHOR_KIND + DEBUG_EVENT_CLASS)
- 跨 request 隔离:上次 preset DEBUG_EVENT_CLASS · 本次不传 event_class · finally 依然 pop 兜底
"""
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from path2_web.app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    """带真实数据的 test client(复用 v3 test_diagnose_node_env.py 同构 fixture)。"""
    monkeypatch.delenv("DEBUG_BAR_RANGE", raising=False)
    monkeypatch.delenv("DEBUG_ANCHOR_KIND", raising=False)
    monkeypatch.delenv("DEBUG_EVENT_CLASS", raising=False)

    data = tmp_path / "data"
    data.mkdir()
    n = 300
    # 构造一段真实突破:前 200 bar 平盘 · 1 根峰值(idx200)· 10 bar 回踩平盘 · 1 根突破
    # (idx211)· 尾部平盘补满 n 根。mirror 已验证的 test_diagnose_anchor_kind_env.py::_make_ohlcv
    # 峰值→回踩→突破 结构——BODetector 要求"局部峰值先立住、后被击穿",单调 ramp(10→15 连续上冲)
    # 无局部峰值 · 不产生 BO(已用临时 probe 脚本验证:原 plan verbatim 单调 ramp 形态 bo=0 · debug_break
    # 从不触发 · 该 fixture 下游 3/5 test 恒 fail,与 handler 实现是否正确无关;现形态验证 bo=1,
    # start_idx=end_idx=211)。
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


def _diagnose_url(event_class: str | None = None, start_bar: int = 0, end_bar: int = 280):
    q = ("pattern_id=bottom_burst&symbol=AAA&start=2024-01-01&end=2024-10-01"
         f"&scope=time&start_bar={start_bar}&end_bar={end_bar}")
    if event_class is not None:
        q += f"&event_class={event_class}"
    return f"/diagnose?{q}"


def test_event_class_query_writes_debug_event_class_env(client, monkeypatch):
    """GET ?event_class=tb · handler try 期间 env DEBUG_EVENT_CLASS 写入。"""
    captured: list[str | None] = []
    import path2.debug_ctx as dc

    def spy(i, *, anchor_kind, class_id, **_kw):
        captured.append(os.environ.get("DEBUG_EVENT_CLASS"))
    monkeypatch.setattr(dc, "debug_break", spy)
    monkeypatch.setattr("path2.atoms.throwback.debug_break", spy)

    r = client.get(_diagnose_url(event_class="tb"))
    assert r.status_code == 200
    assert "tb" in captured, f"expected 'tb' in captured env values, got {captured}"


def test_no_event_class_query_does_not_write_debug_event_class_env(client, monkeypatch):
    """GET 不传 event_class · handler 不写 DEBUG_EVENT_CLASS env。"""
    captured: list[str | None] = []
    import path2.debug_ctx as dc

    def spy(i, *, anchor_kind, class_id, **_kw):
        captured.append(os.environ.get("DEBUG_EVENT_CLASS"))
    monkeypatch.setattr(dc, "debug_break", spy)
    monkeypatch.setattr("path2.atoms.throwback.debug_break", spy)

    r = client.get(_diagnose_url(event_class=None))
    assert r.status_code == 200
    assert len(captured) > 0, "spy never observed debug_break call · fixture broken"
    assert all(v is None for v in captured), (
        f"expected DEBUG_EVENT_CLASS unset for all captured, got {captured}"
    )


def test_empty_event_class_query_does_not_write_debug_event_class_env(client, monkeypatch):
    """GET ?event_class= 空串 · handler 判据 `if event_class:` · 不写 env。"""
    captured: list[str | None] = []
    import path2.debug_ctx as dc

    def spy(i, *, anchor_kind, class_id, **_kw):
        captured.append(os.environ.get("DEBUG_EVENT_CLASS"))
    monkeypatch.setattr(dc, "debug_break", spy)
    monkeypatch.setattr("path2.atoms.throwback.debug_break", spy)

    r = client.get(_diagnose_url(event_class=""))
    assert r.status_code == 200
    assert len(captured) > 0, "spy never observed debug_break call · fixture broken"
    assert all(v is None for v in captured), (
        f"expected DEBUG_EVENT_CLASS unset (empty event_class treated as unset), got {captured}"
    )


def test_finally_pops_all_three_envs_on_success(client):
    """handler 正常返回后 · 三 env 都 pop 清 · 无残留。"""
    r = client.get(_diagnose_url(event_class="tb"))
    assert r.status_code == 200
    assert os.environ.get("DEBUG_BAR_RANGE") is None
    assert os.environ.get("DEBUG_ANCHOR_KIND") is None
    assert os.environ.get("DEBUG_EVENT_CLASS") is None


def test_finally_pops_debug_event_class_env_bootstrap_pollution(client, monkeypatch):
    """跨 request 隔离:preset DEBUG_EVENT_CLASS='stale' · 本次不传 event_class · finally 依然 pop 兜底
    (无条件 pop DEBUG_EVENT_CLASS · 不管本次是否写过)。"""
    monkeypatch.setenv("DEBUG_EVENT_CLASS", "stale")
    r = client.get(_diagnose_url(event_class=None))
    assert r.status_code == 200
    assert os.environ.get("DEBUG_EVENT_CLASS") is None, (
        "handler finally should pop DEBUG_EVENT_CLASS unconditionally to prevent "
        "cross-request pollution"
    )
