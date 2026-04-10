"""实盘 UI 的应用状态。"""

from dataclasses import dataclass, field

from BreakoutStrategy.live.pipeline.results import MatchedBreakout


@dataclass
class AppState:
    items: list[MatchedBreakout] = field(default_factory=list)
    selected: MatchedBreakout | None = None
    last_scan_date: str = ""
    last_scan_bar_date: str = ""
