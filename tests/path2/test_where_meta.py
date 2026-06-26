# tests/path2/test_where_meta.py
"""W.attr 工厂携带结构化元数据 + measure;调用接口 (x,ctx)->bool 不变。"""
from dataclasses import dataclass
from path2.dag import where as W


@dataclass(frozen=True)
class _E:          # 最小 event 替身(只需被 getattr 的字段)
    drought: int = 0


def test_attr_still_returns_bool():
    fn = W.attr("drought", ">=", 60)
    assert fn(_E(drought=88), None) is True
    assert fn(_E(drought=10), None) is False


def test_attr_carries_meta_and_measure():
    fn = W.attr("drought", ">=", 60)
    assert fn.meta == {"kind": "attr", "field": "drought", "op": ">=", "threshold": 60}
    assert fn.measure(_E(drought=88), None) == 88


def test_none_value_still_false():
    fn = W.attr("drought", ">=", 60)
    assert fn(_E(drought=None), None) is False   # 保留旧 None 短路语义
    assert fn.measure(_E(drought=None), None) is None
