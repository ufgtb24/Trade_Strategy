"""把扫描结果里的 breakout/peak dict 转成 ChartCanvasManager 期望的对象。

ScanManager.parallel_scan 跨进程返回时把 Breakout/Peak 序列化成 JSON-friendly
dict（见 scanner.py:389-458），而 ChartCanvasManager + MarkerComponent +
PanelComponent 这条绘制链全部用属性访问（bo.index、bo.broken_peaks、
p.id 等）。live UI 直接把 dict 传过去会立刻在 canvas_manager.py:150 抛
AttributeError: 'dict' object has no attribute 'index'。

这里用最轻量的 dataclass 包装，只填图表真正读到的字段——不复制完整的
Breakout/Peak 定义，避免把未使用的因子/特征也带进来。不改 scanner
输出格式，因为 dict 是跨进程 pickle 契约，non-live UI 也依赖它。
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional


@dataclass
class ChartPeak:
    """MarkerComponent.draw_peaks 只读 index / id / price 三个字段。"""
    index: int
    id: Optional[int]
    price: float


@dataclass
class ChartBreakout:
    """canvas_manager + markers + panels 绘制链需要的最小 Breakout 结构。

    各字段的实际使用点：
      index             — canvas_manager.py:150, markers.py:175, panels hover
      price             — markers.py:181
      date              — panels.py:45（strftime）
      quality_score     — canvas_manager hover, markers.py:204, panels.py:36
      broken_peaks      — markers.py:288/293（draw_resistance_zones 读
                          p.price/p.index）+ canvas_manager.py:162
      broken_peak_ids   — markers.py:209/234, canvas_manager hover
      superseded_peak_ids — canvas_manager hover L514
      labels            — canvas_manager hover L536
      num_peaks_broken  — panels.py:33/46, markers.py:284（property）
    """
    index: int
    price: float
    date: date
    quality_score: Optional[float]
    broken_peaks: list            # list[ChartPeak]
    broken_peak_ids: list         # list[int]
    superseded_peak_ids: list     # list[int]
    labels: dict = field(default_factory=dict)

    @property
    def num_peaks_broken(self) -> int:
        return len(self.broken_peaks)


def adapt_peaks(raw_peaks: list) -> tuple[list[ChartPeak], dict]:
    """把 raw_peaks dict 列表转成 ChartPeak 列表 + id→ChartPeak 映射。

    映射用来在重建 ChartBreakout 时通过 broken_peak_ids 反查 ChartPeak 对象
    （scanner 的 dict 契约里 breakout 只保留 ids，不内嵌 peak 明细）。
    """
    peaks = [
        ChartPeak(
            index=int(p["index"]),
            id=p.get("id"),
            price=float(p["price"]),
        )
        for p in raw_peaks
    ]
    by_id = {p.id: p for p in peaks if p.id is not None}
    return peaks, by_id


def adapt_breakout(raw_bo: dict, peaks_by_id: dict) -> ChartBreakout:
    """根据 raw_bo dict + peaks 查找表重建 ChartBreakout。

    broken_peaks 通过 broken_peak_ids → peaks_by_id 查找；如果某个 id 在
    raw_peaks 里找不到（理论上 scanner.py:336-358 保证 all_peaks 包含所有
    被 breakout 引用的 peak，这里只是防御），就跳过该 peak——宁愿漏画一个
    也不要崩掉整个图表。
    """
    broken_ids = raw_bo.get("broken_peak_ids") or []
    superseded_ids = raw_bo.get("superseded_peak_ids") or []
    broken_peaks = [peaks_by_id[i] for i in broken_ids if i in peaks_by_id]

    bo_date_str = raw_bo["date"]
    bo_date = datetime.strptime(bo_date_str, "%Y-%m-%d").date()

    return ChartBreakout(
        index=int(raw_bo["index"]),
        price=float(raw_bo["price"]),
        date=bo_date,
        quality_score=raw_bo.get("quality_score"),
        broken_peaks=broken_peaks,
        broken_peak_ids=list(broken_ids),
        superseded_peak_ids=list(superseded_ids),
        labels=raw_bo.get("labels") or {},
    )
