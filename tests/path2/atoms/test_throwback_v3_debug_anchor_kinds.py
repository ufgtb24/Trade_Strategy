"""throwback_v3 debug 契约锚测试(容器模式:tb_v3 容器 + tb_seg_v3 段)。

用 ast 静态解析,不运行 detector,不依赖 fixture。

契约(V2 容器模式先例,V3 多段 re-entry 版):
- throwback_v3.py 全模块(含 _emit_tb_gate_v3 helper 内部)必有且只有 8 处 debug_break call:
  容器 tb_v3:entry×1(detect per-bo 入口)+ gate×1(_emit_tb_gate_v3 内部,on_gate 包装)
  段 tb_seg_v3:confirm×1(企稳确认根/开段)+ end×5(phase2_break 截断 / weak / rise /
  timeout / 收尾强制闭合)。注意:end×5 而非 end×4 —— L94/114/122/130/175 五处均为
  end 语义,与「总数 8」自洽(1+1+1+5=8;end×4 则总数 7 对不上)。
- 每处必须传 anchor_kind kwarg;anchor_kind 是 str literal(class 维度已删 · spec 2026-08-14 §2.3)
- anchor_kind 分布 Counter 严格等于 baseline

不依赖精确 lineno · 抗 throwback_v3.py 上下加行漂移。
"""
import ast
import pathlib
from collections import Counter

import path2.atoms.throwback_v3 as throwback_v3
from path2.dag.gate_failure import MeasuredKindAware


THROWBACK_V3_PATH = pathlib.Path(__file__).resolve().parents[3] / "path2" / "atoms" / "throwback_v3.py"
EXPECTED_ANCHOR_COUNTER = Counter({
    "gate":    1,   # on_gate 包装(_emit_tb_gate_v3 内部,debug_break 收 gate_idx)
    "entry":   1,   # detect per-bo 入口(bar=bo_idx)
    "confirm": 1,   # 企稳确认根(开段,bar=i)
    "end":     5,   # phase2_break 截断(i-1)/ weak(i-1)/ rise(i-1)/
                    # timeout(i)/ 收尾强制闭合(end)
})


def _collect_debug_break_calls():
    src = THROWBACK_V3_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(THROWBACK_V3_PATH))
    return [n for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and getattr(n.func, "id", None) == "debug_break"]


def test_throwback_v3_has_exactly_eight_debug_break_calls():
    calls = _collect_debug_break_calls()
    assert len(calls) == 8, (
        f"expected 8 debug_break calls in throwback_v3.py · got {len(calls)}"
        f" at lines {[c.lineno for c in calls]}"
    )


def test_every_debug_break_has_anchor_kind_kwarg_as_str_literal():
    calls = _collect_debug_break_calls()
    for c in calls:
        anchor_kind_kw = next((k for k in c.keywords if k.arg == "anchor_kind"), None)
        assert anchor_kind_kw is not None, (
            f"L{c.lineno} debug_break missing required anchor_kind kwarg"
        )
        assert isinstance(anchor_kind_kw.value, ast.Constant) and isinstance(anchor_kind_kw.value.value, str), (
            f"L{c.lineno} anchor_kind must be str literal (for grep-ability) · got "
            f"{ast.dump(anchor_kind_kw.value)}"
        )


def test_throwback_v3_anchor_kind_distribution_matches_baseline():
    """anchor_kind 分布 Counter 严格等于 baseline。"""
    calls = _collect_debug_break_calls()
    kinds = [
        next(k.value.value for k in c.keywords if k.arg == "anchor_kind")
        for c in calls
    ]
    actual = Counter(kinds)
    assert actual == EXPECTED_ANCHOR_COUNTER, (
        f"anchor_kind distribution mismatch:\n"
        f"  expected {dict(EXPECTED_ANCHOR_COUNTER)}\n"
        f"  actual   {dict(actual)}\n"
        f"lines: {[c.lineno for c in calls]}\n"
        f"kinds: {kinds}"
    )


def _make_measured():
    return MeasuredKindAware(kind='count', value=0.0, label='x')


def test_emit_tb_gate_v3_triggers_debug_break_on_diagnose_path(monkeypatch):
    """on_gate 非 None(diagnose)→ debug_break 被调用,参数 = gate_idx(非 bo_idx);
    GateFailure.node_id 直出为空(身份由 gate_collector per-node wrapper 注入)。"""
    calls = []
    monkeypatch.setattr("path2.atoms.throwback_v3.debug_break",
                        lambda i, *, anchor_kind, **_kw: calls.append(i))

    collected = []
    throwback_v3._emit_tb_gate_v3(
        bo_idx=100, gate_idx=250, gate_name='phase1_break',
        measured=_make_measured(), threshold=0.0, atr_window=14,
        on_gate=lambda gf: collected.append(gf),
    )

    assert calls == [250], "debug_break should be called with gate_idx (not bo_idx)"
    assert len(collected) == 1, "on_gate should still be called (existing behavior preserved)"
    assert collected[0].node_id == ''


def test_emit_tb_gate_v3_skips_debug_break_on_scan_path(monkeypatch):
    """on_gate=None → 早退分支;此断言验证 local invariant。真实 scan attach 了非 None
    on_gate,scan 真正的 bypass 靠 _DEBUG_MODE=False。"""
    calls = []
    monkeypatch.setattr("path2.atoms.throwback_v3.debug_break",
                        lambda i, *, anchor_kind, **_kw: calls.append(i))

    throwback_v3._emit_tb_gate_v3(
        bo_idx=100, gate_idx=250, gate_name='phase1_break',
        measured=_make_measured(), threshold=0.0, atr_window=14,
        on_gate=None,
    )

    assert calls == [], "scan path (on_gate=None) must not touch debug_break"
