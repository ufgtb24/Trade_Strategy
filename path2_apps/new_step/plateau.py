"""new_step 专用识别器——从 K 线直接找「旧平台 → 一串最高价连续抬高的阶跃 → 新平台」，在新平台上
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
    同一个 s 只造一个对象，由这次阶跃各版本、所有天的 plateau 实例共用。

    输出字段：
    - level:    本段收盘价中位数（「旧平台的价位」，height / keep_ratio 都以它为基准）
    - range:    ln(本段最高收盘 / 本段最低收盘)
    - sigma:    波动 over 本段 |r|，r_i = ln(close_i / close_{i-1})：取中位数，中位数为 0 时（价格卡在
                固定档位、过半根收盘一分不动）改取平均数；恒 > 0（开段、往前找时都要求旧平台波动 > 0，
                见 PlateauDetector 判据 1、2）
    - vol_mean: 本段平均成交量（Step.vol_ratio 的分母）
    """
    level: float
    range: float
    sigma: float
    vol_mean: float


@dataclass(frozen=True)
class Step(Event):
    """阶跃段：一次阶跃在某个版本下的 `[s, e]`（e = 这个版本里最高价最后一次抬高的那根）。

    confirm_idx = end_idx = e。同一版本只造一个对象，由该版本所有天的 plateau 实例共用。
    停顿后续上的阶跃，段内含停顿的那几根。

    输出字段：
    - bars:      本段根数 e - s + 1
    - rise:      本段最高收盘 / close_{s-1} - 1（阶跃把价位抬了多少，简单收益，按收盘）
    - max_ret:   段内最大的 r
    - vs_left:   max_ret / old.sigma（阶跃比左侧旧平台强多少倍）
    - vol_ratio: 段内最大成交量 / old.vol_mean；旧平台平均成交量 ≤ 0（如全 0）时为 None，
                 where 遇 None 判不满足，即「平台交界放量」不成立
    - vol_mean:  段内平均成交量（段内的根量都是好的，切段时已查；只作诊断）
    - vol_max:   段内最大成交量（「阶跃阶段的量」，新平台缩不缩量拿它比：往前找起点会吸进量小的
                 根，平均量会被稀释，最大量不受影响）
    """
    bars: int
    rise: float
    max_ret: float
    vs_left: float
    vol_ratio: Optional[float]
    vol_mean: float
    vol_max: float


@dataclass(frozen=True)
class NewPlatform(Event):
    """新平台段：阶跃 [s, e] 之后到当天前一根 `[e+1, t-1]`（至少 1 根）。

    confirm_idx = end_idx = t-1。逐 (版本, t) 新造，同一版本的各天互相嵌套。

    输出字段：
    - bars:         本段根数 t - 1 - e
    - low:          本段最低收盘
    - range:        ln(本段最高收盘 / 本段最低收盘)；只有 1 根时为 0（从新平台第一天累计，只作诊断）
    - recent_range: ln(最高收盘 / 最低收盘) over 本段最后 min(calm_window, bars) 根（「波动小」读它，
                    只看最近一段，早期晃过一次之后站稳了还能过）
    - sigma:        波动 over 本段 |r|（含 r_{e+1}，即阶跃末根到新平台首根那一跳）；口径同旧平台：
                    中位数，中位数为 0 时改取平均数
    - vol_mean:     本段量好的根的平均成交量；一根量好的都没有时为 None
    """
    bars: int
    low: float
    range: float
    recent_range: float
    sigma: float
    vol_mean: Optional[float]


@dataclass(frozen=True)
class Today(Event):
    """当天：`[t, t]` 点事件，确认型（confirm_idx = start_idx = t），是 new_step 的买点。

    同一根 K 线只造一个对象，跨阶跃、跨版本的 plateau 实例共用。

    输出字段：
    - body: close_t / open_t - 1（> 0 即收阳）
    """
    is_point = True   # 点几何承诺,供 PatternSpec._validate_render_grid 反射
    body: float


@dataclass(frozen=True)
class PlateauEvent(Event):
    """复合事件：一次阶跃的某个版本 [s, e] 在新平台上的某一天 t，截到 t 为止的证据。

    跨度 `[s-L, t]`，confirm_idx = end_idx = t（回顾型：字段只用到 t 及以前的数据）。
    跨段比较的量放这里，单段自己的量放子段。height 统一为 ln(阶跃最高收盘 / old.level)，恒 > 0
    （≤ 0 的版本不产，见 PlateauDetector 的 on_gate）。

    输出字段：
    - days:           t - e（当天距阶跃末根的根数，最小 2）
    - height:         ln(max close over [s, e] / old.level)（阶跃把价位抬高了多少，按收盘）
    - old_flat_ratio: old.range / height（旧平台振幅相对阶跃高度）
    - vs_right:       step.max_ret / new.sigma（阶跃比右侧新平台强多少倍）；new.sigma = 0 时
                      为 None，where 遇 None 判不满足，即「阶跃比右侧强」不成立（不用 inf：
                      JSON 序列化不了）
    - calm_ratio:     new.recent_range / height（新平台最近一段的振幅相对阶跃高度）
    - keep_ratio:     ln(close_t / old.level) / height（当天收盘守住了阶跃高度的几成；1 = 一点没吐，
                      0 = 回到旧平台价位，< 0 = 跌破旧平台价位）。只读当天，吐回去之后再站回来还能过
    - vs_high:        close_t / max high over [s, t-1]（当天收盘相对阶跃以来最高价；< 1 即没追涨）
    - overhead:       阶跃之前的前高 / close_t：前高 = max high over [lo, s-1] 中价格好的根，
                      lo = min(max(0, t - overhead_window), s-1)（窗口随当天往后挪，前高过了
                      overhead_window 根就移出去；窗口至少含 s-1）。> 1 即当天收盘上方压着近期前高。
                      新平台自己的高点不算：新平台冲过阶跃顶再回落是台阶式上行里的常态（正样本
                      QBTS 2024-11、KULR 2024-12 都是），算进来会把它们一起挡掉
    - vol_shrink:     new.vol_mean / step.vol_max（新平台平均量相对阶跃里量最大那天）；新平台没有
                      好量或阶跃最大量 ≤ 0 时为 None（where 判不满足）
    - low_age:        距新平台最近一次「创新低」的根数 t - j：j 取 [e+2, t] 里收盘严格低于
                      [e+1, j-1] 全部收盘的最后一根（新平台第一天本身不算创新低；含当天，当天
                      创新低时为 0）；新平台从没创过新低时为 None
    - dump_ratio:     阶跃涨幅被快速吃掉的最大比例（派发）。对 u ∈ [e+1, t]：peak_u = max close over
                      [s, u]（含新平台上冲出的更高收盘），recent_u = max close over [max(s, u-dump_window), u]；
                      eaten_u = ln(recent_u / close_u) / ln(peak_u / close_{s-1})——最近 dump_window 根之内
                      跌掉的部分占阶跃整个涨幅的几成（慢慢阴跌回去的，每一段都跌得少，读数小；在高位横几天
                      再急跌的照样算）。取 u 里最大；peak_u 不高于 close_{s-1} 的 u 不算，一个都不算时为
                      None。只增不减：一旦过了门槛，这一版往后各天都过（invalidation，用户明说）

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
    overhead: float
    vol_shrink: Optional[float]
    low_age: Optional[int]
    dump_ratio: Optional[float]
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


def _sigma(abs_r: np.ndarray) -> float:
    """一段 |r| 的波动:中位数;中位数为 0(价格卡在固定档位、过半根收盘一分不动)时改取平均数。
    开段的 σ_i、OldPlatform.sigma、NewPlatform.sigma 共用这一个算法。"""
    m = float(np.median(abs_r))
    return m if m != 0 else float(np.mean(abs_r))


class PlateauDetector:
    """new_step 专用——从 K 线直接找「旧平台 → 一串最高价连续抬高的阶跃 → 新平台」，在新平台上
    每天产一个截到当天的复合事件，买点是它的 today 段。

    只吃 K 线（open / high / close / volume），不消费任何流；单流，产 PlateauEvent。
    detector 只切段、算字段，不下任何够不够格的判断，阈值全在
    `path2_apps/new_step/dag_spec.py` 的 where。

    记 r_i = ln(close_i / close_{i-1})，L = old_window；「第 b 根抬高」= high_b > high_{b-1}（两根价格
    都好）。阶跃 = 一串最高价连续抬高的 K 线，最高价一回落就完成；判断阶跃在哪天结束用最高价，
    阶跃把价位抬了多少用收盘。核心判据：
      1. 开段：i 从 L+1 起逐根扫。算 σ_i = median(|r|) over [i-L, i-1]（中位数为 0 时改取同窗
         mean(|r|)）；σ_i > 0 且 r_i ≥ strong_k·σ_i 即在 i 开一次阶跃，记 σ = σ_i。
      2. 起点往前找：i 自己抬高时，沿「抬高」一根根往前，直到前一根没抬高为止，起点 s 是这串里
         最早的那根（i 自己没抬高时 s = i）。往前找要求新纳入的那根量好、它的旧平台回看窗干净且
         波动 > 0（不然旧平台波动为 0，「比左侧强」没法算），且 s ≥ L+1。
      3. 往后到最高价回落：从 i 起，下一根抬高（且价格、量都好）就并入，第一根没抬高的根即 e+1，
         阶跃 [s, e] 完成（第一个版本）。
      4. 停顿后续上：e+1 起的停顿里（停顿至少 1 根、至多 max_pause 根，即 j ∈ [e+2, e+1+max_pause]），
         第一根 r_j ≥ strong_k·σ 且 high_j 高过 [s, e] 最高价的 j 就是续上：从 j 起再按判据 3 往后到
         最高价回落，得到下一个版本 [s, e2]（含停顿那几根）。停顿里有坏根就不再找。重复直到找不到。
         同一次阶跃只有一个起点；新版本只往后覆盖：停顿那几天照旧按上一个版本产，从 j 起换版本。
      5. 每个版本：height = ln(max close over [s, e] / old.level)；height ≤ 0 时 emit gate
         `step_not_above_old`，这个版本不产。否则当天 t 从 e+2 到 min(e+max_days, n-1, 下一版本的
         j-1)：每天产一个实例，新平台 = [e+1, t-1]，当天 = [t, t]，plateau 跨度 [s-L, t]。阶跃完成
         那天（e+1）不产（新平台至少 1 根）。
      6. 版本总跨度 e - s + 1 > max_step_bars：第一个版本超了就 emit gate `step_too_long`、这次阶跃
         整个不产；续上之后超了，这次阶跃从续上那天起不再产（上一个版本只产到续上前一天，与数据只到
         续上那几天时的结果一致），扫描从这串抬高的末根之后继续。
      7. 扫描从最后一个版本的 e + max_pause + 2 继续：停顿窗里的根只当续上的候选，不另开阶跃
         （这条只看停顿窗、不看后来有没有续上，保证因果）。
      8. 对象共用：同一 s 的 OldPlatform、同一版本的 Step、同一根 K 线的 Today 各只造一个对象，
         跨实例共用；NewPlatform 与 PlateauEvent 逐 (版本, t) 新造。全部实例按 (end_idx, start_idx)
         排序再 yield。
      9. 坏数据跳过，不产出 NaN 字段：
         - 价格坏 = 该根 open / high / close 任一非有限或 ≤ 0；量坏 = volume 非有限或 < 0。
         - 开段时回看窗 [i-L-1, i] 价格须全好、[i-L, i] 量须全好，否则这根不开段；
         - 并入阶跃的根价格、量都须好，否则阶跃在它前一根完成；
         - e+1 价格坏则该版本不产；当天 t 价格坏则该版本到此为止（之后的实例都要读它）。
         新平台的量只进 vol_mean（跳过量坏的根）；当天的量不参与任何字段。
         overhead 的前高只取价格好的根。

    输出字段（逐项口径见各事件类 docstring）：

      类（node）             跨度 / confirm     字段
      OldPlatform(old_plat)  [s-L, s-1] / end   level 收盘中位数；range = ln(最高收盘/最低收盘)；
                                                sigma = median(|r|)（为 0 时取 mean）；vol_mean 平均成交量
      Step(step)             [s, e] / end       bars；rise = 最高收盘/close_{s-1} − 1；max_ret 段内最大 r；
                                                vs_left = max_ret / old.sigma；
                                                vol_ratio = 段内最大成交量 / old.vol_mean（≤0 时 None）；
                                                vol_mean 段内平均成交量；vol_max 段内最大成交量
      NewPlatform(new_plat)  [e+1, t-1] / end   bars；low 最低收盘；range = ln(最高收盘/最低收盘)；
                                                recent_range = 最后 calm_window 根的 ln(最高收盘/最低收盘)；
                                                sigma = median(|r|)（为 0 时取 mean）；vol_mean（无好量时 None）
      Today(today，点事件)   [t, t] / start     body = close_t/open_t − 1
      PlateauEvent(plateau)  [s-L, t] / end     days = t − e；height = ln(阶跃最高收盘 / old.level)；
                                                old_flat_ratio = old.range / height；
                                                vs_right = step.max_ret / new.sigma（new.sigma = 0 时 None）；
                                                calm_ratio = new.recent_range / height；
                                                keep_ratio = ln(close_t / old.level) / height；
                                                vs_high = close_t / max high over [s, t-1]；
                                                overhead = 阶跃前前高 / close_t（窗口 overhead_window）；
                                                vol_shrink = new.vol_mean / step.vol_max；
                                                low_age = 距新平台最近一次严格创新低的根数（没创过为 None）；
                                                dump_ratio = 最近 dump_window 根内跌掉的部分占阶跃涨幅的最大比例

    None 的语义：Step.vol_ratio、PlateauEvent.vs_right、vol_shrink 为 None 时 where 判不满足（不用
    inf，JSON 序列化不了）；low_age 为 None 表示「新平台没创过新低」、dump_ratio 为 None 表示「没有
    快速回落」，where 要用 W.not_(…) 写才能让它们判满足。

    on_gate（attempt = 每次阶跃的每个版本）：
    - `step_not_above_old`：这个版本的最高收盘没高过旧平台价位（height ≤ 0）；
    - `step_too_long`：第一个版本的跨度就超过 max_step_bars。
    族尾（到 max_days、换到下一版本、坏数据截断）是正常结束，不 emit。

    失效边界：
    - 数据开头不足 L+1 根不产（最早的阶跃起点是第 L+1 根）。
    - 旧平台成交量全 0 时 vol_ratio 为 None，平台交界放量判不成立。
    - 旧平台 |r| 全为 0（收盘一根都没动过）时 σ 中位数、平均数都是 0，不开段。
    - 往前找只看最高价抬没抬高：猛涨前一两根小 K 线只要最高价比前一天高就会被算进阶跃（实测 13 只
      标注股约三分之一的阶跃往前多吸 1 根以上，其中近一半那根涨跌不到旧平台波动），阶跃的根数、
      平均量随之变化。
    - 停顿窗里够猛却没创新高的根既不算续上、也不另开阶跃。
    - 旧平台窗里含更早一次阶跃时 old_flat_ratio 偏大（旧平台固定取 L 根、不往回找起点）。

    构造参数：
    - old_window:      L，旧平台根数，也是 σ_i 的回看窗（结构型）
    - strong_k:        开段与续上的倍数（取机制值，强度交给 where）（结构型）
    - max_step_bars:   一次阶跃各版本的总跨度上限（防失控的机制值，结构型）
    - max_pause:       停顿最多几根仍可续上（结构型）
    - max_days:        当天距阶跃末根最多几根（t ≤ e + max_days；过滤型）
    - overhead_window: overhead 的前高从当天往前看多少根（字段窗口：只改字段值、不改事件集）
    - calm_window:     recent_range 看新平台最后多少根（字段窗口）
    - dump_window:     dump_ratio 看最近多少根之内的回落（字段窗口）
    """
    has_debug_hooks: ClassVar[bool] = False
    event_cls = PlateauEvent
    on_gate = None   # Detector.on_gate protocol 静态声明,运行时不自动继承;默认 None = 生产路径无开销

    # 过滤型构造参数声明(tune-gates multivar 协议):param → (事件字段, op)。
    # 语义:以该参数最松值构造,事后按 `getattr(event, field) op value` 过滤,与直接以 value
    # 构造得到的事件集逐事件相等——max_days 只在 emit 处把关(t ≤ e + max_days ⇔ days ≤ max_days),
    # 不参与切段、续上与 gate,故成立。on_gate 诊断侧信道同样不受 max_days 影响。
    filter_params: ClassVar[dict[str, tuple[str, str]]] = {"max_days": ("days", "<=")}

    def __init__(self, old_window: int, strong_k: float, max_step_bars: int, max_pause: int,
                 max_days: int, overhead_window: int, calm_window: int, dump_window: int):
        for name, v in (("old_window", old_window), ("max_step_bars", max_step_bars),
                        ("overhead_window", overhead_window), ("calm_window", calm_window)):
            if v < 1:
                raise ValueError(f"{name} 须 ≥ 1,得到 {v}")
        for name, v in (("max_pause", max_pause), ("dump_window", dump_window)):
            if v < 0:
                raise ValueError(f"{name} 须 ≥ 0,得到 {v}")
        self.old_window = old_window
        self.strong_k = strong_k
        self.max_step_bars = max_step_bars
        self.max_pause = max_pause
        self.max_days = max_days
        self.overhead_window = overhead_window
        self.calm_window = calm_window
        self.dump_window = dump_window

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
            up = np.zeros(n, dtype=bool)   # 第 b 根抬高:high_b > high_{b-1},两根价格都好
            up[1:] = pair_ok & (high[1:] > high[:-1])
        abs_r = np.abs(r)
        # win_med[j] = median(|r|) over [j, j+L-1];σ_i = win_med[i-L]。坏窗得 NaN,开段前先查窗干净。
        win_med = np.median(sliding_window_view(abs_r, L), axis=1)
        price_bad_cum = np.concatenate(([0], np.cumsum(~price_ok)))
        vol_bad_cum = np.concatenate(([0], np.cumsum(~vol_ok)))

        def clean(cum, a: int, b: int) -> bool:   # [a, b] 闭区间内无坏根
            return cum[b + 1] - cum[a] == 0

        def rise_to(b: int) -> int:   # 从 b 起往后并入抬高的根,返回最后一根
            while b + 1 < n and up[b + 1] and vol_ok[b + 1]:
                b += 1
            return b

        out: List[PlateauEvent] = []
        today_cache: dict[int, Today] = {}
        k = self.strong_k
        i = L + 1
        while i < n:
            if not (clean(price_bad_cum, i - L - 1, i) and clean(vol_bad_cum, i - L, i)):
                i += 1
                continue
            sigma = float(win_med[i - L])
            if sigma == 0:   # 价格卡档位:中位数为 0 时取同窗平均(与 OldPlatform.sigma 同一算法)
                sigma = _sigma(abs_r[i - L:i])
            if not (sigma > 0 and r[i] >= k * sigma):
                i += 1
                continue
            # 2. 起点往前找
            s = i
            if up[i]:
                while (s - 1 >= L + 1 and up[s - 1] and vol_ok[s - 1]
                       and clean(price_bad_cum, s - 1 - L - 1, s - 1)
                       and clean(vol_bad_cum, s - 1 - L, s - 1)
                       and _sigma(abs_r[s - 1 - L:s - 1]) > 0):
                    s -= 1
            # 3. 往后到最高价回落
            e = rise_to(i)
            if e - s + 1 > self.max_step_bars:
                self._gate(s, e, "step_too_long", float(e - s + 1), "bars",
                           float(self.max_step_bars), "<=", (s - L, s - 1))
                i = e + self.max_pause + 2
                continue
            # 4. 停顿后续上
            versions = [(e, None)]   # (版本末根, 续上那根;第一个版本为 None)
            tail = None              # 续上后太长:这次阶跃只产到续上前一天
            while True:
                top = float(high[s:e + 1].max())
                j_hit = None
                for j in range(e + 1, min(e + 1 + self.max_pause, n - 1) + 1):
                    if not (price_ok[j] and vol_ok[j]):
                        break
                    if j >= e + 2 and r[j] >= k * sigma and high[j] > top:
                        j_hit = j
                        break
                if j_hit is None:
                    break
                e2 = rise_to(j_hit)
                if e2 - s + 1 > self.max_step_bars:
                    tail, e = j_hit - 1, e2
                    break
                versions.append((e2, j_hit))
                e = e2
            self._emit_step(s, versions, tail, close, high, open_, vol, r, abs_r, price_ok,
                            out, today_cache)
            i = e + self.max_pause + 2

        out.sort(key=lambda ev: (ev.end_idx, ev.start_idx))
        yield from out

    def _gate(self, s, e, name, value, label, threshold, op, lookback) -> None:
        # gate: step_not_above_old · 版本最高收盘是否高过旧平台价位
        #       measured=log_ratio(height),判据 height>0 通过,height<=0 这个版本不产
        # gate: step_too_long · 第一个版本的跨度是否超过 max_step_bars
        #       measured=count(bars = e-s+1),判据 bars<=max_step_bars 通过,否则这次阶跃不产
        if self.on_gate is None:
            return
        self.on_gate(GateFailure(
            failure_event_window=(s, e),
            start_idx=s,
            gate_idx=e,
            anchor_bar=e,
            gate_name=name,
            measured=MeasuredKindAware(kind="log_ratio" if label == "height" else "count",
                                       value=value, label=label),
            threshold=threshold,
            op=op, threshold_param=None if label == "height" else "max_step_bars",
            evaluation_lookback=lookback,
            symbol=current_symbol.get() or "",
            stream=None,
        ))

    def _emit_step(self, s, versions, tail, close, high, open_, vol, r, abs_r, price_ok,
                   out, today_cache) -> None:
        """一次阶跃:造旧平台,逐版本判 height、逐天产 plateau 实例。tail 非 None 时最后一个版本
        只产到 tail(续上之后太长,续上那天起这次阶跃不再产)。"""
        n = len(close)
        L = self.old_window
        lo = s - L
        oc = close[lo:s]
        old = OldPlatform(
            start_idx=lo, end_idx=s - 1, confirm_idx=s - 1,
            level=float(np.median(oc)),
            range=float(np.log(oc.max() / oc.min())),
            sigma=_sigma(abs_r[lo:s]),
            vol_mean=float(vol[lo:s].mean()),
        )
        base = float(close[s - 1])
        # overhead 的前高只取价格好的根(坏根记 -inf,不参与取最大)
        high_ok = np.where(price_ok, high, -np.inf)
        for v, (e, _) in enumerate(versions):
            if v + 1 < len(versions):
                t_cap = versions[v + 1][1] - 1
            else:
                t_cap = n - 1 if tail is None else tail
            top_close = float(close[s:e + 1].max())
            height = float(np.log(top_close / old.level))
            if height <= 0:
                self._gate(s, e, "step_not_above_old", height, "height", 0.0, ">",
                           (lo, s - 1))
                continue
            max_ret = float(r[s:e + 1].max())
            vmax = float(vol[s:e + 1].max())
            step = Step(
                start_idx=s, end_idx=e, confirm_idx=e,
                bars=e - s + 1,
                rise=top_close / base - 1.0,
                max_ret=max_ret,
                vs_left=max_ret / old.sigma,
                vol_ratio=(vmax / old.vol_mean) if old.vol_mean > 0 else None,
                vol_mean=float(vol[s:e + 1].mean()),
                vol_max=vmax,
            )
            if e + 1 >= n or not price_ok[e + 1]:
                continue
            # 滚动量:新平台 [e+1, t-1] 的最低/最高收盘、[s, t-1] 的最高价、[e+2, t-1] 里最近一次
            # 严格创新低的那根;派发:[s, u] 的最高收盘、已见过的最大吃掉比例。
            # 产完 t 再把 t 并进来(派发的 u 含当天,先并再产)。
            new_min = new_max = float(close[e + 1])
            high_max = float(high[s:e + 2].max())
            last_low: Optional[int] = None
            peak = top_close
            dump: Optional[float] = None

            def eat(u: int) -> None:
                nonlocal peak, dump
                cu = float(close[u])
                peak = max(peak, cu)
                if peak > base:
                    recent = float(close[max(s, u - self.dump_window):u + 1].max())
                    x = float(np.log(recent / cu) / np.log(peak / base))
                    dump = x if dump is None else max(dump, x)

            eat(e + 1)
            for t in range(e + 2, min(e + self.max_days, t_cap) + 1):
                if not price_ok[t]:
                    break   # 坏数据截断:之后的实例都要读这根
                ct = float(close[t])
                eat(t)
                nc = close[e + 1:t]
                recent = nc[-self.calm_window:]
                nv = vol[e + 1:t]
                nv = nv[np.isfinite(nv) & (nv >= 0)]
                new = NewPlatform(
                    start_idx=e + 1, end_idx=t - 1, confirm_idx=t - 1,
                    bars=t - 1 - e,
                    low=new_min,
                    range=float(np.log(new_max / new_min)),
                    recent_range=float(np.log(recent.max() / recent.min())),
                    sigma=_sigma(abs_r[e + 1:t]),
                    vol_mean=float(nv.mean()) if nv.size else None,
                )
                low_at = t if ct < new_min else last_low
                prior_high = float(high_ok[min(max(0, t - self.overhead_window), s - 1):s].max())
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
                    calm_ratio=new.recent_range / height,
                    keep_ratio=float(np.log(ct / old.level)) / height,
                    vs_high=ct / high_max,
                    overhead=prior_high / ct,
                    vol_shrink=(new.vol_mean / step.vol_max
                                if new.vol_mean is not None and step.vol_max > 0 else None),
                    low_age=(t - low_at) if low_at is not None else None,
                    dump_ratio=dump,
                    old=old, step=step, new=new, today=today,
                ))
                last_low = low_at
                new_min = min(new_min, ct)
                new_max = max(new_max, ct)
                high_max = max(high_max, float(high[t]))
