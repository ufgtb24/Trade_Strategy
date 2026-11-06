"""new_step 专用识别器——从 K 线直接找「旧平台 → 一两根大阳线的阶跃 → 新平台」，在新平台上
每天产一个截到当天的复合事件，买点是它的 today 段。

形状偏见只属于 new_step，不进 `path2/atoms`，别拿它去做别的 pattern。

本模块只切段、算字段，不下任何够不够格的判断；阈值全在
`path2_apps/new_step/dag_spec.py` 的 where。判据、字段表、失效边界见
`PlateauDetector` 与各事件类的 docstring。

公开内容：
  PlateauDetector   识别器（只吃 K 线，单流，产 PlateauEvent）
  PlateauEvent      复合事件（node plateau），四个子段槽 old / step / new / today
  OldPlatform       旧平台段（node old_plat）
  Step              阶跃段（node step）
  NewPlatform       新平台段（node new_plat）
  Today             当天（node today，点事件，买点）
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Iterator, List, Optional

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

from path2.core import Event
from path2.dag.gate_failure import GateFailure, MeasuredKindAware
from path2.debug import current_symbol


@dataclass(frozen=True)
class OldPlatform(Event):
    """旧平台段：阶跃起点 s 之前固定 L 根 `[s-L, s-1]`（L = old_window，不往回找起点）。

    confirm_idx = end_idx = s-1（回顾型：字段只用到 s-1 及以前的数据）。
    同一个 s 只造一个对象，由该阶跃所有前缀、所有天的 plateau 实例共用。

    输出字段：
    - level:    本段收盘价中位数（「旧平台的价位」，height / keep_ratio / 跌回判据都以它为基准）
    - range:    ln(本段最高收盘 / 本段最低收盘)
    - sigma:    median(|r|) over 本段，r_i = ln(close_i / close_{i-1})；与开段时的 σ_s 同窗同值
    - vol_mean: 本段平均成交量（Step.vol_ratio 的分母）
    """
    level: float
    range: float
    sigma: float
    vol_mean: float


@dataclass(frozen=True)
class Step(Event):
    """阶跃段：一段阶跃的一个前缀 `[s, e]`。

    confirm_idx = end_idx = e。同一前缀只造一个对象，由该前缀所有天的 plateau 实例共用。

    输出字段：
    - bars:      本段根数 e - s + 1
    - rise:      close_e / close_{s-1} - 1（本段累计涨幅，简单收益）
    - max_ret:   段内最大的 r
    - vs_left:   max_ret / old.sigma（阶跃比左侧旧平台强多少倍；old.sigma 恒 > 0）
    - vol_ratio: 段内最大成交量 / old.vol_mean；旧平台平均成交量 ≤ 0（如全 0）时为 None，
                 where 遇 None 判不满足，即「平台交界放量」不成立
    """
    bars: int
    rise: float
    max_ret: float
    vs_left: float
    vol_ratio: Optional[float]


@dataclass(frozen=True)
class NewPlatform(Event):
    """新平台段：阶跃前缀 [s, e] 之后到当天前一根 `[e+1, t-1]`（至少 1 根）。

    confirm_idx = end_idx = t-1。逐 (前缀, t) 新造，同一前缀的各天互相嵌套。

    输出字段：
    - bars:  本段根数 t - 1 - e
    - low:   本段最低收盘
    - range: ln(本段最高收盘 / 本段最低收盘)；只有 1 根时为 0
    - sigma: median(|r|) over 本段（含 r_{e+1}，即阶跃末根到新平台首根那一跳）
    """
    bars: int
    low: float
    range: float
    sigma: float


@dataclass(frozen=True)
class Today(Event):
    """当天：`[t, t]` 点事件，确认型（confirm_idx = start_idx = t），是 new_step 的买点。

    同一根 K 线只造一个对象，跨阶跃、跨前缀的 plateau 实例共用。

    输出字段：
    - body: close_t / open_t - 1（> 0 即收阳）
    """
    is_point = True   # 点几何承诺,供 PatternSpec._validate_render_grid 反射
    body: float


@dataclass(frozen=True)
class PlateauEvent(Event):
    """复合事件：一个阶跃前缀 [s, e] 在新平台上的某一天 t，截到 t 为止的证据。

    跨度 `[s-L, t]`，confirm_idx = end_idx = t（回顾型：字段只用到 t 及以前的数据）。
    跨段比较的量放这里，单段自己的量放子段。height 统一为 ln(close_e / old.level)，恒 > 0
    （≤ 0 的前缀不产，见 PlateauDetector 的 on_gate）。

    输出字段：
    - days:           t - e（当天距阶跃末根的根数，最小 2）
    - height:         ln(close_e / old.level)（阶跃把价位抬高了多少）
    - old_flat_ratio: old.range / height（旧平台振幅相对阶跃高度）
    - vs_right:       step.max_ret / new.sigma（阶跃比右侧新平台强多少倍）；new.sigma = 0 时
                      为 None，where 遇 None 判不满足，即「阶跃比右侧强」不成立（不用 inf：
                      JSON 序列化不了）
    - calm_ratio:     new.range / height（新平台振幅相对阶跃高度）
    - keep_ratio:     ln(min close over [e+1, t] / old.level) / height（新平台连同当天的最低
                      收盘守住了阶跃高度的几成；1 = 一点没吐，0 = 吐回旧平台价位）
    - vs_high:        close_t / max high over [s, t-1]（当天收盘相对阶跃以来最高价；< 1 即没追涨）

    子段槽（child_slots 无条件返回四槽，槽值是单事件、永不为 None；字段名与槽名同名）：
    - old:   OldPlatform（node old_plat）
    - step:  Step（node step）
    - new:   NewPlatform（node new_plat）
    - today: Today（node today），买点 = `plateau.today`
    """
    days: int
    height: float
    old_flat_ratio: float
    vs_right: Optional[float]
    calm_ratio: float
    keep_ratio: float
    vs_high: float
    old: OldPlatform
    step: Step
    new: NewPlatform
    today: Today

    def child_slots(self):
        return {"old": self.old, "step": self.step, "new": self.new, "today": self.today}

    def child(self, name: str):
        if name == "old":
            return self.old
        if name == "step":
            return self.step
        if name == "new":
            return self.new
        if name == "today":
            return self.today
        raise KeyError(name)


class PlateauDetector:
    """new_step 专用——从 K 线直接找「旧平台 → 一两根大阳线的阶跃 → 新平台」，在新平台上
    每天产一个截到当天的复合事件，买点是它的 today 段。

    只吃 K 线（open / high / close / volume），不消费任何流；单流，产 PlateauEvent。
    detector 只切段、算字段，不下任何够不够格的判断，阈值全在
    `path2_apps/new_step/dag_spec.py` 的 where。

    记 r_i = ln(close_i / close_{i-1})，L = old_window。核心判据：
      1. 阶跃：i 从 L+1 起逐根扫。i 不在阶跃里时算 σ_i = median(|r|) over [i-L, i-1]；
         σ_i > 0 且 r_i ≥ strong_k·σ_i 即开段，起点 s、记 σ_s。之后的根 r ≥ strong_k·σ_s
         且段长 < max_step_bars 就并入；第一根不满足即收段，段尾 e'。扫描从 e'+1 继续
         （e'+1 不并入本段，但可以开下一段）。
      2. 段内每个前缀 [s, e]（e = s..e'）各是一个阶跃候选（站在 e+1 那天只知道阶跃走到了 e）。
      3. 旧平台 = 固定 [s-L, s-1]（不往回找起点）。
      4. 每个前缀：height = ln(close_e / old.level)；height ≤ 0 时 emit gate
         `step_not_above_old` 并跳过这个前缀。否则当天 t 从 e+2 到 min(e+max_days, n-1)：
         先判 close_t ≤ old.level 则这一族结束（不产 t 及以后）；否则产一个实例：
         新平台 = [e+1, t-1]，当天 = [t, t]，plateau 跨度 [s-L, t]。阶跃后第一天（e+1）
         不产（新平台至少 1 根）。当天 t 自己是大阳线（甚至开了下一段阶跃）也照样是这个
         前缀的新平台上的一天。
      5. 对象共用：同一 s 的 OldPlatform、同一前缀的 Step、同一根 K 线的 Today 各只造
         一个对象，跨实例共用（引擎按对象只标注一次，带子不随天数叠层）；NewPlatform 与
         PlateauEvent 逐 (前缀, t) 新造。
      6. 全部实例收集后按 (end_idx, start_idx) 排序再 yield。
      7. 坏数据跳过，不产出 NaN 字段：
         - 价格坏 = 该根 open / high / close 任一非有限或 ≤ 0；量坏 = volume 非有限或 < 0。
         - 开段时回看窗 [i-L-1, i] 价格须全好、[i-L, i] 量须全好，否则这根不开段；
         - 并入的根价格、量都须好，否则收段；
         - e+1 价格坏则该前缀不产；当天 t 价格坏则这一族到此为止（之后的实例都要读它）。
         新平台与当天的成交量不参与任何字段，量坏不影响它们。

    输出字段（height 统一为 ln(close_e / old.level)；逐项口径见各事件类 docstring）：

      类（node）             跨度 / confirm     字段
      OldPlatform(old_plat)  [s-L, s-1] / end   level 收盘中位数；range = ln(最高收盘/最低收盘)；
                                                sigma = median(|r|)；vol_mean 平均成交量
      Step(step)             [s, e] / end       bars；rise = close_e/close_{s-1} − 1；max_ret 段内最大 r；
                                                vs_left = max_ret / old.sigma；
                                                vol_ratio = 段内最大成交量 / old.vol_mean（≤0 时 None）
      NewPlatform(new_plat)  [e+1, t-1] / end   bars；low 最低收盘；range = ln(最高收盘/最低收盘)；
                                                sigma = median(|r|)
      Today(today，点事件)   [t, t] / start     body = close_t/open_t − 1
      PlateauEvent(plateau)  [s-L, t] / end     days = t − e；height；old_flat_ratio = old.range / height；
                                                vs_right = step.max_ret / new.sigma（new.sigma = 0 时 None）；
                                                calm_ratio = new.range / height；
                                                keep_ratio = ln(min close over [e+1, t] / old.level) / height；
                                                vs_high = close_t / max high over [s, t-1]

    None 的语义：Step.vol_ratio、PlateauEvent.vs_right 为 None 时 where 判不满足（不用 inf，
    JSON 序列化不了）。

    on_gate（attempt = 每个阶跃前缀）：唯一 gate `step_not_above_old`——前缀收盘没高过
    旧平台价位（height ≤ 0）。族尾（跌回旧平台、到 max_days、坏数据截断）是正常结束，不 emit。

    失效边界：
    - 数据开头不足 L+1 根不产（最早的阶跃起点是第 L+1 根）。
    - 旧平台成交量全 0 时 vol_ratio 为 None，平台交界放量判不成立。
    - 中间夹小阳线、分几天爬上去的阶跃会被切成几级（每级各自一段、各自一个旧平台）。
    - 旧平台窗里含更早一级小阶跃时 old_flat_ratio 偏大。

    构造参数（全部结构型，除 max_days 为过滤型）：
    - old_window:    L，旧平台根数，也是 σ_i 的回看窗
    - strong_k:      开段 / 并入的倍数（取机制值，强度交给 where）
    - max_step_bars: 一段阶跃最多几根
    - max_days:      当天距阶跃末根最多几根（t ≤ e + max_days）
    """
    has_debug_hooks: ClassVar[bool] = False
    event_cls = PlateauEvent
    on_gate = None   # Detector.on_gate protocol 静态声明,运行时不自动继承;默认 None = 生产路径无开销

    # 过滤型构造参数声明(tune-gates multivar 协议):param → (事件字段, op)。
    # 语义:以该参数最松值构造,事后按 `getattr(event, field) op value` 过滤,与直接以 value
    # 构造得到的事件集逐事件相等——max_days 只在 emit 处把关(t ≤ e + max_days ⇔ days ≤ max_days),
    # 不参与切段、跌回判据与 gate,故成立。on_gate 诊断侧信道同样不受 max_days 影响。
    filter_params: ClassVar[dict[str, tuple[str, str]]] = {"max_days": ("days", "<=")}

    def __init__(self, old_window: int, strong_k: float, max_step_bars: int, max_days: int):
        if old_window < 1:
            raise ValueError(f"old_window 须 ≥ 1,得到 {old_window}")
        if max_step_bars < 1:
            raise ValueError(f"max_step_bars 须 ≥ 1,得到 {max_step_bars}")
        self.old_window = old_window
        self.strong_k = strong_k
        self.max_step_bars = max_step_bars
        self.max_days = max_days

    def detect(self, df: pd.DataFrame) -> Iterator[PlateauEvent]:
        close = df["close"].to_numpy(dtype=float)
        open_ = df["open"].to_numpy(dtype=float)
        high = df["high"].to_numpy(dtype=float)
        vol = df["volume"].to_numpy(dtype=float)
        n = len(close)
        L = self.old_window
        if n < L + 2:   # 最早的阶跃起点是第 L+1 根
            return

        with np.errstate(invalid="ignore", divide="ignore", over="ignore"):
            price_ok = (np.isfinite(close) & (close > 0) & np.isfinite(open_) & (open_ > 0)
                        & np.isfinite(high) & (high > 0))
            vol_ok = np.isfinite(vol) & (vol >= 0)
            r = np.full(n, np.nan)
            pair_ok = price_ok[1:] & price_ok[:-1]
            r[1:] = np.where(pair_ok, np.log(np.where(pair_ok, close[1:] / close[:-1], 1.0)), np.nan)
        abs_r = np.abs(r)
        # win_med[j] = median(|r|) over [j, j+L-1];σ_i = win_med[i-L]。坏窗得 NaN,开段前先查窗干净。
        win_med = np.median(sliding_window_view(abs_r, L), axis=1)
        price_bad_cum = np.concatenate(([0], np.cumsum(~price_ok)))
        vol_bad_cum = np.concatenate(([0], np.cumsum(~vol_ok)))

        def clean(cum, a: int, b: int) -> bool:   # [a, b] 闭区间内无坏根
            return cum[b + 1] - cum[a] == 0

        out: List[PlateauEvent] = []
        today_cache: dict[int, Today] = {}
        k = self.strong_k
        i = L + 1
        while i < n:
            if not (clean(price_bad_cum, i - L - 1, i) and clean(vol_bad_cum, i - L, i)):
                i += 1
                continue
            sigma_s = float(win_med[i - L])
            if not (sigma_s > 0 and r[i] >= k * sigma_s):
                i += 1
                continue
            s = i
            seg_end = s
            thr = k * sigma_s
            while (seg_end + 1 < n and seg_end - s + 1 < self.max_step_bars
                   and price_ok[seg_end + 1] and vol_ok[seg_end + 1] and r[seg_end + 1] >= thr):
                seg_end += 1
            self._emit_segment(s, seg_end, close, high, open_, vol, r, abs_r, price_ok,
                               out, today_cache)
            i = seg_end + 1   # e'+1 不并入本段,但可以开下一段

        out.sort(key=lambda ev: (ev.end_idx, ev.start_idx))
        yield from out

    def _emit_segment(self, s, seg_end, close, high, open_, vol, r, abs_r, price_ok,
                      out, today_cache) -> None:
        """一段阶跃 [s, seg_end]:造旧平台,逐前缀判 height、逐天产 plateau 实例。"""
        n = len(close)
        L = self.old_window
        lo = s - L
        oc = close[lo:s]
        old = OldPlatform(
            start_idx=lo, end_idx=s - 1, confirm_idx=s - 1,
            level=float(np.median(oc)),
            range=float(np.log(oc.max() / oc.min())),
            sigma=float(np.median(abs_r[lo:s])),
            vol_mean=float(vol[lo:s].mean()),
        )
        for e in range(s, seg_end + 1):
            height = float(np.log(close[e] / old.level))
            if height <= 0:
                # gate: step_not_above_old · 阶跃前缀收盘是否高过旧平台价位
                # measured=log_ratio(height = ln(close_e / old.level))
                # 判据: height>0 通过,继续找新平台; height<=0 失败,跳过这个前缀
                if self.on_gate is not None:
                    self.on_gate(GateFailure(
                        failure_event_window=(s, e),
                        start_idx=s,
                        gate_idx=e,
                        anchor_bar=e,
                        gate_name="step_not_above_old",
                        measured=MeasuredKindAware(kind="log_ratio", value=height, label="height"),
                        threshold=0.0,
                        op=">", threshold_param=None,
                        evaluation_lookback=(lo, s - 1),
                        symbol=current_symbol.get() or "",
                        stream=None,
                    ))
                continue
            max_ret = float(r[s:e + 1].max())
            vmax = float(vol[s:e + 1].max())
            step = Step(
                start_idx=s, end_idx=e, confirm_idx=e,
                bars=e - s + 1,
                rise=float(close[e] / close[s - 1] - 1.0),
                max_ret=max_ret,
                vs_left=max_ret / old.sigma,
                vol_ratio=(vmax / old.vol_mean) if old.vol_mean > 0 else None,
            )
            if e + 1 >= n or not price_ok[e + 1]:
                continue
            # 滚动量:新平台 [e+1, t-1] 的最低/最高收盘、[s, t-1] 的最高价;产完 t 再把 t 并进来
            new_min = new_max = float(close[e + 1])
            high_max = float(high[s:e + 2].max())
            for t in range(e + 2, min(e + self.max_days, n - 1) + 1):
                if not price_ok[t]:
                    break   # 坏数据截断:之后的实例都要读这根
                ct = float(close[t])
                if ct <= old.level:
                    break   # 整级台阶吐回旧平台价位,这一族到此为止
                new = NewPlatform(
                    start_idx=e + 1, end_idx=t - 1, confirm_idx=t - 1,
                    bars=t - 1 - e,
                    low=new_min,
                    range=float(np.log(new_max / new_min)),
                    sigma=float(np.median(abs_r[e + 1:t])),
                )
                today = today_cache.get(t)
                if today is None:
                    today = Today(start_idx=t, end_idx=t, confirm_idx=t,
                                  body=float(close[t] / open_[t] - 1.0))
                    today_cache[t] = today
                out.append(PlateauEvent(
                    start_idx=lo, end_idx=t, confirm_idx=t,
                    days=t - e,
                    height=height,
                    old_flat_ratio=old.range / height,
                    vs_right=(max_ret / new.sigma) if new.sigma > 0 else None,
                    calm_ratio=new.range / height,
                    keep_ratio=float(np.log(min(new_min, ct) / old.level)) / height,
                    vs_high=ct / high_max,
                    old=old, step=step, new=new, today=today,
                ))
                new_min = min(new_min, ct)
                new_max = max(new_max, ct)
                high_max = max(high_max, float(high[t]))
