"""throwback._emit_tb_gate 的 debug_break 埋点验证:
- 位置正确性:on_gate=None 时早退,debug_break 不被调用(local invariant,非 scan 分野)
- 参数正确性:on_gate 非 None 时 debug_break 收到 gate_idx
- 真实 scan 的 bypass 靠 _DEBUG_MODE=False 常量,详见 test_emit_tb_gate_skips_debug_break_on_scan_path
"""
from path2.atoms import throwback
from path2.dag.gate_failure import MeasuredKindAware


def _make_measured():
    return MeasuredKindAware(kind='count', value=0.0, label='x')


def test_emit_tb_gate_triggers_debug_break_on_diagnose_path(monkeypatch):
    """on_gate 非 None(diagnose)→ debug_break 被调用,参数 = gate_idx。"""
    calls = []
    monkeypatch.setattr("path2.atoms.throwback.debug_break", lambda i, *, anchor_kind, class_id, **_kw: calls.append(i))

    collected = []
    throwback._emit_tb_gate(
        bo_idx=100, gate_idx=250, gate_name='phase1_break',
        measured=_make_measured(), threshold=0.0, atr_window=14,
        on_gate=lambda gf: collected.append(gf),
    )

    assert calls == [250], "debug_break should be called with gate_idx (not bo_idx)"
    assert len(collected) == 1, "on_gate should still be called (existing behavior preserved)"


def test_emit_tb_gate_skips_debug_break_on_scan_path(monkeypatch):
    """on_gate=None → 早退分支;此断言验证 local invariant。真实 scan attach 了非 None on_gate,scan 真正的 bypass 靠 _DEBUG_MODE=False。"""
    calls = []
    monkeypatch.setattr("path2.atoms.throwback.debug_break", lambda i, *, anchor_kind, class_id, **_kw: calls.append(i))

    throwback._emit_tb_gate(
        bo_idx=100, gate_idx=250, gate_name='phase1_break',
        measured=_make_measured(), threshold=0.0, atr_window=14,
        on_gate=None,
    )

    assert calls == [], "scan path (on_gate=None) must not touch debug_break"
