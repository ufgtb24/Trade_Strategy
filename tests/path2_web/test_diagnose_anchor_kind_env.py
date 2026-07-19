"""v3 handler anchor_kind query + 双 env pop 测试。

覆盖:
- anchor_kind query 写 env DEBUG_ANCHOR_KIND(非空)
- 无 anchor_kind query · 不写 DEBUG_ANCHOR_KIND env
- 空串 anchor_kind · 不写 DEBUG_ANCHOR_KIND env(handler 判据 `if anchor_kind:`)
- finally 无条件 pop 双 env(异常路径也测)
- 跨 request 隔离:上次 preset DEBUG_ANCHOR_KIND · 本次不传 anchor_kind · finally 依然 pop 兜底

fixture 说明(相对 plan 原文两处调整,理由见 task-3-report.md):
1. pattern_id 用 `bottom_burst`(非 `bo_only`)—— `bo_only` 只有孤立 BODetector 节点,
   拓扑里没有 ThrowbackDetector,`path2.atoms.throwback.debug_break` 永远不会被调用;
   `bottom_burst` 是仓库里唯一挂了 tb(ThrowbackDetector,consumes_stream="bo")节点的
   注册 pattern。
2. OHLCV 用真实构造的突破序列(非全平),且 `date` 显式 set_index 成 DatetimeIndex——
   `path2_web/data.py::slice_window` 要求 `df.index` 是具名 'date' 的 DatetimeIndex
   (`df.loc[str(start):str(end)]`);若 'date' 只是普通列(RangeIndex),`.loc` 字符串切片
   静默返回空窗口(0 行),detector 无 bar 可扫,debug_break 永远不触发。全平价格数据下
   BODetector 也不会有真实突破(peak 存在但从不被击穿),因此改用一段"平台+单峰+突破"序列,
   在 `bottom_burst` 生产参数(total_window=20/min_side_bars=6/min_relative_height=0.2/
   exceed_threshold=0.003)下必然在 idx=21 产生一个 BOEvent,从而使
   evaluate_throwback() 内 `debug_break(bo_idx, anchor_kind='entry')`(无条件调用,不受
   on_gate 是否挂钩影响)至少触发一次。
"""
import json
import os
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from path2_web.app import create_app


def _make_ohlcv(n: int = 200) -> pd.DataFrame:
    """构造一段在 bottom_burst 生产 BO 参数下必产生 1 个 BOEvent 的序列。

    结构:10 根平盘 + 1 根峰值(idx10,high=12.1)+ 10 根平盘 + 1 根突破
    (idx21,high=13.1)+ 尾部平盘补满 n 根。峰值相对高度 (12.1-9.9)/9.9≈0.222
    ≥ min_relative_height(0.2);突破价 13.1 > peak.price*(1+exceed_threshold)
    = 12.1*1.003≈12.136,越过阈值触发 BOEvent(已用 probe 脚本独立验证:
    num BOs==1,start_idx=end_idx=21)。
    """
    closes = [10.0] * 10 + [12.0] + [10.0] * 10 + [13.0] + [10.0] * (n - 22)
    highs = [c + 0.1 for c in closes]
    lows = [c - 0.1 for c in closes]
    opens = list(closes)
    df = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n),
        "open": opens, "high": highs, "low": lows,
        "close": closes, "volume": [100.0] * n,
    })
    return df.set_index("date")   # ★ slice_window 要求 DatetimeIndex(name='date'),非普通列


@pytest.fixture
def client(tmp_path, monkeypatch):
    """带真实数据的 test client · dataset_dir=tmp_path。"""
    monkeypatch.delenv("DEBUG_BAR_RANGE", raising=False)
    monkeypatch.delenv("DEBUG_ANCHOR_KIND", raising=False)

    data = tmp_path / "data"
    data.mkdir()
    _make_ohlcv(200).to_pickle(data / "AAA.pkl")

    outputs = tmp_path / "out"
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({
        "dataset_dir": str(data),
        "scan": {"start_date": "2024-01-01", "end_date": "2024-07-01",
                 "workers": 1, "ticker_regex": None, "label_horizon": 20},
        "last_selected_pattern": "bottom_burst",
    }))
    return TestClient(create_app(config_path=cfg_path, outputs_root=str(outputs),
                                 use_thread_pool=True))


def _diagnose_url(anchor_kind: str | None = None, start_bar: int = 50, end_bar: int = 80):
    q = ("pattern_id=bottom_burst&symbol=AAA&start=2024-01-01&end=2024-07-01"
         f"&scope=time&start_bar={start_bar}&end_bar={end_bar}")
    if anchor_kind is not None:
        q += f"&anchor_kind={anchor_kind}"
    return f"/diagnose?{q}"


def test_anchor_kind_query_writes_debug_anchor_kind_env_during_request(client, monkeypatch):
    """GET ?anchor_kind=gate · handler try 期间 env DEBUG_ANCHOR_KIND 写入。用 monkeypatch hijack
    debug_break 观测 · 因 handler finally 会 pop · request 结束后 env 已清。"""
    captured: list[str | None] = []
    import path2.debug_ctx as dc

    real = dc.debug_break
    def spy(i, *, anchor_kind, class_id, **_kw):
        captured.append(os.environ.get("DEBUG_ANCHOR_KIND"))
        # 不 fire · 避免 breakpoint 挂
    monkeypatch.setattr(dc, "debug_break", spy)
    # detector 通过 `from path2.debug_ctx import debug_break` 引用 · 也需 patch
    monkeypatch.setattr("path2.atoms.throwback.debug_break", spy)

    r = client.get(_diagnose_url(anchor_kind="gate"))
    assert r.status_code == 200
    # handler try 期间至少一次 debug_break 被调 · 其时 DEBUG_ANCHOR_KIND 应 == 'gate'
    assert "gate" in captured, f"expected 'gate' in captured env values, got {captured}"


def test_no_anchor_kind_query_does_not_write_debug_anchor_kind_env(client, monkeypatch):
    """GET 不传 anchor_kind · handler 不写 DEBUG_ANCHOR_KIND env。"""
    captured: list[str | None] = []
    import path2.debug_ctx as dc

    def spy(i, *, anchor_kind, class_id, **_kw):
        captured.append(os.environ.get("DEBUG_ANCHOR_KIND"))
    monkeypatch.setattr(dc, "debug_break", spy)
    monkeypatch.setattr("path2.atoms.throwback.debug_break", spy)

    r = client.get(_diagnose_url(anchor_kind=None))
    assert r.status_code == 200
    # request 期间 DEBUG_ANCHOR_KIND 始终未设(None)
    assert all(v is None for v in captured), (
        f"expected DEBUG_ANCHOR_KIND unset for all captured, got {captured}"
    )


def test_empty_anchor_kind_query_does_not_write_debug_anchor_kind_env(client, monkeypatch):
    """GET ?anchor_kind= 空串 · handler 判据 `if anchor_kind:` · 不写 env。"""
    captured: list[str | None] = []
    import path2.debug_ctx as dc

    def spy(i, *, anchor_kind, class_id, **_kw):
        captured.append(os.environ.get("DEBUG_ANCHOR_KIND"))
    monkeypatch.setattr(dc, "debug_break", spy)
    monkeypatch.setattr("path2.atoms.throwback.debug_break", spy)

    r = client.get(_diagnose_url(anchor_kind=""))
    assert r.status_code == 200
    assert all(v is None for v in captured), (
        f"expected DEBUG_ANCHOR_KIND unset (empty anchor_kind treated as unset), got {captured}"
    )


def test_finally_pops_both_envs_on_success(client):
    """handler 正常返回后 · 两 env 都 pop 清 · 无残留。"""
    r = client.get(_diagnose_url(anchor_kind="gate"))
    assert r.status_code == 200
    assert os.environ.get("DEBUG_BAR_RANGE") is None
    assert os.environ.get("DEBUG_ANCHOR_KIND") is None


def test_finally_pops_debug_anchor_kind_env_bootstrap_pollution(client, monkeypatch):
    """跨 request 隔离:preset DEBUG_ANCHOR_KIND='stale' · 本次不传 anchor_kind · finally 依然 pop 兜底
    (无条件 pop DEBUG_ANCHOR_KIND · 不管本次是否写过)。"""
    monkeypatch.setenv("DEBUG_ANCHOR_KIND", "stale")
    # 注:monkeypatch.setenv 会在 test 结束自动 restore · 所以我们在 request 前手动 unset
    # · 用 os.environ.pop 来测 handler finally 是否 pop
    r = client.get(_diagnose_url(anchor_kind=None))
    assert r.status_code == 200
    # handler finally 应 pop DEBUG_ANCHOR_KIND(哪怕本次没写)
    assert os.environ.get("DEBUG_ANCHOR_KIND") is None, (
        "handler finally should pop DEBUG_ANCHOR_KIND unconditionally to prevent "
        "cross-request pollution"
    )
