"""BO (突破) atom: PeakEvent 活跃峰 + BOEvent 对外 + BODetector。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Iterable, Iterator, List, Optional, Tuple

import numpy as np
import pandas as pd

from path2 import Event
from path2.calc.measure import VALID_MEASURES, measure_at, measure_series
from path2.calc.volume import calculate_vol_ratio
from path2.dag.gate_failure import GateFailure, MeasuredKindAware
from path2.debug import current_symbol


@dataclass(frozen=True)
class PeakEvent(Event):
    """峰事件(凸点峰/大阴线高点)。点几何:start=confirm=end=登记 bar(因果诚实,
    峰存在在登记时确定)。峰 bar(窗口 argmax 精确位置)由 peak_idx 承载,≠ start_idx。

    双角色:detect 期间兼作内部活跃峰——elevation 演化 price、supersede 锚
    original_price 均用 object.__setattr__(frozen 显式打破,与
    annotate_stream 注入 instance_id 同手段);detect 结束定稿后不再改。

    定稿三态(alive/broken/eaten)不是字段,由消费侧按引用关系合成:被
    BOEvent.ref_ids.broken 引用 → broken;被别的 PeakEvent.ref_ids.superseded
    引用 → eaten;否则 alive。引用(吃掉的旧峰)走 ref_slots 协议,
    superseded_refs → 引擎翻译落 Event.ref_ids 的 superseded 槽。峰位
    (peak_idx/price)是普通字段,不走引用协议。"""
    is_point = True   # 点几何承诺,供 PatternSpec._validate_render_grid 反射
    pk_id: int = 0                  # 峰唯一标识(convex/bear 共用计数器)
    kind: str = "convex"            # 'convex' | 'bear'
    peak_idx: int = 0               # 峰 bar(窗口 argmax 精确位置;≠ 登记 bar start_idx)
    price: float = 0.0              # 峰价(初始=登记价);detect 内 elevation 演化
    original_price: Optional[float] = None   # supersede 锚;首次抬升记录
    relative_height: float = 0.0
    volume_peak: Optional[float] = None   # 峰位量比(vol_ratio);bear 路径不传,恒 None
    superseded_refs: Tuple[Event, ...] = ()   # 吃掉者记录被它 supersede 的旧峰

    def ref_slots(self):
        return {"superseded": self.superseded_refs} if self.superseded_refs else {}


@dataclass(frozen=True)
class BOEvent(Event):
    """单点突破事件。start_idx == end_idx == BO bar 索引;confirm_idx = start_idx(点事件,该根即确认)。

    输出字段(where 可引用):
    - drought:           距上一根 BO 的 bar 数;序列首次 BO 为 None
    - pk_count:          当前 bar 一次性突破的 peak 个数(派生自 broken_refs,@property)
    - broken_peak_ids:   被突破的 peak id 元组(追溯用;派生自 broken_refs,@property)
    - vol_ratio:         当根量比;序列前 vol_baseline_period 根热身期为 None
    - peak_vol_max:      被突破各 peak 中最大的非 None volume_peak;全 None(如全为 bear 峰)→ 0.0
    - peak_age_max:      被突破各 peak 中最大的 bo_idx - peak.peak_idx(阴跌反弹近峰小,跨越长期结构远)
    - broken_refs:       被突破的 PeakEvent 对象元组(ref_slots 翻译落 Event.ref_ids 的
                         broken 槽);渲染引用走 ref_slots 协议,取代裸三元组
                         referenced_points(已取消)
    """
    is_point = True   # 点几何承诺,供 PatternSpec._validate_render_grid 反射
    drought: Optional[int] = None
    vol_ratio: Optional[float] = None
    peak_vol_max: float = 0.0
    peak_age_max: int = 0   # 距峰时间距离:该 bo 突破的各 peak 中最大的 bo_idx - peak.peak_idx(阴跌反弹近峰小,跨越长期结构远)
    broken_refs: Tuple[Event, ...] = ()   # 被突破峰(PeakEvent)对象元组;ref_slots 翻译落 Event.ref_ids 的 broken 槽

    def ref_slots(self):
        return {"broken": self.broken_refs} if self.broken_refs else {}

    @property
    def pk_count(self) -> int:
        return len(self.broken_refs)

    @property
    def broken_peak_ids(self) -> Tuple[int, ...]:
        return tuple(p.pk_id for p in self.broken_refs)


@dataclass(frozen=True)
class BurstEvent(Event):
    """一串 bo 聚合成的密度 burst。members 存完整 BOEvent 对象(非 id)。
    预算标量在 detect 期算一次,供 where W.attr 直读。
    confirm_idx = end_idx:前缀物化,每个实例在其最后成员 bo(= end_idx)那根 emit 并确认。

    输出字段(where 可引用):
    - count:             簇内 bo 个数(= len(members))
    - distinct_pk:       簇内 bo 突破过的不同 peak 个数(并集)
    - max_bar_vol_ratio: burst [start_idx, end_idx] 区间内任一 bar 的 vol_ratio 最大值,
                         由 BurstDetector.detect() 一次性预算整列后传入 _make_burst,
                         非 BO bar 也参与取 max
    - first_drought:     簇首 bo 的 drought(序列首次 bo 落首位时为 0)
    - peak_age_max:      簇内各 bo peak_age_max 的最大值(max 聚合=存在性:任一根 bo 突破陈旧峰即满足)
    - members:           内嵌完整 BOEvent 序列,支持 Child("first_bo"/"last_bo") 端点选择器
                         与 children("members") 全员选择器
    """
    count: int = 0
    distinct_pk: int = 0
    max_bar_vol_ratio: float = 0.0
    first_drought: int = 0
    peak_age_max: int = 0   # 簇内各 bo peak_age_max 的最大值(max 聚合=存在性:任一根 bo 突破陈旧峰即满足)
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
    只切串 + 算预算标量;阈值过滤交给 burst node 的 where。min_bos 为过滤型参数(见 filter_params)。
    """
    has_debug_hooks: ClassVar[bool] = False
    event_cls = BurstEvent
    on_gate = None   # Detector.on_gate protocol 静态声明,运行时不自动继承;默认 None = 生产路径无开销

    # 过滤型构造参数声明(tune-gates multivar 协议):param → (事件字段, op)。
    # 语义:以该参数最松值构造,事后按 `getattr(event, field) op value` 过滤,与直接以 value
    # 构造得到的事件集逐事件相等(含 members 与全部字段)——min_bos 只在 emit 处把关
    # (`k - head + 1 >= self.min_bos`),不参与切串,故成立。声明者对等价性负责
    # (tests/path2/atoms/test_burst_filter_params.py)。
    # 契约范围仅限 detect() 产出的 Event 流;on_gate 诊断侧信道不在此契约内——
    # 最松档(min_bos=1)因 `last_cluster_size < 1` 恒假而永不吐 min_bos_insufficient、
    # 严档可能吐,且两侧 threshold=self.min_bos 取值不同,故诊断记录本身不逐事件相等。
    # 调参路径固定传 on_gate=None(该分支从不执行)故无害;若未来接出 gate_failures
    # 消费该信道,需重新评估此例外。
    filter_params: ClassVar[dict[str, tuple[str, str]]] = {"min_bos": ("count", ">=")}

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
                # gate: chain_break · 判断相邻两次突破是否紧邻, 足以视作同一簇
                # measured=gap(相邻两次突破的起点索引之差, 单位=bar)
                # 判据: gap<=gap_max 通过并入同簇; gap>gap_max 失败, 前一簇立即结算, 后一根另起新簇
                if self.on_gate is not None:
                    prev_cluster_start = seq[head].start_idx
                    prev_cluster_end = seq[k - 1].end_idx
                    self.on_gate(GateFailure(
                        failure_event_window=(prev_cluster_start, seq[k].start_idx),
                        start_idx=prev_cluster_start,
                        gate_idx=seq[k].start_idx,
                        anchor_bar=prev_cluster_end,
                        gate_name='chain_break',
                        measured=MeasuredKindAware(kind='gap',
                                                    value=seq[k].start_idx - seq[k - 1].start_idx,
                                                    label='gap'),
                        threshold=self.gap_max,
                        op='<=', threshold_param='gap_max',
                        evaluation_lookback=None,
                        symbol=current_symbol.get() or '',
                    ))
                head = k                               # 断链:相邻 gap > gap_max
            if k - head + 1 >= self.min_bos:
                out.append(self._make_burst(seq[head: k + 1], vol_ratio_series))   # 前缀实例,end=seq[k]

        # 流末尾:若最后一簇 size < min_bos,从未跨过 emit 门槛 · 吐 min_bos_insufficient
        if self.on_gate is not None and len(seq) > 0:
            last_cluster_size = len(seq) - head
            if last_cluster_size < self.min_bos:
                # gate: min_bos_insufficient · 扫描结束时手头这一簇的突破数量是否达到确认门槛
                # measured=count(当前簇内已积累的突破个数 = len(seq) - head)
                # 判据: count>=min_bos 通过并落地为 burst; count<min_bos 失败, 该簇被丢弃
                cluster_start = seq[head].start_idx
                cluster_end = seq[-1].end_idx
                self.on_gate(GateFailure(
                    failure_event_window=(cluster_start, cluster_end),
                    start_idx=cluster_start,
                    gate_idx=cluster_end,
                    anchor_bar=cluster_end,
                    gate_name='min_bos_insufficient',
                    measured=MeasuredKindAware(kind='count', value=last_cluster_size, label='bo数'),
                    threshold=self.min_bos,
                    op='>=', threshold_param='min_bos',
                    evaluation_lookback=None,
                    symbol=current_symbol.get() or '',
                ))

        out.sort(key=lambda e: (e.end_idx, e.start_idx))         # 保险;实际天然 end 升序
        yield from out

    def _make_burst(self, seg, vol_ratio_series) -> BurstEvent:
        peaks: set = set()
        for m in seg:
            peaks.update(m.broken_peak_ids)
        start, end = seg[0].start_idx, seg[-1].end_idx
        bar_vols = vol_ratio_series.iloc[start: end + 1].dropna()
        max_bar_vol_ratio = float(bar_vols.max()) if len(bar_vols) else 0.0
        # 实例身份由物化标注(annotate_stream)按 (node_id, span, 流序) 赋予;
        # 同簇前缀靠 last_bo end_idx 区分 span、跨簇靠簇首 start_idx 区分 span。
        return BurstEvent(
            start_idx=seg[0].start_idx, end_idx=seg[-1].end_idx,
            confirm_idx=seg[-1].end_idx,   # 前缀物化:最后成员 bo 那根确认
            count=len(seg),
            distinct_pk=len(peaks),
            max_bar_vol_ratio=max_bar_vol_ratio,
            first_drought=seg[0].drought if seg[0].drought is not None else 0,
            peak_age_max=max(m.peak_age_max for m in seg),
            members=tuple(seg),
        )


class BODetector:
    """单点 BO Detector,多流:产 bo + pk 两流。活跃峰 = PeakEvent(合一)。

    核心判据(与单流版逐字一致):
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

    合一:活跃峰直接是 PeakEvent(登记时即 yield ("pk", ev) 出流)。frozen 的演化
    (elevation 改 price、supersede 锚 original_price)一律用 object.__setattr__,
    detect 结束定稿后不再改。事件 yield 即定稿是通例;本 detector 的 elevation
    抬价(price / original_price)是现存例外,见 authoring-path2-detector
    reference §2。

    detect 主循环:逐 bar 先登记峰(产 pk 流,可能 0..N 个),再突破检测(产 bo 流,
    可能 0..1 个)。同一 (id(det), consumes_stream) 一次 detect 填满两流(引擎兄弟机制)。
    原 emit 流程拆到内部方法:_detect_peak_in_window 滑窗内检测新 peak(收集式返回
    Tuple[PeakEvent, ...]);_check_breakout 逐 active_peak 判突破。

    输出字段详见 BOEvent / PeakEvent。
    """
    produces = {"bo": BOEvent, "pk": PeakEvent}
    has_debug_hooks: ClassVar[bool] = False
    on_gate = None   # Detector.on_gate protocol 静态声明,运行时不自动继承;默认 None = 生产路径无开销

    def __init__(self,
                 total_window: int = 20,
                 min_side_bars: int = 6,
                 min_relative_height: float = 0.2,
                 exceed_threshold: float = 0.003,
                 peak_supersede_threshold: float = 0.01,
                 bear_drop: Optional[float] = None,   # None=禁用 bear 检测(默认 OFF,Ruling A)
                 bear_min_rh: float = 0.20,
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
        self.bear_drop = bear_drop
        self.bear_min_rh = bear_min_rh
        self.vol_baseline_period = vol_baseline_period
        self.peak_measure = peak_measure
        self.breakout_measure = breakout_measure
        # 状态字段先在 __init__ 占位,每次 detect() 入口重置
        # (per spec §1.2.4:状态不跨 detect() 调用)
        self._active_peaks: List[PeakEvent] = []
        self._last_bo_idx: Optional[int] = None
        self._peak_id_counter: int = 0
        self._vol_ratio_series: Optional[pd.Series] = None

    def _eval_lookback(self, current_idx: int) -> Tuple[int, int]:
        """detector 内部判据依赖的历史窗 · [current_idx - total_window, current_idx - 1]
        裁剪起点至非负(不裁剪终点:current_idx=0 时得到 (0, -1),仅供 tooltip 展示、
        不参与 ⊆ 判据,保持与 GateFailure.evaluation_lookback 语义一致的简单公式)。
        """
        return (max(0, current_idx - self.total_window), current_idx - 1)

    def detect(self, df: pd.DataFrame):
        """多流主循环:逐 bar 登记峰(产 pk 流)+ 突破检测(产 bo 流)。

        活跃峰 = PeakEvent(合一),detect 期间 object.__setattr__ 演化 price。
        同一 (id(det), consumes) 一次 detect 填满 bo+pk 两流(引擎兄弟机制)。
        """
        # 重置状态(detect 之间不跨调用)
        self._active_peaks = []
        self._last_bo_idx = None
        self._peak_id_counter = 0
        self._vol_ratio_series = calculate_vol_ratio(df["volume"], self.vol_baseline_period)
        for i in range(len(df)):
            for pk_ev in self._detect_peak_in_window(df, i):   # 登记峰(含 supersede),产 pk
                yield ("pk", pk_ev)
            bo = self._check_breakout(df, i)                    # 突破检测,产 bo
            if bo is not None:
                yield ("bo", bo)

    def _check_breakout(self, df: pd.DataFrame, i: int) -> Optional[BOEvent]:
        """逐 active_peak 判突破(原 emit 的第 2-5 步)。

        被突破峰记入 broken_peaks;小幅突破 elevation 抬升、大幅突破 supersede
        移除;构造 BOEvent,broken_refs 引用被突破峰(ref_slots 翻译落 Event.ref_ids
        的 broken 槽)。定稿状态(broken/eaten/alive)不再是 PeakEvent 字段,由消费侧
        从 ref_ids 合成(见 PeakEvent 类文档)。无突破时发 no_active_peak_broken gate
        并返回 None。语义字段与单流版逐字一致。
        """
        # 突破检测
        breakout_price = measure_at(df, i, self.breakout_measure)
        # elevation 用 peak_measure(同 peak 检测口径);small breakout 时把 peak.price
        # 抬升到此值,下次突破比较以 elevated 价为基。supersede 始终锚原始 price。
        elevation_price = measure_at(df, i, self.peak_measure)
        broken_peaks: List[PeakEvent] = []
        remaining_peaks: List[PeakEvent] = []

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
                            object.__setattr__(peak, "original_price", peak.price)
                        object.__setattr__(peak, "price", elevation_price)
                    remaining_peaks.append(peak)
            else:
                remaining_peaks.append(peak)

        self._active_peaks = remaining_peaks

        if not broken_peaks:
            # gate: no_active_peak_broken · 当前 bar 的价格是否越过某个已登记的候选高点(含溢价倍数)
            # measured=breakout_price(当前 bar 用来比较的价, 由 breakout_measure 决定, 一般是 close 或 high)
            # 判据: 存在候选高点 P 使 breakout_price > P.price*(1+exceed_threshold) 则通过; 否则失败
            if self.on_gate is not None:
                self.on_gate(GateFailure(
                    failure_event_window=(i, i),
                    start_idx=i, gate_idx=i,
                    anchor_bar=i,
                    gate_name='no_active_peak_broken',
                    stream="bo",   # 多流化:gate failure 归属 bo 流(gate_collector 按流路由)
                    measured=MeasuredKindAware(kind='breakout_price', value=breakout_price, label='突破价'),
                    threshold=None,
                    op=None, threshold_param=None,
                    evaluation_lookback=self._eval_lookback(i),
                    symbol=current_symbol.get() or '',
                ))
            return None

        # 3. 算字段
        drought = None if self._last_bo_idx is None else (i - self._last_bo_idx)
        vol_ratio = self._vol_ratio_series.iloc[i] if self._vol_ratio_series is not None else None
        if vol_ratio is not None and pd.isna(vol_ratio):
            vol_ratio = None
        else:
            vol_ratio = float(vol_ratio) if vol_ratio is not None else None
        peak_vol_max = max((p.volume_peak for p in broken_peaks if p.volume_peak is not None), default=0.0)
        peak_age_max = max((i - p.peak_idx for p in broken_peaks), default=0)

        self._last_bo_idx = i

        return BOEvent(
            start_idx=i,
            end_idx=i,
            confirm_idx=i,   # 点事件:该根即确认
            drought=drought,
            vol_ratio=vol_ratio,   # 因子移植的遗留，暂时无用，只是反映因子功能在 path2 中依旧保留
            peak_vol_max=peak_vol_max,    # 因子移植的遗留，暂时无用
            peak_age_max=peak_age_max,
            broken_refs=tuple(broken_peaks),   # 被突破峰(PeakEvent 对象),ref_slots 翻译落 Event.ref_ids 的 broken 槽
        )

    def _register_peak(self, peak: PeakEvent, out: List[PeakEvent]) -> None:
        """登记新峰(convex/bear 共用):分配 pk_id + supersede 杀旧峰 + 入活跃池 + 收集出流。

        supersede 规则与凸点峰登记一致:新峰价相对旧峰 current(elevated) price
        涨幅 ≥ peak_supersede_threshold 时旧峰被淘汰,否则保留。被杀旧峰记入新峰
        superseded_refs(ref_slots 翻译落 Event.ref_ids 的 superseded 槽)。
        PeakEvent frozen → pk_id/superseded_refs 用 object.__setattr__ 演化。
        """
        object.__setattr__(peak, "pk_id", self._peak_id_counter)
        self._peak_id_counter += 1
        remaining: List[PeakEvent] = []
        eaten: List[PeakEvent] = []
        for old in self._active_peaks:
            exceed_pct = (peak.price - old.price) / old.price if old.price else 0.0
            if exceed_pct < self.peak_supersede_threshold:
                remaining.append(old)
            else:
                eaten.append(old)
        self._active_peaks = remaining + [peak]
        if eaten:
            object.__setattr__(peak, "superseded_refs", tuple(eaten))
        out.append(peak)

    def _detect_peak_in_window(self, df: pd.DataFrame, current_idx: int) -> Tuple[PeakEvent, ...]:
        """在 [current_idx - total_window, current_idx - 1] 窗口内检测新 peak(收集式)。

        返回本 bar 新登记的 convex 峰元组(可能空)。gate 失败只跳过 convex 登记、
        不提前 return——为后续 bear 检测(current_idx-1 大阴线)留位置(见 Task 3)。

        peak 判据(4 条):
          1. 在窗口的最高 max(open, close)(实体上界)
          2. 局部索引不在前 min_side_bars 或后 min_side_bars
          3. (peak_price - window_low_min) / window_low_min >= min_relative_height
          4. peak 索引未在 active_peaks 中
        """
        out = []
        window_start = current_idx - self.total_window
        if window_start < 0:
            # gate: peak_no_local_max(热身检查) · 当前 bar 之前是否有 total_window 根历史数据可做局部最大扫描
            # measured=window_start(扫描窗口左端的全局索引 = current_idx - total_window)
            # 判据: window_start>=0 通过(历史够长); <0 失败, 数据不足静默跳过, 非真失败
            if self.on_gate is not None:
                self.on_gate(GateFailure(
                    failure_event_window=(current_idx, current_idx),
                    start_idx=current_idx, gate_idx=current_idx,
                    anchor_bar=current_idx,
                    gate_name='peak_no_local_max',
                    stream="pk",   # 多流化:gate failure 归属 pk 流(gate_collector 按流路由)
                    measured=MeasuredKindAware(kind='window_start', value=window_start, label='窗口起点'),
                    threshold=0,
                    op='>=', threshold_param=None,
                    evaluation_lookback=self._eval_lookback(current_idx),
                    symbol=current_symbol.get() or '',
                ))
            # 数据不足:跳过 convex 登记
        else:
            lows = df['low'].iloc[window_start: current_idx]

            measures_s = measure_series(df, self.peak_measure)
            measures = list(measures_s.iloc[window_start: current_idx])
            max_measure = max(measures)
            # 并列峰取最左(list.index 返回最左匹配,与 dev breakout_detector.py:463 行为一致)
            max_local_idx = measures.index(max_measure)

            if max_local_idx < self.min_side_bars:
                # gate: peak_side_bars_insufficient(首侧) · 候选高点距扫描窗口左端是否留出足够的确认空间
                # measured=side_bars_offset(高点在窗口内的相对位置 = 距窗口左端的根数)
                # 判据: offset>=min_side_bars 通过; <min_side_bars 失败, 高点太靠窗口起点, 尚不能算稳定极值
                if self.on_gate is not None:
                    self.on_gate(GateFailure(
                        failure_event_window=(current_idx, current_idx),
                        start_idx=current_idx, gate_idx=current_idx,
                        anchor_bar=current_idx,
                        gate_name='peak_side_bars_insufficient',
                        stream="pk",   # 多流化:gate failure 归属 pk 流(gate_collector 按流路由)
                        measured=MeasuredKindAware(kind='side_bars_offset', value=max_local_idx, label='峰-窗首侧翼'),
                        threshold=self.min_side_bars,
                        op='>=', threshold_param='min_side_bars',
                        evaluation_lookback=self._eval_lookback(current_idx),
                        symbol=current_symbol.get() or '',
                    ))
            elif max_local_idx >= len(measures) - self.min_side_bars:
                # gate: peak_side_bars_insufficient(尾侧) · 候选高点距扫描窗口右端是否留出足够的确认空间
                # measured=side_bars_offset(距窗口右端的根数 = len(measures) - 1 - max_local_idx)
                # 判据: offset>=min_side_bars 通过; <min_side_bars 失败, 高点太靠窗口末端, 后续可能被新高覆盖
                if self.on_gate is not None:
                    self.on_gate(GateFailure(
                        failure_event_window=(current_idx, current_idx),
                        start_idx=current_idx, gate_idx=current_idx,
                        anchor_bar=current_idx,
                        gate_name='peak_side_bars_insufficient',
                        stream="pk",   # 多流化:gate failure 归属 pk 流(gate_collector 按流路由)
                        measured=MeasuredKindAware(
                            kind='side_bars_offset',
                            value=len(measures) - 1 - max_local_idx,
                            label='峰-窗尾侧翼',
                        ),
                        threshold=self.min_side_bars,
                        op='>=', threshold_param='min_side_bars',
                        evaluation_lookback=self._eval_lookback(current_idx),
                        symbol=current_symbol.get() or '',
                    ))
            else:
                peak_global_idx = window_start + max_local_idx
                # 已存在
                already_active = any(p.peak_idx == peak_global_idx for p in self._active_peaks)
                if already_active:
                    # gate: peak_already_active · 新识别到的高点是否已在候选高点集合里
                    # measured=peak_idx(候选高点的全局索引 = window_start + max_local_idx)
                    # 判据: 集合中未包含相同索引的高点通过; 已存在则失败(去重, 避免同一根被反复识别)
                    if self.on_gate is not None:
                        self.on_gate(GateFailure(
                            failure_event_window=(current_idx, current_idx),
                            start_idx=current_idx, gate_idx=current_idx,
                            anchor_bar=current_idx,
                            gate_name='peak_already_active',
                            stream="pk",   # 多流化:gate failure 归属 pk 流(gate_collector 按流路由)
                            measured=MeasuredKindAware(kind='peak_idx', value=peak_global_idx, label='已存在peak索引'),
                            threshold=None,
                            op=None, threshold_param=None,
                            evaluation_lookback=self._eval_lookback(current_idx),
                            symbol=current_symbol.get() or '',
                        ))
                else:
                    window_min_low = min(lows)
                    if window_min_low <= 0:
                        # gate: peak_no_local_max(除零守卫) · 扫描窗口内最低价是否有效, 可作相对高度的分母
                        # measured=window_min_low(窗口内所有 low 的最小值)
                        # 判据: window_min_low>0 通过; <=0 失败, 除零或负价, 相对高度无意义
                        if self.on_gate is not None:
                            self.on_gate(GateFailure(
                                failure_event_window=(current_idx, current_idx),
                                start_idx=current_idx, gate_idx=current_idx,
                                anchor_bar=current_idx,
                                gate_name='peak_no_local_max',
                                stream="pk",   # 多流化:gate failure 归属 pk 流(gate_collector 按流路由)
                                measured=MeasuredKindAware(kind='window_min_low', value=window_min_low, label='窗口最低价'),
                                threshold=0,
                                op='>', threshold_param=None,
                                evaluation_lookback=self._eval_lookback(current_idx),
                                symbol=current_symbol.get() or '',
                            ))
                    else:
                        relative_height = (max_measure - window_min_low) / window_min_low
                        if relative_height < self.min_relative_height:
                            # gate: peak_relative_height_insufficient · 高点相对窗口内最低价的抬升幅度是否达到门槛
                            # measured=relative_height((max_measure - window_min_low) / window_min_low)
                            # 判据: relative_height>=min_relative_height 通过; 否则失败, 高点太平, 不算有意义的极值
                            if self.on_gate is not None:
                                self.on_gate(GateFailure(
                                    failure_event_window=(current_idx, current_idx),
                                    start_idx=current_idx, gate_idx=current_idx,
                                    anchor_bar=current_idx,
                                    gate_name='peak_relative_height_insufficient',
                                    stream="pk",   # 多流化:gate failure 归属 pk 流(gate_collector 按流路由)
                                    measured=MeasuredKindAware(kind='relative_height', value=relative_height, label='相对高度'),
                                    threshold=self.min_relative_height,
                                    op='>=', threshold_param='min_relative_height',
                                    evaluation_lookback=self._eval_lookback(current_idx),
                                    symbol=current_symbol.get() or '',
                                ))
                        else:
                            # 算 volume_peak (vol_ratio at peak idx)
                            if self._vol_ratio_series is not None:
                                vp = self._vol_ratio_series.iloc[peak_global_idx]
                                volume_peak = float(vp) if not pd.isna(vp) else 0.0
                            else:
                                volume_peak = 0.0

                            # peak-peak supersede 抽到 _register_peak(convex/bear 共用,
                            # 单一真源):新 peak 显著高于(>peak_supersede_threshold) 旧 peak 时,
                            # 旧 peak 被淘汰,防止低位老 peak 长期残留、被后续大涨"一锅端"成
                            # 几十个 broken_peak_ids。对比锚定旧 peak 的当前(elevated) price
                            # ——dev 同实现。
                            peak = PeakEvent(
                                start_idx=current_idx, end_idx=current_idx, confirm_idx=current_idx,
                                kind="convex",
                                peak_idx=peak_global_idx,   # 峰 bar(窗口 argmax);登记 bar = current_idx
                                price=max_measure,
                                original_price=None,        # 首次抬升前为 None(与旧 Peak 语义一致)
                                relative_height=relative_height,
                                volume_peak=volume_peak,
                            )
                            self._register_peak(peak, out)

        # ── bear 检测(convex 之后,写死顺序) ──
        # 看 bar i-1(与凸点窗口口径一致:只看当根之前已确认的 bar)。大阴线显著性
        # 来自当根形态,无需侧翼、不受窗口热身期限制。bear_drop=None 时整个 bear
        # 检测禁用(默认 OFF,Ruling A:仅显式 ON 的 app 启用)。
        # 同 bar 冲突时序(Ruling B,已接受,删死检查):bear 在 current_idx=prev+1
        # 先到(大阴线当根即可登记,不受侧翼限制);convex 需 current_idx>=prev+
        # min_side_bars+1 后到(峰需尾侧 min_side_bars 确认)→ 同时满足 argmax+
        # 大阴线的 bar 在 convex 后到时已被 already_active(peak_idx==prev)抑制,
        # 标为 bear(bear-wins)。
        if self.bear_drop is not None and current_idx >= 1:
            prev = current_idx - 1
            o = df["open"].iat[prev]; c = df["close"].iat[prev]
            drop = (o - c) / o if o else 0.0
            if drop >= self.bear_drop:
                window_low = min(df["low"].iloc[max(0, current_idx - self.total_window): current_idx])
                rel_h = (df["high"].iat[prev] - window_low) / window_low if window_low > 0 else 0.0
                if rel_h >= self.bear_min_rh:
                    bear = PeakEvent(
                        start_idx=current_idx, end_idx=current_idx, confirm_idx=current_idx,
                        kind="bear", peak_idx=prev,
                        price=df["high"].iat[prev],
                        relative_height=rel_h)
                    self._register_peak(bear, out)
        return tuple(out)
