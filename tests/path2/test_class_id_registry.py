import pytest
from path2.core import Event, _CLASS_ID_REGISTRY
from path2.atoms.trend import TrendSegment
from path2.atoms.breakout import BOEvent  # noqa: F401 — triggers class_id registration
from path2.atoms.throwback import ThrowbackEvent  # noqa: F401
from path2.atoms.platform import Platform  # noqa: F401
from path2.atoms.distribution import Distribution  # noqa: F401
from path2.dag.result import PatternMatch  # noqa: F401


def test_known_class_ids_registered():
    assert _CLASS_ID_REGISTRY["trend"] is TrendSegment
    for cid in ("trend", "bo", "tb", "platform", "dist", "match"):
        assert cid in _CLASS_ID_REGISTRY


def test_duplicate_class_id_raises():
    with pytest.raises(ValueError, match="class_id 冲突"):
        from dataclasses import dataclass
        @dataclass(frozen=True)
        class Dup(Event):
            class_id = "trend"   # 已被 TrendSegment 占用


def test_missing_class_id_raises():
    with pytest.raises(TypeError, match="必须声明.*class_id"):
        from dataclasses import dataclass
        @dataclass(frozen=True)
        class NoId(Event):
            pass
