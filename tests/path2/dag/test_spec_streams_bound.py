"""PatternSpec 构造期校验:多流 detector 的每条流都有 node 认领(契约 C3)。

背景:多流 detector 声明多条流(stream_schema 的键),声明了但没建 node 认领的流,
此前只会在引擎 _translate_refs 阶段以一句误导性的「事件池外」报错现身——那一刻已经
跑到求解匹配阶段,报错离病灶(PatternSpec 声明本身)很远。本测试把 review §1.2 的
实验固化:提前到 PatternSpec 构造期,报一句说人话、点名缺流的错。
"""
import importlib
from dataclasses import dataclass

import pytest

from path2.atoms.breakout import BODetector
from path2.core import Event
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec


@dataclass(frozen=True)
class _E(Event):
    start_idx: int = 0
    end_idx: int = 0
    confirm_idx: int = 0


class _Dual:
    """多流假 detector,产 'bo'/'pk' 两条流。"""
    produces = {"bo": _E, "pk": _E}

    def detect(self, df):
        yield ("bo", _E(start_idx=0, end_idx=0, confirm_idx=0))
        yield ("pk", _E(start_idx=1, end_idx=1, confirm_idx=1))


class _Single:
    """单流假 detector,不写 produces(走 stream_schema 回落路径 {None: event_cls})。"""
    event_cls = _E

    def detect(self, df):
        yield _E(start_idx=0, end_idx=0, confirm_idx=0)


@dataclass(frozen=True)
class _Container(Event):
    """带 child_slots 的容器事件,用于构造子结构 node。"""
    start_idx: int = 0
    end_idx: int = 0
    confirm_idx: int = 0
    members: tuple = ()

    def child_slots(self):
        return {"members": self.members}


class _ContainerDet:
    event_cls = _Container

    def detect(self, df):
        yield _Container(start_idx=0, end_idx=0, confirm_idx=0)


def test_missing_stream_node_raises_with_message():
    """多流假 detector 只建一个 node → PatternSpec 构造期抛 ValueError,
    match='没有 node 认领' 且信息含缺的流名 pk。"""
    det = _Dual()
    with pytest.raises(ValueError, match="没有 node 认领") as exc_info:
        PatternSpec("p", nodes=[NodeSpec("bo", det, produces_stream="bo")], edges=())
    assert "pk" in str(exc_info.value)


def test_both_streams_bound_passes():
    """两条流都建 node → 通过。"""
    det = _Dual()
    spec = PatternSpec("p", nodes=[
        NodeSpec("bo", det, produces_stream="bo"),
        NodeSpec("pk", det, produces_stream="pk"),
    ], edges=())
    assert {n.node_id for n in spec.nodes} == {"bo", "pk"}


def test_single_stream_detector_without_produces_stream_passes():
    """单流 detector 不写 produces_stream → 通过(声明 {None} = 认领 {None})。"""
    det = _Single()
    spec = PatternSpec("p", nodes=[NodeSpec("bo", det)], edges=())
    assert spec.nodes[0].node_id == "bo"


def test_same_detector_different_consumes_stream_validated_independently():
    """同一 detector 两次不同 consumes_stream 的调用各自独立校验:构造两个 node
    组,其中一组(consumes_stream='src2')缺 pk 认领 → 报错信息指向那一组,
    不牵连另一组(consumes_stream='src1',已双绑齐全)。"""
    det = _Dual()
    src_a, src_b = _Single(), _Single()
    nodes = [
        NodeSpec("src1", src_a),
        NodeSpec("src2", src_b),
        NodeSpec("g1_bo", det, produces_stream="bo", consumes_stream="src1"),
        NodeSpec("g1_pk", det, produces_stream="pk", consumes_stream="src1"),
        NodeSpec("g2_bo", det, produces_stream="bo", consumes_stream="src2"),
    ]
    with pytest.raises(ValueError, match="没有 node 认领") as exc_info:
        PatternSpec("p", nodes=nodes, edges=())
    msg = str(exc_info.value)
    assert "g2_bo" in msg
    assert "g1_bo" not in msg and "g1_pk" not in msg


def test_substructure_node_not_participating():
    """子结构 node(detector=None)不参与流认领校验。"""
    det = _ContainerDet()
    spec = PatternSpec("p", nodes=[
        NodeSpec("box", det, children={"members": "inner"}),
        NodeSpec("inner", event_cls=_E),
    ], edges=())
    assert spec.nodes[1].produced_by == "box"


def test_bo_detector_pk_stream_unbound_raises_at_construction():
    """回归:真实 BODetector 只建 bo node → 构造期即报错(review §1.2 的实验固化,
    错误不再是引擎 _translate_refs 阶段那句误导性的「事件池外」)。"""
    det = BODetector()
    with pytest.raises(ValueError, match="没有 node 认领") as exc_info:
        PatternSpec("p", nodes=[NodeSpec("bo", det, produces_stream="bo")], edges=())
    assert "pk" in str(exc_info.value)


_APP_NAMES = ["bb_pk", "bb_v0", "bb_v1", "bb_v3", "bo_only", "bottom_burst", "try_conplex_where"]


@pytest.mark.parametrize("app_name", _APP_NAMES)
def test_app_build_pattern_constructible(app_name):
    """7 个 app 的 build_pattern(Params.default()) 全部可构造(不被新校验误杀)。"""
    dag_spec = importlib.import_module(f"path2_apps.{app_name}.dag_spec")
    params_mod = importlib.import_module(f"path2_apps.{app_name}.params")
    spec = dag_spec.build_pattern(params_mod.Params.default())
    assert isinstance(spec, PatternSpec)
