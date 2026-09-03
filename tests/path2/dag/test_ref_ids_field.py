"""Event.ref_ids 声明字段(契约 C1)。

ref_slots() 对象引用经引擎 _translate_refs 翻译后,不再以 {slot}_ref_ids 属性注入
(object.__setattr__ 挂在实例上、绕过 __init__),而是落地为 Event 基类的声明字段
ref_ids —— 形状 = 按槽名字典序排列的 (槽名, (instance_id, ...)) 对,
配便利方法 ref_ids_of(slot) 查询。声明字段的好处:dataclasses.replace() 会保留它
(旧的属性注入做不到,replace() 只按 __init__ 签名重建实例)。
"""
import dataclasses

import pandas as pd

from path2.dag.engine import run_streams
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec
from tests.path2.dogfood_multistream import RangeNoteDetector


def _df():
    n = 15
    base = list(range(1, n + 1))
    return pd.DataFrame({"open": base, "high": [x + 0.5 for x in base],
                         "low": [x - 0.5 for x in base], "close": base,
                         "volume": [1] * n})


def _run():
    det = RangeNoteDetector(span=3, min_bars=5)
    spec = PatternSpec("p", edges=(), nodes=[
        NodeSpec("range", det, produces_stream="range"),
        NodeSpec("note", det, produces_stream="note", solve=False),
    ])
    streams = run_streams(spec, _df())
    return streams["range"], streams["note"]


def test_ref_ids_translated_and_queryable():
    ranges, notes = _run()
    rng, note = ranges[0], notes[0]
    assert note.ref_ids == (("anchor", (rng.instance_id,)),)
    assert note.ref_ids_of("anchor") == (rng.instance_id,)
    assert note.ref_ids_of("nope") == ()


def test_old_attribute_injection_removed():
    _, notes = _run()
    assert hasattr(notes[0], "anchor_ref_ids") is False


def test_ref_ids_empty_when_no_refs():
    ranges, _ = _run()
    assert ranges[0].ref_ids == ()


def test_ref_ids_survives_dataclasses_replace():
    """声明字段(而非属性注入)的好处:replace() 重建实例仍保留 ref_ids。"""
    _, notes = _run()
    note = notes[0]
    replaced = dataclasses.replace(note, start_idx=note.start_idx - 1)
    assert replaced.ref_ids == note.ref_ids


def test_ref_ids_hashable():
    _, notes = _run()
    hash(notes[0])  # tuple 容器,不抛
