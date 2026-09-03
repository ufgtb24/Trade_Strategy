"""path2 评估层:match 买点的前瞻幅度 / 首次穿越方向(pattern 质量度量)。

走势-无关:只依赖 Event 区间 + df["close"]/df["high"]/df["low"]/df["date"]。放
calc/atr.py 供 rolling_atr_pct_nanmedian(波动率尺度 M;calc 约定纯数值、本模块
碰 Event/PatternMatch 故 calc 不放此处)。

幅度量(连续统计量、窗内逐点平均):
  - match_forward_returns    : max(high[t+1..t+N])/close[t]-1(只看涨,盲区=先涨后跌回)
  - match_forward_drawdowns  : min(low [t+1..t+N])/close[t]-1(下行镜像,补上述盲区)

首次穿越方向(分类量、买点单点;MFE/MAE 丢顺序,这一类把顺序补回来):
  - match_first_passage      : 买点后窗口内先触上行线 P(1+kM)还是下行线 P/(1+kM)
  - random_day_first_passage : 全宇宙随机日基线计数(无条件基准,对照 pattern 命中)
  几何对称单参数 k(M=ATR/close 滚动 nanmedian,内算);seed 由 ticker md5 派生、跨进程可复现。
"""
from __future__ import annotations

import hashlib
from typing import Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from path2.core import Event
from path2.dag.result import PatternMatch


# ---------------------------------------------------------------------------
# 首次穿越方向(first-passage):买点后窗口内"先触上行线 P(1+kM) 还是下行线
# P/(1+kM)"的方向判据。几何对称单参数 k —— (1+kM) 与 1/(1+kM) 相乘为 1,可逆对称
# (纠正算术 ±kM 对下行的不公平);M = ATR/close 滚动 nanmedian(波动率尺度)。
# 外加随机日基线(每票抽 k 日,seed 由 ticker md5 派生,跨进程可复现)。
# ---------------------------------------------------------------------------

DEFAULT_FP_K: float = 5.0       # 默认几何对称阈值参数 k(上行 P(1+kM)、下行 P/(1+kM))
RANDOM_DAY_K: int = 3            # 随机日基线每票抽样天数
FIRST_PASSAGE_SEED: int = 777    # 随机日基线全局种子(与 ticker md5 异或)


def _ticker_seed(ticker: str, seed: int = FIRST_PASSAGE_SEED) -> int:
    """ticker → 跨进程稳定的整数种子。

    用 md5(非内建 hash):内建 hash(str) 受 PYTHONHASHSEED 影响跨进程不可复现;
    md5 是确定性摘要,同一 (ticker, seed) 在任何进程里都返回同一个值。
    公式:(int(md5_hex,16) % 2**32) ^ seed。
    """
    digest = hashlib.md5(ticker.encode()).hexdigest()
    return (int(digest, 16) % 2 ** 32) ^ seed


def _first_passage_at(
    hi: "np.ndarray",
    lo: "np.ndarray",
    cl: "np.ndarray",
    M: "np.ndarray",
    t: int,
    n: int,
    k: float,
) -> Optional[str]:
    """单点首次穿越方向(几何对称单参数 k + 波动率尺度 M):买点 t、窗口 n。

    上行线 = cl[t] * (1 + k*M[t]);下行线 = cl[t] / (1 + k*M[t])。
    (1+kM) 与 1/(1+kM) 相乘 = 1 → 可逆对称:涨到上行线再跌回、与跌到下行线再涨回,
    需要的反向运动相等(几何对称,纠正算术 ±kM 对下行的不公平)。

    M[t] 非有限(period 样本不足)或 <=0 → None(跳过该买点日,不计数)。
    t+n 越界(整个 n 日窗口不完整)→ None。
    段为 hi/lo 的 [t+1 .. t+n];四态:同根 iu==idn(非哨兵)→ both;都未触 → none;
    iu<idn → up;iu>idn → down。
    """
    if t + n >= len(cl):
        return None
    mt = M[t]
    if not np.isfinite(mt) or mt <= 0:
        return None
    c0 = cl[t]
    up_line = c0 * (1 + k * mt)
    dn_line = c0 / (1 + k * mt)
    seg_h = hi[t + 1 : t + n + 1]
    seg_l = lo[t + 1 : t + n + 1]
    up = np.nonzero(seg_h >= up_line)[0]
    dn = np.nonzero(seg_l <= dn_line)[0]
    iu = up[0] if len(up) else 10 ** 9
    idn = dn[0] if len(dn) else 10 ** 9
    if iu == idn == 10 ** 9:
        return "none"
    if iu == idn:
        return "both"
    return "up" if iu < idn else "down"


def _resolve_end_events(match, end_node: str) -> Tuple[Event, ...]:
    """end_node 解析: 'node_id' → 单 event(现状语义); 'node_id.slot' →
    该容器 child_slots 中该 slot 的 child events(运行时物化,零 spec 依赖)。

    2026-08-07 统一标准协议(用户拍板): 路径第二段 = 父内 slot 名(家庭身份),
    非全局类型标识——"tb.segments" 即"tb 容器里 segments 槽的企稳段";
    同类型多 slot 时 slot 名寻址天然精确(按类型寻址会跨 slot 误匹配)。
    slot 存在但为空 → 空样本(合法,非漂移);slot 名不存在 → KeyError(漂移)。
    """
    if "." not in end_node:
        return (match.node_index[end_node],)   # 缺失 → KeyError(现状)
    parts = end_node.split(".")
    if len(parts) > 2:
        raise ValueError(f"end_node 路径最多一级: {end_node!r}")
    parent_id, slot_name = parts
    parent = match.node_index[parent_id]       # 缺失 → KeyError(现状)
    slot = parent.child_slots().get(slot_name)
    if slot is None:
        raise KeyError(
            f"end_node {end_node!r}: 容器 {parent_id!r} 无 slot {slot_name!r}"
            f"(声明指向但无此槽=漂移)")
    return tuple(slot) if isinstance(slot, tuple) else (slot,)


def match_forward_returns(
    match: PatternMatch,
    end_node: str,
    df: pd.DataFrame,
    horizons: Sequence[int],
    sample_window: Optional[tuple[int, int]] = None,
) -> dict[int, Optional[float]]:
    """end_node 解析出的 event(s)(买点窗)内逐买点日 max(high[t+1..t+N])/close[t]-1
    的均值,每 horizon 一项——"未来 N 日内最大涨幅",非端点收益。路径(如 'tb.segments')
    样本 = 各 child span bar 并集(统一标准协议,与 serialize 同一 _resolve_end_events)。

    sample_window: t4 配套的样本消费窗(spec §10 样本消费窗截取),双边含端 (lo, hi)——
    买点日 t 仅当 lo <= t <= hi 参与样本,跨界 tb_seg 只取窗内部分计样本;None = 全量
    (向后兼容)。label 前瞻窗不受截取影响(仍看未来 N 根——截的是买点日集合,不是 label 窗)。

    df 必须就是产生该 match 的那个窗口 df(event 的 start_idx/end_idx 是它的
    0-based 行位置索引,索引对齐由调用方保证)。
    t+N 越界的买点日跳过(要求整个 N 日窗口完整可见);某 horizon 全部越界 → 该项 None。
    end_node 缺失 → KeyError;路径最多一级,child slot 无匹配 → KeyError
    (解析协议见 _resolve_end_events)。
    """
    events = _resolve_end_events(match, end_node)   # 缺失 → KeyError(语义自然)
    close = df["close"]
    high = df["high"]
    n_bars = len(df)
    out: dict[int, Optional[float]] = {}
    for n in horizons:
        rets = [
            float(high.iloc[t + 1 : t + n + 1].max()) / float(close.iat[t]) - 1.0
            for ev in events
            for t in ev.sample_bar_indices()
            if t + n < n_bars
            and (sample_window is None or sample_window[0] <= t <= sample_window[1])
        ]
        out[n] = sum(rets) / len(rets) if rets else None
    return out


def match_forward_drawdowns(
    match: PatternMatch,
    end_node: str,
    df: pd.DataFrame,
    horizons: Sequence[int],
    sample_window: Optional[tuple[int, int]] = None,
) -> dict[int, Optional[float]]:
    """end_node 解析出的 event(s)(买点窗)内逐买点日 min(low[t+1..t+N])/close[t]-1
    的均值,每 horizon 一项——"未来 N 日内最大跌幅",match_forward_returns 的下行镜像
    (非端点收益)。补 mfr"只看涨"看不到的先涨后跌回场景。路径样本 = 各 child span
    bar 并集(统一标准协议,与 serialize 同一 _resolve_end_events)。

    sample_window: t4 配套的样本消费窗(spec §10 样本消费窗截取),双边含端 (lo, hi)——
    买点日 t 仅当 lo <= t <= hi 参与样本,跨界 tb_seg 只取窗内部分计样本;None = 全量
    (向后兼容)。label 前瞻窗不受截取影响(仍看未来 N 根——截的是买点日集合,不是 label 窗)。

    与 match_forward_returns 同口径:df 必须就是产生该 match 的那个窗口 df
    (event 的 start_idx/end_idx 是它的 0-based 行位置索引,索引对齐由调用方保证);
    t+N 越界的买点日跳过(要求整个 N 日窗口完整可见);某 horizon 全部越界 → 该项 None;
    end_node 缺失 → KeyError;路径最多一级,child slot 无匹配 → KeyError
    (解析协议见 _resolve_end_events)。
    """
    events = _resolve_end_events(match, end_node)   # 缺失 → KeyError(语义自然)
    close = df["close"]
    low = df["low"]
    n_bars = len(df)
    out: dict[int, Optional[float]] = {}
    for n in horizons:
        rets = [
            float(low.iloc[t + 1 : t + n + 1].min()) / float(close.iat[t]) - 1.0
            for ev in events
            for t in ev.sample_bar_indices()
            if t + n < n_bars
            and (sample_window is None or sample_window[0] <= t <= sample_window[1])
        ]
        out[n] = sum(rets) / len(rets) if rets else None
    return out


def match_first_passage(
    match: PatternMatch,
    end_node: str,
    df: pd.DataFrame,
    horizon: int,
    k: float = DEFAULT_FP_K,
    sample_window: Optional[tuple[int, int]] = None,
    M: Optional["np.ndarray"] = None,
) -> dict[str, int]:
    """end_node 解析出的 event(s)(买点窗)内逐买点日的首次穿越四态计数:
    {up, down, both, none}(单组)。路径(如 'tb.segments')样本 = 各 child span bar 并集
    (统一标准协议,与 match_forward_returns 同一 _resolve_end_events)。

    sample_window: t4 配套的样本消费窗(spec §10 样本消费窗截取),双边含端 (lo, hi)——
    买点日 t 仅当 lo <= t <= hi 参与样本,跨界 tb_seg 只取窗内部分计样本;None = 全量
    (向后兼容)。label 前瞻窗不受截取影响(仍看未来 horizon 根——截的是买点日集合)。

    波动率尺度 M = rolling_atr_pct_nanmedian(high, low, close, 20)(默认内算,可由 M
    参数外传);阈值几何对称单参数 k:上行 P(1+kM)、下行 P/(1+kM)。遍历 span 全买点日
    (t+horizon 越界 或 M[t] 样本不足 → 跳过),逐个 _first_passage_at 判定、累计四态。

    M: 外传的波动率尺度(每股算一次复用,供多次调用共享,省去重复计算);None 时内算。
    必须按同一个 df 算(len(M) 须等于 len(df)——首穿下标是 df 行位置索引),否则
    抛 ValueError(防跨窗错位喂入导致越界判定基准与 M 索引不一致、静默算错)。

    集合级 ratio 的分母 = 买点日数(up+down+both+none),与 match_forward_returns 的
    span 全买点日口径对齐。end_node 缺失 → KeyError;路径最多一级,child slot
    无匹配 → KeyError(解析协议见 _resolve_end_events)。
    """
    from path2.calc.atr import FP_ATR_WINDOW, rolling_atr_pct_nanmedian

    events = _resolve_end_events(match, end_node)   # 缺失 → KeyError(语义自然)
    if M is None:
        M = rolling_atr_pct_nanmedian(df["high"], df["low"], df["close"], FP_ATR_WINDOW).values
    if len(M) != len(df):
        raise ValueError(
            f"M 长度 {len(M)} 与 df 长度 {len(df)} 不一致:M 必须按同一个 df 算"
            f"(首穿下标是 df 行位置索引,M 与 df 错位会导致越界判定基准与 M 取值静默错位)")
    hi = df["high"].values
    lo = df["low"].values
    cl = df["close"].values
    counts = {"up": 0, "down": 0, "both": 0, "none": 0}
    for ev in events:
        for t in ev.sample_bar_indices():
            if sample_window is not None and not (sample_window[0] <= t <= sample_window[1]):
                continue
            state = _first_passage_at(hi, lo, cl, M, t, horizon, k)
            if state is None:
                continue
            counts[state] += 1
    return counts


def random_day_first_passage(
    ticker: str,
    df: pd.DataFrame,
    start_ts: "pd.Timestamp",
    end_ts: "pd.Timestamp",
    horizon: int,
    k: float = DEFAULT_FP_K,
    n_days: int = RANDOM_DAY_K,
    seed: int = FIRST_PASSAGE_SEED,
    M: Optional["np.ndarray"] = None,
) -> dict:
    """全宇宙随机日基线的首次穿越方向计数(无条件基准,对照 pattern 命中)。单组。

    流程:
      1. 候选日 = date∈[start_ts,end_ts] 且 i+horizon<n_bars(先过滤再抽样);
      2. rng = default_rng(_ticker_seed(ticker, seed))(ticker md5 派生,跨进程稳定);
      3. 抽 min(n_days, len(候选)) 日,逐个 _first_passage_at(几何对称单 k + M)判定、
         累计四态。M = rolling_atr_pct_nanmedian(默认内算,可由 M 参数外传),与
         match_first_passage 同尺子。

    M: 外传的波动率尺度(每股算一次复用,供多次调用共享,省去重复计算);None 时内算。
    必须按同一个 df 算(len(M) 须等于 len(df)——候选日/首穿下标都是 df 行位置索引),
    否则抛 ValueError(防跨窗错位喂入导致静默算错)。

    返回 {"n_sampled": int, "counts": {up,down,both,none}}(counts 单组);
    无候选 → n_sampled=0、counts 四态零。

    df 需有 date/high/low/close 列(date 为可被 pd.Timestamp 转换的日期时间)。
    """
    from path2.calc.atr import FP_ATR_WINDOW, rolling_atr_pct_nanmedian

    hi = df["high"].values
    lo = df["low"].values
    cl = df["close"].values
    if M is None:
        M = rolling_atr_pct_nanmedian(df["high"], df["low"], df["close"], FP_ATR_WINDOW).values
    if len(M) != len(df):
        raise ValueError(
            f"M 长度 {len(M)} 与 df 长度 {len(df)} 不一致:M 必须按同一个 df 算"
            f"(候选日/首穿下标是 df 行位置索引,M 与 df 错位会导致静默算错)")
    dts = df["date"].values
    n_bars = len(df)

    # 先过滤:日期在区间内 + horizon 窗口完整
    in_win = [
        i for i in range(n_bars)
        if start_ts <= pd.Timestamp(dts[i]) <= end_ts and i + horizon < n_bars
    ]
    counts = {"up": 0, "down": 0, "both": 0, "none": 0}
    if not in_win:
        return {"n_sampled": 0, "counts": counts}

    rng = np.random.default_rng(_ticker_seed(ticker, seed))
    sample = rng.choice(in_win, size=min(n_days, len(in_win)), replace=False)
    for i in sample:
        state = _first_passage_at(hi, lo, cl, M, int(i), horizon, k)
        if state is None:                    # M[t] 样本不足,保守跳过
            continue
        counts[state] += 1
    return {"n_sampled": int(len(sample)), "counts": counts}
