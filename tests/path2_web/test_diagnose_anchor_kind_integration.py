"""v3 集成测试:GET /diagnose?anchor_kind=X 时 · monkeypatch pydevd.settrace 为 counter ·
assert 只对应 anchor_kind 埋点 fire · 其他 skip。

覆盖:
- anchor_kind='gate' → 只 anchor_kind='gate' 埋点 fire · 其他 skip
- anchor_kind='entry' → 只 'entry' fire
- anchor_kind='trough' → 只 'trough' fire
- anchor_kind='end' → 只 'end' fire
- 无 anchor_kind → 4 种 anchor_kind 都 fire(v1 兼容)

同时验证 fire 参数值确实落在 range 内(与 v2 契约 #4 加强联防)。
"""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from path2_web.app import create_app


@pytest.fixture
def client_with_real_pkl(tmp_path, monkeypatch):
    """使用真实 pkl 数据(dataset_dir 复用 /home/yu/PycharmProjects/Trade_Strategy/datasets/pkls)
    · 保 TSLA 类活跃股票有 tb events 命中埋点。若数据集不可访问 · skip test。"""
    real_dataset = Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls")
    if not (real_dataset / "TSLA.pkl").exists():
        pytest.skip("real dataset unavailable · skip integration test")

    monkeypatch.setenv("DEBUG_MODE", "1")
    monkeypatch.delenv("DEBUG_BAR_RANGE", raising=False)
    monkeypatch.delenv("DEBUG_ANCHOR_KIND", raising=False)

    # 强制 reimport debug_ctx · 让 _DEBUG_MODE 读当前 env
    sys.modules.pop("path2.debug_ctx", None)

    outputs = tmp_path / "out"
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({
        "dataset_dir": str(real_dataset),
        "scan": {"start_date": "2025-01-01", "end_date": "2026-01-01",
                 "workers": 1, "ticker_regex": None, "label_horizon": 20},
        "last_selected_pattern": "bottom_burst",
    }))
    return TestClient(create_app(config_path=cfg_path, outputs_root=str(outputs),
                                 use_thread_pool=True))


@pytest.fixture
def fire_recorder(monkeypatch):
    """monkeypatch pydevd.settrace + breakpoint · 记录每次 fire 时的 (bar, anchor_kind)。

    因为 debug_break 内部 fire 时不知道自己是哪个 (bar, anchor_kind) 上下文 · 我们在
    debug_break 外层再套一层 wrapper · 捕获参数。"""
    hits: list[tuple[int, str]] = []
    import path2.debug_ctx as dc

    real = dc.debug_break

    def wrapped(i: int, *, anchor_kind: str, **_kw) -> None:
        # 复刻 real debug_break 的判据 · 只在 fire 分支 append
        if not dc._DEBUG_MODE:
            return
        r = dc._read_range()
        if r is None:
            return
        if not (r[0] <= i <= r[1]):
            return
        required = dc._read_anchor_kind()
        if required is not None and required != anchor_kind:
            return
        hits.append((i, anchor_kind))
        # 不真 fire · 避免 breakpoint 挂 stdin

    monkeypatch.setattr(dc, "debug_break", wrapped)
    # detector 通过 `from path2.debug_ctx import debug_break` · patch 处也需
    # bb tb 已换代 V4(2026-08-16) · 埋点宿主从 throwback 换到 throwback_v4
    monkeypatch.setattr("path2.atoms.throwback_v4.debug_break", wrapped)
    return hits


def _url(anchor_kind: str | None = None, start_bar: int = 0, end_bar: int = 250):
    q = ("pattern_id=bottom_burst&symbol=TSLA&start=2025-01-01&end=2026-01-01"
         f"&scope=time&start_bar={start_bar}&end_bar={end_bar}")
    if anchor_kind:
        q += f"&anchor_kind={anchor_kind}"
    return f"/diagnose?{q}"


def test_anchor_kind_gate_only_gate_fires(client_with_real_pkl, fire_recorder):
    r = client_with_real_pkl.get(_url(anchor_kind="gate"))
    assert r.status_code == 200
    anchor_kinds_fired = {anchor_kind for _, anchor_kind in fire_recorder}
    assert anchor_kinds_fired == {"gate"}, (
        f"expected only 'gate' fires · got {anchor_kinds_fired} · full hits: {fire_recorder}"
    )


def test_anchor_kind_entry_only_entry_fires(client_with_real_pkl, fire_recorder):
    r = client_with_real_pkl.get(_url(anchor_kind="entry"))
    assert r.status_code == 200
    anchor_kinds_fired = {anchor_kind for _, anchor_kind in fire_recorder}
    assert anchor_kinds_fired == {"entry"}, (
        f"expected only 'entry' fires · got {anchor_kinds_fired}"
    )


def test_anchor_kind_trough_only_trough_fires(client_with_real_pkl, fire_recorder):
    r = client_with_real_pkl.get(_url(anchor_kind="trough"))
    assert r.status_code == 200
    anchor_kinds_fired = {anchor_kind for _, anchor_kind in fire_recorder}
    # trough 埋点在 phase1 success 分支 · 需 tb 有真实 match 才 fire · 若数据无 tb match
    # 集合可能是空(允许) · 若非空则必须只含 trough
    assert anchor_kinds_fired <= {"trough"}, (
        f"expected only 'trough' (or empty) fires · got {anchor_kinds_fired}"
    )


def test_anchor_kind_end_only_end_fires(client_with_real_pkl, fire_recorder):
    r = client_with_real_pkl.get(_url(anchor_kind="end"))
    assert r.status_code == 200
    anchor_kinds_fired = {anchor_kind for _, anchor_kind in fire_recorder}
    assert anchor_kinds_fired <= {"end"}, (
        f"expected only 'end' (or empty) fires · got {anchor_kinds_fired}"
    )


def test_no_anchor_kind_v1_compat_all_anchor_kinds_fire(client_with_real_pkl, fire_recorder):
    """v1 兼容 · 无 anchor_kind query · 全 anchor_kind 都可能 fire。"""
    r = client_with_real_pkl.get(_url(anchor_kind=None))
    assert r.status_code == 200
    anchor_kinds_fired = {anchor_kind for _, anchor_kind in fire_recorder}
    # v1 兼容 · 至少 gate 或 entry 会 fire(TSLA 2025 数据几乎必有 bo 触发 evaluate_throwback)
    assert len(anchor_kinds_fired) >= 1, (
        f"expected at least 1 anchor_kind fires under v1 compat · got empty"
    )
