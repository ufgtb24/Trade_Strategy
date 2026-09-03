"""v3 anchor_kind-gated debug 单元测试。

覆盖:
- 生产零成本(DEBUG_MODE 未设 → 立即 return · 不读 env · 不 import pydevd)
- v1 兼容 fallback(DEBUG_ANCHOR_KIND 未设或空串 → 全 anchor_kind fire)
- v3 anchor_kind 门限(DEBUG_ANCHOR_KIND 设 → 只匹配 anchor_kind fire · 其他 skip)
- required kwarg(缺 anchor_kind → TypeError)
- 三门形态无 class 维度(DEBUG_ANCHOR_KIND + bar 命中即 fire · spec 2026-08-14 §2.3)

用 monkeypatch stub pydevd.settrace 为计数器 · 避免真 pause。
"""
import importlib
import os
import sys
from typing import Optional

import pytest


@pytest.fixture
def fresh_debug_ctx(monkeypatch):
    """强制 reimport debug_ctx · 让 _DEBUG_MODE 读当前 env。返回 module。"""
    monkeypatch.setenv("DEBUG_MODE", "1")
    monkeypatch.delenv("DEBUG_BAR_RANGE", raising=False)
    monkeypatch.delenv("DEBUG_ANCHOR_KIND", raising=False)
    sys.modules.pop("path2.debug_ctx", None)
    import path2.debug_ctx as m
    return m


@pytest.fixture
def fire_counter(monkeypatch, fresh_debug_ctx):
    """stub pydevd.settrace 为计数器 · 记录每次 fire 时的 anchor_kind 上下文(靠 caller 传入)。
    ImportError fallback 用 stub breakpoint 也计数。"""
    hits: list[tuple[str, Optional[dict]]] = []
    # 注 sys.modules['pydevd'] · 让 debug_break 里 `import pydevd` 拿到 stub
    class StubPydevd:
        @staticmethod
        def settrace(**kwargs):
            hits.append(("settrace", kwargs))
    monkeypatch.setitem(sys.modules, "pydevd", StubPydevd)
    # 也 stub breakpoint · 万一 ImportError fallback 走到
    monkeypatch.setattr("builtins.breakpoint", lambda: hits.append(("breakpoint", None)))
    return hits


def test_debug_mode_unset_early_return(monkeypatch):
    """DEBUG_MODE 未设 → 立即 return · 即使 range/anchor_kind env 齐全也不 fire。"""
    monkeypatch.delenv("DEBUG_MODE", raising=False)
    monkeypatch.setenv("DEBUG_BAR_RANGE", "100,200")
    monkeypatch.setenv("DEBUG_ANCHOR_KIND", "gate")
    sys.modules.pop("path2.debug_ctx", None)
    import path2.debug_ctx as m
    # 无 pydevd stub · 若真 fire 会挂 stdin;此测试确认 _DEBUG_MODE=False 时不走 fire 路径
    m.debug_break(150, anchor_kind="gate")   # 不该 fire · 无异常即 pass


def test_no_range_no_fire(fresh_debug_ctx, fire_counter):
    """DEBUG_MODE=1 · 但 DEBUG_BAR_RANGE 未设 → 不 fire。"""
    fresh_debug_ctx.debug_break(150, anchor_kind="gate")
    assert fire_counter == []


def test_bar_out_of_range_no_fire(fresh_debug_ctx, fire_counter, monkeypatch):
    """bar 落 range 外 → 不 fire。"""
    monkeypatch.setenv("DEBUG_BAR_RANGE", "100,200")
    fresh_debug_ctx.debug_break(50, anchor_kind="gate")
    assert fire_counter == []


def test_v1_compat_no_anchor_kind_env_fires_any_anchor_kind(fresh_debug_ctx, fire_counter, monkeypatch):
    """DEBUG_ANCHOR_KIND 未设 → v1 兼容 · 任意 anchor_kind fire。"""
    monkeypatch.setenv("DEBUG_BAR_RANGE", "100,200")
    # DEBUG_ANCHOR_KIND 未设(fresh_debug_ctx fixture 已 delenv)
    fresh_debug_ctx.debug_break(150, anchor_kind="gate")
    fresh_debug_ctx.debug_break(150, anchor_kind="entry")
    fresh_debug_ctx.debug_break(150, anchor_kind="trough")
    fresh_debug_ctx.debug_break(150, anchor_kind="end")
    assert len(fire_counter) == 4


def test_v1_compat_empty_anchor_kind_env_fires_any_anchor_kind(fresh_debug_ctx, fire_counter, monkeypatch):
    """DEBUG_ANCHOR_KIND='' 空串 → v1 兼容 fallback · 任意 anchor_kind fire。"""
    monkeypatch.setenv("DEBUG_BAR_RANGE", "100,200")
    monkeypatch.setenv("DEBUG_ANCHOR_KIND", "")
    fresh_debug_ctx.debug_break(150, anchor_kind="gate")
    fresh_debug_ctx.debug_break(150, anchor_kind="entry")
    assert len(fire_counter) == 2


def test_anchor_kind_env_gate_only_gate_fires(fresh_debug_ctx, fire_counter, monkeypatch):
    """DEBUG_ANCHOR_KIND='gate' → 只 anchor_kind='gate' fire · 其他 skip。"""
    monkeypatch.setenv("DEBUG_BAR_RANGE", "100,200")
    monkeypatch.setenv("DEBUG_ANCHOR_KIND", "gate")
    fresh_debug_ctx.debug_break(150, anchor_kind="gate")   # fire
    fresh_debug_ctx.debug_break(150, anchor_kind="entry")  # skip
    fresh_debug_ctx.debug_break(150, anchor_kind="trough") # skip
    fresh_debug_ctx.debug_break(150, anchor_kind="end")    # skip
    assert len(fire_counter) == 1


def test_anchor_kind_env_end_matches_end_anchor_kind(fresh_debug_ctx, fire_counter, monkeypatch):
    """DEBUG_ANCHOR_KIND='end' → 只 anchor_kind='end' fire。"""
    monkeypatch.setenv("DEBUG_BAR_RANGE", "100,200")
    monkeypatch.setenv("DEBUG_ANCHOR_KIND", "end")
    fresh_debug_ctx.debug_break(150, anchor_kind="end")
    fresh_debug_ctx.debug_break(150, anchor_kind="gate")
    assert len(fire_counter) == 1


def test_anchor_kind_kwarg_required_typeerror(fresh_debug_ctx):
    """debug_break(i) 缺 anchor_kind kwarg → TypeError(required kwarg)。"""
    with pytest.raises(TypeError, match="anchor_kind"):
        fresh_debug_ctx.debug_break(150)   # type: ignore[call-arg]


def test_anchor_kind_positional_forbidden_typeerror(fresh_debug_ctx):
    """debug_break(i, anchor_kind) 位置传 anchor_kind → TypeError(keyword-only)。"""
    with pytest.raises(TypeError):
        fresh_debug_ctx.debug_break(150, "gate")   # type: ignore[misc]


# --- _read_range 纯解析覆盖(直接调用,独立于 debug_break 的 DEBUG_MODE/anchor_kind 网关逻辑)---

def test_read_range_unset_returns_none(fresh_debug_ctx):
    """DEBUG_BAR_RANGE 未设 → 直接返 None(fresh_debug_ctx 已 delenv,与空串区分)。"""
    assert fresh_debug_ctx._read_range() is None


def test_read_range_empty_string_returns_none(fresh_debug_ctx, monkeypatch):
    """DEBUG_BAR_RANGE='' 空串 → 走 `if not raw` 分支返 None(区别于未设,同一分支不同触发路径)。"""
    monkeypatch.setenv("DEBUG_BAR_RANGE", "")
    assert fresh_debug_ctx._read_range() is None


@pytest.mark.parametrize("raw", ["bogus", "1,2,3", "abc,def", "1,", ",", "10"])
def test_read_range_malformed_returns_none(fresh_debug_ctx, monkeypatch, raw):
    """畸形格式 → 走 except (ValueError, TypeError) 分支返 None。"""
    monkeypatch.setenv("DEBUG_BAR_RANGE", raw)
    assert fresh_debug_ctx._read_range() is None


def test_bar_at_lo_boundary_fires(fresh_debug_ctx, fire_counter, monkeypatch):
    """bar == lo(闭区间下界)→ fire · 验证比较是 <= 而非 <。"""
    monkeypatch.setenv("DEBUG_BAR_RANGE", "100,200")
    fresh_debug_ctx.debug_break(100, anchor_kind="gate")
    assert len(fire_counter) == 1


def test_bar_at_hi_boundary_fires(fresh_debug_ctx, fire_counter, monkeypatch):
    """bar == hi(闭区间上界)→ fire · 验证比较是 <= 而非 <。"""
    monkeypatch.setenv("DEBUG_BAR_RANGE", "100,200")
    fresh_debug_ctx.debug_break(200, anchor_kind="gate")
    assert len(fire_counter) == 1


# ── 三门形态正例(class 维度已删 · spec 2026-08-14 §2.3)──


def test_no_class_gate_anchor_and_bar_sufficient(fresh_debug_ctx, fire_counter, monkeypatch):
    """三门形态:DEBUG_ANCHOR_KIND + bar 命中即 fire,无任何 class 维度(spec 2026-08-14 §2.3)。"""
    monkeypatch.setenv("DEBUG_BAR_RANGE", "100,200")
    monkeypatch.setenv("DEBUG_ANCHOR_KIND", "gate")
    fresh_debug_ctx.debug_break(150, anchor_kind="gate")
    assert len(fire_counter) == 1
    fresh_debug_ctx.debug_break(150, anchor_kind="end")   # anchor_kind 不匹配 · 不 fire
    assert len(fire_counter) == 1


def test_debug_break_rejects_class_id_kwarg(fresh_debug_ctx, fire_counter, monkeypatch):
    """签名已删 class_id · 传 class_id kwarg → TypeError(防旧埋点悄悄回流)。"""
    monkeypatch.setenv("DEBUG_BAR_RANGE", "100,200")
    with pytest.raises(TypeError, match="class_id"):
        fresh_debug_ctx.debug_break(150, anchor_kind="gate", class_id="tb")   # type: ignore[call-arg]
    assert fire_counter == []
