"""多流 fixture detector:同一趟产 'range'(区间)+ 'note'(点,引用 range)。

不是 stdlib —— 仅用于多流引擎端到端验收(dogfood),故定义在 tests/ 下、不进 path2/ 包。
RangeNoteDetector 在同一趟 detect 内 yield 两条命名流:
  - 'range':每 span 根产一个区间事件(该窗 high 最高点);
  - 'note':range 之后 1 根内的点事件,引用它(同源多流 ref_slots 翻译)。
窗口不足(min_bars)时 emit gate(stream='range'),用于验证 on_gate 按流归属。
"""
from dataclasses import dataclass
from typing import Iterator, Optional, Tuple

import pandas as pd

from path2.core import Event


@dataclass(frozen=True)
class RangeEvent(Event):
    start_idx: int = 0
    end_idx: int = 0
    confirm_idx: int = 0


@dataclass(frozen=True)
class NoteEvent(Event):
    start_idx: int = 0
    end_idx: int = 0
    confirm_idx: int = 0
    anchor_refs: Tuple[Event, ...] = ()

    def ref_slots(self):
        return {"anchor": self.anchor_refs} if self.anchor_refs else {}


class RangeNoteDetector:
    """每 span 根产一个 range(该窗 high 最高点),随后 1 根内产 note 引用它。
    窗口不足时 emit gate(stream='range')。"""
    produces = {"range": RangeEvent, "note": NoteEvent}

    def __init__(self, span: int = 3, min_bars: int = 5):
        self.span, self.min_bars = span, min_bars
        self.on_gate = None

    def detect(self, df: pd.DataFrame) -> Iterator[Tuple[str, Event]]:
        highs = df["high"].to_numpy()
        for i in range(len(df)):
            if i < self.min_bars:
                self._gate("warmup", i, "窗口不足")
                continue
            if i % self.span == 0:
                lo = max(0, i - self.span)
                j = int(highs[lo:i + 1].argmax()) + lo
                rng = RangeEvent(start_idx=lo, end_idx=i, confirm_idx=i)
                yield ("range", rng)
                if i + 1 < len(df):
                    yield ("note", NoteEvent(start_idx=i + 1, end_idx=i + 1,
                                             confirm_idx=i + 1, anchor_refs=(rng,)))

    def _gate(self, gate_name, i, label):
        if self.on_gate is not None:
            from path2.dag.gate_failure import GateFailure, MeasuredKindAware
            self.on_gate(GateFailure(
                failure_event_window=(i, i), start_idx=i, gate_idx=i, anchor_bar=i,
                gate_name=gate_name, measured=MeasuredKindAware(kind="count", value=1, label=label),
                threshold=1, op=None, threshold_param=None, evaluation_lookback=None,
                symbol="TEST", stream="range"))
