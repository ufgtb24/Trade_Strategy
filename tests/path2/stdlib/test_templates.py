"""BarwiseDetector 单测:抽象强制 / 主循环+None 过滤 / 零跨事件校验。"""
from dataclasses import dataclass

import pandas as pd
import pytest

from path2 import run
from path2.core import Event
from path2.stdlib.templates import BarwiseDetector


@dataclass(frozen=True)
class _Ev(Event):
    pass


def test_cannot_instantiate_without_emit():
    with pytest.raises(TypeError):
        BarwiseDetector()  # 抽象方法 emit 未实现


def test_detect_loops_all_bars_and_filters_none():
    # emit 在 i==1、i==3 命中,其余 None;模板主循环覆盖 range(len(df))
    class D(BarwiseDetector):
        def emit(self, df, i):
            if i in (1, 3):
                return _Ev(event_id=f"e{i}", start_idx=i, end_idx=i)
            return None

    df = pd.DataFrame({"volume": [10, 20, 30, 40, 50]})
    got = list(run(D(), df))
    assert [(e.start_idx, e.event_id) for e in got] == [(1, "e1"), (3, "e3")]


def test_template_does_no_cross_event_checks():
    # 模板自身不校验 end_idx 升序 / id 唯一(留给 run());直接 detect()
    # 故意乱序 + 重复 id,detect 仍照单全收(不抛)
    class D(BarwiseDetector):
        def emit(self, df, i):
            return _Ev(event_id="dup", start_idx=4 - i, end_idx=4 - i)

    df = pd.DataFrame({"volume": [1, 2, 3]})
    raw = list(D().detect(df))  # 绕过 run(),直检模板裸行为
    assert [e.start_idx for e in raw] == [4, 3, 2]
    assert all(e.event_id == "dup" for e in raw)


def test_barwise_detector_publicly_exported():
    import path2
    from path2.stdlib.templates import BarwiseDetector as _BD

    assert path2.BarwiseDetector is _BD
    assert "BarwiseDetector" in path2.__all__
    assert "span_id" in path2.__all__
