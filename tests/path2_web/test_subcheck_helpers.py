"""Task 16:pair 层 4 通道 subcheck helper 单测。

test_check_anchor_needs_map 对 brief 做了 adaptation:真实 `DependencyEdge._anchor_ok`
(edges.py:91)是实例方法、签名 `(self, src_ep, e_dst)`,无 `edge_ok_map` 参数
(brief 早期设想已 stale)。`_check_anchor(edge, u, v)` 直接调 `edge._anchor_ok(u, v)`;
anchor_field 未声明(默认 None)时 `_anchor_ok` 自身恒返回 True,故本用例仍是"无 anchor
约束时 pass"语义,只是不再经 edge_ok_map 这一跳。
"""
from path2_web.diagnose import (
    _check_feasible_window, _check_satisfies, _check_anchor, _check_strict, SubCheck,
)
from path2.dag.edges import TemporalEdge
from path2.atoms.breakout import BOEvent


def _bo(idx):
    return BOEvent(event_id=f"bo_{idx}", start_idx=idx, end_idx=idx, confirm_idx=idx,
                   drought=None, pk_count=1, broken_peak_ids=(), vol_ratio=None,
                   peak_vol_max=0.0, referenced_points=())


def test_check_feasible_window_pass():
    edge = TemporalEdge(src='a', dst='b', min_gap=0, max_gap=10)
    sc = _check_feasible_window(edge, _bo(10), _bo(15))
    assert sc.channel == 'feasible_window'
    assert sc.passed is True


def test_check_feasible_window_fail():
    edge = TemporalEdge(src='a', dst='b', min_gap=0, max_gap=10)
    sc = _check_feasible_window(edge, _bo(10), _bo(25))
    assert sc.passed is False
    assert sc.reason.startswith('gap')


def test_check_satisfies_pass():
    edge = TemporalEdge(src='a', dst='b', min_gap=0, max_gap=10)
    sc = _check_satisfies(edge, _bo(10), _bo(15))
    assert sc.passed is True


def test_check_anchor_needs_map():
    """无 anchor_field 时 pass(承 real _anchor_ok:94 `if self.anchor_field is None: return True`;
    real API 无 edge_ok_map 参数,见模块 docstring)。"""
    edge = TemporalEdge(src='a', dst='b', min_gap=0, max_gap=10)
    sc = _check_anchor(edge, _bo(10), _bo(15))
    assert sc.channel == 'anchor'
    assert sc.passed is True


def test_check_strict_no_strict_returns_pass():
    """非 strict 边 · 直接 pass"""
    edge = TemporalEdge(src='a', dst='b', min_gap=0, max_gap=10)
    sc = _check_strict(edge, _bo(10), _bo(15), streams={})
    assert sc.passed is True
