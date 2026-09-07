"""预置流(preset)的引擎侧行为钉子。

preset = 调用方把上一次 run_streams 算出来的事件流原样交回,指明这些 node
不必重新检测。被预置的流跳过检测与身份注入,原样成为本次返回值的一部分;
出口的引用槽翻译与 children 校验照常对它跑。
"""
import pandas as pd
import pytest

from path2 import config
from path2.core import Event
from path2.dag.engine import run_streams
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec
from tests.path2.dogfood_multistream import RangeNoteDetector

from dataclasses import dataclass


@dataclass(frozen=True)
class _Plain(Event):
    """无引用槽的事件——用来验证「没有引用槽就抓不住未标注」这个失败面。"""
    start_idx: int = 0
    end_idx: int = 0
    confirm_idx: int = 0


class _PlainDet:
    produces = {"p": _Plain}

    def detect(self, df):
        yield ("p", _Plain(start_idx=0, end_idx=0, confirm_idx=0))


class _CountingRangeNote(RangeNoteDetector):
    """统计 detect 被真正调用了几趟。"""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.calls = 0

    def detect(self, df):
        self.calls += 1
        yield from super().detect(df)


def _df(n: int = 15) -> pd.DataFrame:
    base = list(range(1, n + 1))
    return pd.DataFrame({"open": base, "high": [x + 0.5 for x in base],
                         "low": [x - 0.5 for x in base], "close": base,
                         "volume": [1] * n})


def _spec(det, *, alias: bool = False) -> PatternSpec:
    if alias:
        return PatternSpec("p", edges=(), nodes=[
            NodeSpec("n1", det, produces_stream="range"),
            NodeSpec("n2", det, produces_stream="range"),
            NodeSpec("nb", det, produces_stream="note", solve=False),
        ])
    return PatternSpec("p", edges=(), nodes=[
        NodeSpec("range", det, produces_stream="range"),
        NodeSpec("note", det, produces_stream="note", solve=False),
    ])


def _face(streams):
    """比较面:身份 + 几何 + 引用槽翻译结果。ref_ids 必须在里面——
    真实数据上曾出现过 span/身份全等、只有 ref_ids 不等的情形。"""
    return {nid: [(e.node_id, e.instance_id, e.start_idx, e.end_idx, e.ref_ids)
                  for e in evs] for nid, evs in streams.items()}


def test_preset_whole_group_skips_detect_and_is_byte_identical():
    """整组预置:一趟 detect 都不跑,结果与独立全量重跑逐字相同(含 ref_ids)。

    ⚠ 不能只断言 seeded == full:预置流原样进返回值,那两个 dict 里装的是同一批
    list 对象,相等是重言的。有意义的比较面有两个——
      (a) 与「预置之前拍的快照」比 ⟹ 证明出口的引用槽翻译对预置流是幂等的
          (_translate_refs 会就地重写 ref_ids,不幂等的话这里就露馅);
      (b) 与一次独立的全量重跑比 ⟹ 证明预置路径没有产出不同的结果。
    """
    df = _df()
    det_a = _CountingRangeNote(span=3, min_bars=5)
    full = run_streams(_spec(det_a), df)
    assert det_a.calls == 1
    before = _face(full)                      # 先拍照:下一次调用会就地重写 ref_ids

    det_b = _CountingRangeNote(span=3, min_bars=5)
    seeded = run_streams(_spec(det_b), df, preset=dict(full))
    assert det_b.calls == 0, "整组预置必须省掉那一趟 detect"
    assert _face(seeded) == before            # (a) 幂等

    independent = run_streams(_spec(_CountingRangeNote(span=3, min_bars=5)), df)
    assert _face(seeded) == _face(independent)  # (b) 与独立重跑等价


def test_half_preset_raises_when_fresh_stream_references_preset_sibling():
    """半截预置(同一趟 detect 只预置一部分流)在兄弟间有引用时会抛——响亮,不静默。

    机理:被预置的那条整条跳过,本趟新产出的同名对象被丢弃且未标注;新检测出来
    的兄弟流引用的正是这批被丢弃的对象,出口翻译引用槽时发现它们没有身份。
    """
    df = _df()
    full = run_streams(_spec(_CountingRangeNote(span=3, min_bars=5)), df)
    with pytest.raises(ValueError, match="没有 instance_id"):
        run_streams(_spec(_CountingRangeNote(span=3, min_bars=5)), df,
                    preset={"range": full["range"]})


def test_preset_key_not_in_spec_raises_with_checks_off():
    """键越界必须抛,且不依赖 RUNTIME_CHECKS——关着时原先是静默污染。"""
    df = _df()
    full = run_streams(_spec(_CountingRangeNote(span=3, min_bars=5)), df)
    config.set_runtime_checks(False)
    try:
        with pytest.raises(ValueError, match="ghost"):
            run_streams(_spec(_CountingRangeNote(span=3, min_bars=5)), df,
                        preset={**full, "ghost": []})
    finally:
        config.set_runtime_checks(True)


def test_preset_unannotated_event_raises_even_without_ref_slots():
    """没有引用槽的流喂未标注事件——_translate_refs 抓不住,必须靠入口校验抓。"""
    det = _PlainDet()
    spec = PatternSpec("p", edges=(), nodes=[NodeSpec("p", det, produces_stream="p")])
    with pytest.raises(ValueError, match="未标注"):
        run_streams(spec, _df(), preset={"p": [_Plain(start_idx=0, end_idx=0, confirm_idx=0)]})


def test_preset_event_from_another_spec_raises():
    """事件自报的 node_id 不在本 spec 的 detector node 集内 —— 疑似来自另一份 spec。"""
    df = _df()
    full = run_streams(_spec(_CountingRangeNote(span=3, min_bars=5)), df)
    # 两个 node 必须共用同一个 detector 实例:一个实例产两条流,分开建会让每个实例
    # 各有一条流没人认领,PatternSpec 构造期(_validate_streams_bound)直接拒。
    other_det = _CountingRangeNote(span=3, min_bars=5)
    other = PatternSpec("q", edges=(), nodes=[
        NodeSpec("other_range", other_det, produces_stream="range"),
        NodeSpec("other_note", other_det, produces_stream="note", solve=False),
    ])
    with pytest.raises(ValueError, match="另一份 spec"):
        run_streams(other, df, preset={"other_range": full["range"]})


def test_preset_accepts_alias_shape():
    """别名形状(两个 node 认领同一条产出流)必须通过校验——引擎自己的折叠行为
    会让 streams['n2'] 里坐着 node_id='n1' 的事件,那是合法的。"""
    df = _df()
    full = run_streams(_spec(_CountingRangeNote(span=3, min_bars=5), alias=True), df)
    assert {nid: sorted({e.node_id for e in evs}) for nid, evs in full.items()} == {
        "n1": ["n1"], "n2": ["n1"], "nb": ["nb"]}
    before = _face(full)
    again = run_streams(_spec(_CountingRangeNote(span=3, min_bars=5), alias=True), df,
                        preset=dict(full))
    assert _face(again) == before
