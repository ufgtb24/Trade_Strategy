"""BO (突破) atom: Peak 内部数据 + BOEvent 对外 + BODetector。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator, List, Optional, Tuple

import numpy as np
import pandas as pd

from path2 import Event
from path2.calc.measure import VALID_MEASURES, measure_at, measure_series
from path2.calc.volume import calculate_vol_ratio
from path2.stdlib import BarwiseDetector, span_id


@dataclass
class Peak:
    """BODetector 内部维护的活跃 peak。不是 Event(不出 stream)。

    elevation 机制(对齐 dev breakout_detector.py):小幅突破(≤peak_supersede_threshold)
    时 peak.price 被抬升到 BO 的 elevation_price,original_price 记录首次抬升前的原值
    供 supersede 判定锚定。不抬升时 original_price 保持 None。非 frozen 是必要的:
    dev 同名字段同样可变;且 Peak 是 detector 私有、不进 Event 系统、无 frozen 协议要求。
    """
    index: int
    price: float
    pk_id: int
    volume_peak: float
    relative_height: float
    original_price: Optional[float] = None


@dataclass(frozen=True)
class BOEvent(Event):
    """单点突破事件。start_idx == end_idx == BO bar 索引。

    输出字段(where 可引用):
    - drought:           距上一根 BO 的 bar 数;序列首次 BO 为 None
    - pk_count:          当前 bar 一次性突破的 peak 个数
    - broken_peak_ids:   被突破的 peak id 元组(追溯用)
    - vol_ratio:         当根量比;序列前 vol_baseline_period 根热身期为 None
    - peak_vol_max:      被突破各 peak 中最大的 volume_peak
    - referenced_points: 渲染辅助 (bar_idx, price, label) 三元组;
                         render_grid='price' 时前端按字段存在性渲染卫星 marker
    """
    class_id = "bo"
    is_point = True   # 点几何承诺,供 PatternSpec._validate_render_grid 反射
    drought: Optional[int] = None
    pk_count: int = 0
    broken_peak_ids: Tuple[int, ...] = ()
    vol_ratio: Optional[float] = None
    peak_vol_max: float = 0.0
    referenced_points: Tuple[Tuple[int, float, str], ...] = ()
    # (bar_idx, price, label) 三元组的元组; render_grid='price' 时前端按字段
    # 存在性渲染卫星 marker (dot + text label); label 由 detector 填字面字符串,
    # 前端不读 label 内容做条件分支。

    def __post_init__(self) -> None:
        super().__post_init__()
        # 兜底:frozen + Tuple 类型约定,生产侧若传 list 强转 tuple,
        # 防止下游 in-place mutate(per review I4)。
        if not isinstance(self.broken_peak_ids, tuple):
            object.__setattr__(self, "broken_peak_ids", tuple(self.broken_peak_ids))
        if not isinstance(self.referenced_points, tuple):
            object.__setattr__(self, "referenced_points",
                               tuple(tuple(p) for p in self.referenced_points))


@dataclass(frozen=True)
class BurstEvent(Event):
    """一串 bo 聚合成的密度 burst。members 存完整 BOEvent 对象(非 id)。
    预算标量在 detect 期算一次,供 where W.attr 直读。

    输出字段(where 可引用):
    - count:             簇内 bo 个数(= len(members))
    - distinct_pk:       簇内 bo 突破过的不同 peak 个数(并集)
    - max_bar_vol_ratio: burst [start_idx, end_idx] 区间内任一 bar 的 vol_ratio 最大值,
                         由 BurstDetector.detect() 一次性预算整列后传入 _make_burst,
                         非 BO bar 也参与取 max
    - first_drought:     簇首 bo 的 drought(序列首次 bo 落首位时为 0)
    - members:           内嵌完整 BOEvent 序列,支持 Child("first_bo"/"last_bo") 端点选择器
                         与 children("members") 全员选择器
    """
    class_id = "burst"
    count: int = 0
    distinct_pk: int = 0
    max_bar_vol_ratio: float = 0.0
    first_drought: int = 0
    members: Tuple[BOEvent, ...] = ()

    def child_slots(self):
        return {"members": self.members}

    def child(self, name: str):
        if name == "first_bo":
            return self.members[0]
        if name == "last_bo":
            return self.members[-1]
        raise KeyError(name)

    def children(self, name: str):
        if name == "members":
            return self.members
        raise KeyError(name)


class BurstDetector:
    """consumes bo 流,chain 链式聚类 + all_ends 前缀族物化(独立性原则:不 new BODetector)。

    聚类(chain):相邻 bo 的 start_idx 差 ≤ gap_max 即链接,> gap_max 断链。
    密度判据只看相邻间距、与总跨度无关——修复 span 固定窗把「紧但长」的串切碎的缺陷。
    物化(all_ends):簇内每个 end(潜在 last_bo)若前缀长度 ≥ min_bos 即 emit 一个前缀实例
    (members = 簇首..该 end)。同簇前缀族共享 first_bo(簇首)、end 各异、嵌套重叠;
    买家因果:实例在 end 时刻即时物化,只读 ≤ end 的数据。总实例 O(n)。
    只切串 + 算预算标量;阈值过滤交给 burst node 的 where。
    """
    event_cls = BurstEvent

    def __init__(self, gap_max: int, min_bos: int, vol_baseline_period: int = 63):
        self.gap_max = gap_max
        self.min_bos = min_bos
        self.vol_baseline_period = vol_baseline_period

    def detect(self, bos: Iterable[BOEvent], df) -> Iterator[BurstEvent]:
        seq = sorted(bos, key=lambda e: (e.start_idx, e.end_idx))
        vol_ratio_series = calculate_vol_ratio(df["volume"], self.vol_baseline_period)
        out = []
        head = 0                                       # 当前簇首在 seq 的下标
        for k in range(len(seq)):
            if k > 0 and seq[k].start_idx - seq[k - 1].start_idx > self.gap_max:
                head = k                               # 断链:相邻 gap > gap_max
            if k - head + 1 >= self.min_bos:
                out.append(self._make_burst(seq[head: k + 1], vol_ratio_series))   # 前缀实例,end=seq[k]
        out.sort(key=lambda e: (e.end_idx, e.start_idx))         # 保险;实际天然 end 升序
        yield from out

    def _make_burst(self, seg, vol_ratio_series) -> BurstEvent:
        peaks: set = set()
        for m in seg:
            peaks.update(m.broken_peak_ids)
        start, end = seg[0].start_idx, seg[-1].end_idx
        bar_vols = vol_ratio_series.iloc[start: end + 1].dropna()
        max_bar_vol_ratio = float(bar_vols.max()) if len(bar_vols) else 0.0
        # event_id 唯一性依赖 bo 为点事件(start==end、各索引互异):同簇前缀靠 last_bo end_idx 区分,跨簇靠簇首 start_idx 区分
        return BurstEvent(
            event_id=span_id("burst", seg[0].start_idx, seg[-1].end_idx),
            start_idx=seg[0].start_idx, end_idx=seg[-1].end_idx,
            count=len(seg),
            distinct_pk=len(peaks),
            max_bar_vol_ratio=max_bar_vol_ratio,
            first_drought=seg[0].drought if seg[0].drought is not None else 0,
            members=tuple(seg),
        )


class BODetector(BarwiseDetector):
    """单点 BO Detector,内部维护 active_peaks(supersede 保留,elevation 砍)。

    核心判据:
      peak 识别(在 [current_idx - total_window, current_idx - 1] 滑窗内):
        窗口最高点、不在前/后各 min_side_bars 范围内、
        相对高度 (peak_price - window_min_low) / window_min_low ≥ min_relative_height。
      突破触发(对每个 active_peak):
        measure_at(i, breakout_measure) > peak.price × (1 + exceed_threshold)。
      突破后两类处置:
        - 小幅突破(< peak_supersede_threshold):保留 peak,
          peak.price 抬升至当前 elevation_price(若更高),
          peak.original_price 首次抬升时锚定原始价供后续 supersede 判定;
        - 大幅突破(≥ peak_supersede_threshold):supersede 移除该 peak。
      peak_measure 定峰位,breakout_measure 定突破比较——含义不同,勿混用。

    emit() 流程:
      1. 滑窗内检测新 peak
      2. 逐 active_peak 判突破
      3. 若有突破:算 drought / pk_count / broken_peak_ids / vol_ratio / peak_vol_max
      4. supersede 移除大幅突破的 peak,小幅突破的 elevation 抬升
      5. yield BOEvent

    输出字段详见 BOEvent。
    """

    event_cls = BOEvent

    def __init__(self,
                 total_window: int = 20,
                 min_side_bars: int = 6,
                 min_relative_height: float = 0.2,
                 exceed_threshold: float = 0.003,
                 peak_supersede_threshold: float = 0.01,
                 vol_baseline_period: int = 63,
                 peak_measure: str = "high",
                 breakout_measure: str = "high"):
        if peak_measure not in VALID_MEASURES:
            raise ValueError(f"peak_measure 必须在 {VALID_MEASURES},实际 {peak_measure!r}")
        if breakout_measure not in VALID_MEASURES:
            raise ValueError(f"breakout_measure 必须在 {VALID_MEASURES},实际 {breakout_measure!r}")
        if min_side_bars * 2 > total_window:
            raise ValueError(
                f"min_side_bars ({min_side_bars}) * 2 > total_window ({total_window})"
            )
        self.total_window = total_window
        self.min_side_bars = min_side_bars
        self.min_relative_height = min_relative_height
        self.exceed_threshold = exceed_threshold
        self.peak_supersede_threshold = peak_supersede_threshold
        self.vol_baseline_period = vol_baseline_period
        self.peak_measure = peak_measure
        self.breakout_measure = breakout_measure
        # 状态字段先在 __init__ 占位,每次 detect() 入口重置
        # (per spec §1.2.4:状态不跨 detect() 调用)
        self._active_peaks: List[Peak] = []
        self._last_bo_idx: Optional[int] = None
        self._peak_id_counter: int = 0
        self._vol_ratio_series: Optional[pd.Series] = None

    def detect(self, df: pd.DataFrame):
        # 重置状态(detect 之间不跨调用)
        self._active_peaks = []
        self._last_bo_idx = None
        self._peak_id_counter = 0
        self._vol_ratio_series = calculate_vol_ratio(df['volume'], self.vol_baseline_period)
        # 调用基类 detect(走 BarwiseDetector 主循环 → 调 emit)
        yield from super().detect(df)

    def emit(self, df: pd.DataFrame, i: int) -> Optional[BOEvent]:
        # 1. peak 检测
        self._detect_peak_in_window(df, i)

        # 2. 突破检测
        breakout_price = measure_at(df, i, self.breakout_measure)
        # elevation 用 peak_measure(同 peak 检测口径);small breakout 时把 peak.price
        # 抬升到此值,下次突破比较以 elevated 价为基。supersede 始终锚原始 price。
        elevation_price = measure_at(df, i, self.peak_measure)
        broken_peaks: List[Peak] = []
        remaining_peaks: List[Peak] = []

        for peak in self._active_peaks:
            exceed_price = peak.price * (1 + self.exceed_threshold)
            # supersede 锚定原始价:peak.price 在小幅突破后会被 elevation 抬升,
            # 若仍以 elevated 价为基会让缓步上行的累计涨幅永远进不到 supersede 分支
            supersede_base = peak.original_price if peak.original_price is not None else peak.price
            supersede_price = supersede_base * (1 + self.peak_supersede_threshold)
            if breakout_price > exceed_price:
                broken_peaks.append(peak)
                if breakout_price > supersede_price:
                    # supersede: 不保留
                    pass
                else:
                    # 小幅突破:抬升 peak.price 到当前 elevation_price(若更高),
                    # 首次抬升时记录 original_price 供后续 supersede 锚定
                    if elevation_price > peak.price:
                        if peak.original_price is None:
                            peak.original_price = peak.price
                        peak.price = elevation_price
                    remaining_peaks.append(peak)
            else:
                remaining_peaks.append(peak)

        self._active_peaks = remaining_peaks

        if not broken_peaks:
            return None

        # 3. 算字段
        drought = None if self._last_bo_idx is None else (i - self._last_bo_idx)
        pk_count = len(broken_peaks)
        broken_peak_ids = tuple(p.pk_id for p in broken_peaks)
        vol_ratio = self._vol_ratio_series.iloc[i] if self._vol_ratio_series is not None else None
        if vol_ratio is not None and pd.isna(vol_ratio):
            vol_ratio = None
        else:
            vol_ratio = float(vol_ratio) if vol_ratio is not None else None
        peak_vol_max = max((p.volume_peak for p in broken_peaks), default=0.0)

        self._last_bo_idx = i

        return BOEvent(
            event_id=span_id(self.event_cls.class_id, i, i),
            start_idx=i,
            end_idx=i,
            drought=drought,
            pk_count=pk_count,
            broken_peak_ids=broken_peak_ids,
            vol_ratio=vol_ratio,   # 因子移植的遗留，暂时无用，只是反映因子功能在 path2 中依旧保留
            peak_vol_max=peak_vol_max,    # 因子移植的遗留，暂时无用
            referenced_points=tuple(
                (p.index, p.price, f"pk{p.pk_id}") for p in broken_peaks
            ),
        )

    def _detect_peak_in_window(self, df: pd.DataFrame, current_idx: int):
        """在 [current_idx - total_window, current_idx - 1] 窗口内检测新 peak。

        peak 判据(4 条):
          1. 在窗口的最高 max(open, close)(实体上界)
          2. 局部索引不在前 min_side_bars 或后 min_side_bars
          3. (peak_price - window_low_min) / window_low_min >= min_relative_height
          4. peak 索引未在 active_peaks 中
        """
        window_start = current_idx - self.total_window
        if window_start < 0:
            return
        lows = df['low'].iloc[window_start: current_idx]
        volumes = df['volume'].iloc[window_start: current_idx]

        measures_s = measure_series(df, self.peak_measure)
        measures = list(measures_s.iloc[window_start: current_idx])
        max_measure = max(measures)
        # 并列峰取最左(list.index 返回最左匹配,与 dev breakout_detector.py:463 行为一致)
        max_local_idx = measures.index(max_measure)

        if max_local_idx < self.min_side_bars:
            return
        if max_local_idx >= len(measures) - self.min_side_bars:
            return

        peak_global_idx = window_start + max_local_idx
        # 已存在
        for p in self._active_peaks:
            if p.index == peak_global_idx:
                return

        window_min_low = min(lows)
        if window_min_low <= 0:
            return
        relative_height = (max_measure - window_min_low) / window_min_low
        if relative_height < self.min_relative_height:
            return

        # 算 volume_peak (vol_ratio at peak idx)
        if self._vol_ratio_series is not None:
            vp = self._vol_ratio_series.iloc[peak_global_idx]
            volume_peak = float(vp) if not pd.isna(vp) else 0.0
        else:
            volume_peak = 0.0

        peak = Peak(
            index=peak_global_idx,
            price=max_measure,
            pk_id=self._peak_id_counter,
            volume_peak=volume_peak,
            relative_height=relative_height,
        )
        self._peak_id_counter += 1

        # peak-peak supersede:新 peak 显著高于(>peak_supersede_threshold) 旧 peak 时,
        # 旧 peak 被淘汰,防止低位老 peak 长期残留、被后续大涨"一锅端"成几十个 broken_peak_ids。
        # 对比锚定旧 peak 的当前(elevated) price——dev 同实现。
        remaining_peaks: List[Peak] = []
        for old_peak in self._active_peaks:
            exceed_pct = (max_measure - old_peak.price) / old_peak.price
            if exceed_pct < self.peak_supersede_threshold:
                remaining_peaks.append(old_peak)
            # else: 被新峰值明显超越,淘汰
        self._active_peaks = remaining_peaks
        self._active_peaks.append(peak)
