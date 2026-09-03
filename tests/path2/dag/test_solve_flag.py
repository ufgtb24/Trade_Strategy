"""NodeSpec.solve 判据:零边 pattern 的孤立显示 node 可声明 solve=False 退出求解。"""
from dataclasses import dataclass
import pytest
from path2.core import Event
from path2.dag._solve import compile_plan
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec


@dataclass(frozen=True)
class _E(Event):
    start_idx: int = 0
    end_idx: int = 0
    confirm_idx: int = 0


class _D:
    event_cls = _E
    def detect(self, source): ...


def test_solve_false_excluded_from_bound():
    det = _D()
    spec = PatternSpec("p", nodes=[
        NodeSpec("bo", det),
        NodeSpec("pk", det, solve=False),     # 零边 pattern:pk 声明不参与求解
    ], edges=())
    plan = compile_plan(spec)
    comps = [set(w.comp) for w in plan.wcc_plans]
    assert any("bo" in c for c in comps)
    assert all("pk" not in c for c in comps)
