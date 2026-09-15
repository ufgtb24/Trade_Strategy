"""扫描窗口左截断下的 drought 语义:窗口内首根 bo 的沉寂长度不得记成 0。

背景:BODetector 的 drought = 距上一根 bo 的 K 线根数,本趟扫描的第一根 bo 没有
前序、drought 为 None(词表语义是「无前序」,不是「未知」)。旧实现在 burst 聚合时
把 None 兜底成 0,于是「窗口内此前一根 bo 都没有」被翻译成「距上一根 bo 只有 0 根」——
语义翻面,first_drought >= 阈值 的闸稳稳拦下。而这类样本恰恰是长期沉寂后的首次突破
(圆弧底右侧起点),正是该闸想留的那一类。

修复:BOEvent 携带 drought_floor(本趟扫描可确证的沉寂下界),burst 的 first_drought
读它而非 drought。下界口径 = bo 索引 - total_window(热身期内无 active peak,
结构性不可能产 bo,那段不算「观测到没有 bo」)。
"""
import numpy as np
import pandas as pd

from path2.atoms.breakout import BODetector, BurstDetector

TOTAL_WINDOW = 10
FIRST_BO_IDX = 60
SECOND_BO_IDX = 64


def _silent_then_breakout_df() -> pd.DataFrame:
    """长期沉寂后首次突破:0..12 造一个 130 的峰,13..59 完全横盘(不登记新峰、不突破),
    60 与 64 各突破一次。窗口内第一根 bo 落在 60,它之前 60 根 K 线无任何 bo。
    """
    n = 80
    high = np.full(n, 100.0)
    low = np.full(n, 100.0)
    for i, v in zip(range(13), [100, 105, 112, 120, 126, 129, 130, 126, 118, 112, 106, 102, 100]):
        high[i] = v
        low[i] = v - 2
    # 13..59 横盘 100:相对高度 0 < min_relative_height,不登记新峰;100 也突破不了 130
    high[FIRST_BO_IDX], low[FIRST_BO_IDX] = 140.0, 101.0
    high[61], low[61] = 120.0, 100.0
    high[62], low[62] = 118.0, 100.0
    high[63], low[63] = 119.0, 100.0
    high[SECOND_BO_IDX], low[SECOND_BO_IDX] = 150.0, 118.0
    close = (high + low) / 2
    return pd.DataFrame({"open": close, "high": high, "low": low, "close": close,
                         "volume": np.ones(n) * 1e6})


def _run_bo(df: pd.DataFrame):
    det = BODetector(total_window=TOTAL_WINDOW, min_side_bars=2, min_relative_height=0.05,
                     exceed_threshold=0.005, peak_supersede_threshold=0.03,
                     vol_baseline_period=63)
    return [ev for stream, ev in det.detect(df) if stream == "bo"]


def test_first_bo_keeps_drought_none_but_carries_observable_floor():
    """窗口内首根 bo:drought 仍是 None(无前序),drought_floor 给出可确证的沉寂下界。"""
    bos = _run_bo(_silent_then_breakout_df())
    assert [b.start_idx for b in bos] == [FIRST_BO_IDX, SECOND_BO_IDX]
    assert bos[0].drought is None
    assert bos[0].drought_floor == FIRST_BO_IDX - TOTAL_WINDOW


def test_non_first_bo_floor_equals_drought():
    """有前序的 bo:精确值本身就是下界,两者一致(下游读 drought_floor 无需分支)。"""
    bos = _run_bo(_silent_then_breakout_df())
    assert bos[1].drought == SECOND_BO_IDX - FIRST_BO_IDX
    assert bos[1].drought_floor == bos[1].drought


def test_burst_first_drought_reflects_silence_not_zero():
    """端到端:长期沉寂后首次突破聚合出的 burst,first_drought 反映沉寂长度而非 0。

    这条是本次修复的核心断言——旧实现在此得 0,被 first_drought >= 20 的闸拦掉。
    """
    df = _silent_then_breakout_df()
    bursts = list(BurstDetector(gap_max=5, min_bos=2, vol_baseline_period=63)
                  .detect(_run_bo(df), df))
    assert len(bursts) == 1
    assert bursts[0].first_drought == FIRST_BO_IDX - TOTAL_WINDOW
    assert bursts[0].first_drought >= 20, "该 burst 应能通过 first_drought_min=20 的闸"


def test_bo_at_warmup_boundary_has_zero_floor():
    """bo 紧贴热身期结束就发生:没有任何观测证据说明它干旱,下界为 0(保守拦掉)。"""
    n = 40
    high = np.full(n, 100.0)
    low = np.full(n, 100.0)
    for i, v in zip(range(13), [100, 105, 112, 120, 126, 129, 130, 126, 118, 112, 106, 102, 100]):
        high[i] = v
        low[i] = v - 2
    # 峰在 idx 6,最早能登记它的 bar 是 i=total_window=10(窗口 [0,9],局部 idx 6)
    high[TOTAL_WINDOW], low[TOTAL_WINDOW] = 140.0, 106.0
    close = (high + low) / 2
    df = pd.DataFrame({"open": close, "high": high, "low": low, "close": close,
                       "volume": np.ones(n) * 1e6})
    bos = _run_bo(df)
    assert bos and bos[0].start_idx == TOTAL_WINDOW
    assert bos[0].drought is None and bos[0].drought_floor == 0
