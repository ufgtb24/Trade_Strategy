"""Dogfood 验证脚手架:两级形态 VolSpike(L1) → VolCluster(L2)。

不是 stdlib —— 仅用于 dogfood 验证协议层贴合度,故定义在 tests/ 下,
不进 path2/ 包。集成测试与图脚本共用本模块。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator

import pandas as pd

from path2 import Event


@dataclass(frozen=True)
class VolSpike(Event):
    """L1:某根 K 线相对前 20 日均量放量。"""

    ratio: float = 0.0


@dataclass(frozen=True)
class VolCluster(Event):
    """L2:窗口内 >=3 个 VolSpike 聚成的簇。"""

    count: int = 0
    span_bars: int = 0


class VolSpikeDetector:
    """volume[i] / mean(volume[i-20:i]) > 2.0 → VolSpike(start=end=i)。"""

    LOOKBACK = 20
    THRESHOLD = 2.0

    def detect(self, df: pd.DataFrame) -> Iterator[VolSpike]:
        vol = df["volume"].to_numpy()
        for i in range(self.LOOKBACK, len(vol)):
            mean = vol[i - self.LOOKBACK : i].mean()
            ratio = float(vol[i] / mean)
            if ratio > self.THRESHOLD:
                yield VolSpike(
                    event_id=f"vs_{i}", start_idx=i, end_idx=i, ratio=ratio
                )


class VolClusterDetector:
    """非重叠贪心,窗口锚定首成员:>=3 个 spike 落在 <=W bar 内成簇,
    然后从末成员之后继续扫(保证 end_idx 单调升 + event_id 唯一)。"""

    WINDOW = 10
    MIN_MEMBERS = 3

    def detect(self, spikes: Iterable[VolSpike]) -> Iterator[VolCluster]:
        items = list(spikes)  # L2 需前瞻,物化下层流
        i = 0
        while i < len(items):
            first = items[i]
            window = [first]
            j = i + 1
            while (
                j < len(items)
                and items[j].start_idx - first.start_idx <= self.WINDOW
            ):
                window.append(items[j])
                j += 1
            if len(window) >= self.MIN_MEMBERS:
                start = window[0].start_idx
                end = window[-1].end_idx
                yield VolCluster(
                    event_id=f"vc_{start}_{end}",
                    start_idx=start,
                    end_idx=end,
                    count=len(window),
                    span_bars=end - start,
                )
                i = j
            else:
                i += 1
