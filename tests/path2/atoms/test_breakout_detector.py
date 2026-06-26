import numpy as np
import pandas as pd
import pytest

from path2 import run
from path2.atoms.breakout import BODetector, BOEvent
from path2.calc.measure import measure_series


def make_df(closes, highs=None, lows=None, opens=None, vols=None):
    n = len(closes)
    return pd.DataFrame({
        'open': opens or list(closes),
        'high': highs or [c + 0.1 for c in closes],
        'low': lows or [c - 0.1 for c in closes],
        'close': list(closes),
        'volume': vols or [1000.0] * n,
    })


def test_no_bo_on_flat():
    df = make_df([10.0] * 30)
    bos = list(run(BODetector(peak_measure="body_top", breakout_measure="body_top"), df))
    assert bos == []


def test_simple_bo():
    # 制造一个 peak 在中间,然后突破
    closes = [10.0] * 5 + [12.0] + [10.0] * 5 + [13.0]  # peak at idx 5, BO at idx 11
    df = make_df(closes)
    bos = list(run(BODetector(total_window=10, min_side_bars=2, min_relative_height=0.05, exceed_threshold=0.005,
                              peak_measure="body_top", breakout_measure="body_top"), df))
    # 至少一个 BO 在末位
    assert len(bos) >= 1
    assert bos[-1].start_idx == 11
    assert bos[-1].pk_count >= 1


def test_drought_calculation():
    closes = [10.0] * 5 + [12.0] + [10.0] * 5 + [13.0] + [10.5] * 5 + [14.0]
    df = make_df(closes)
    bos = list(run(BODetector(total_window=10, min_side_bars=2, min_relative_height=0.05, exceed_threshold=0.005,
                              peak_measure="body_top", breakout_measure="body_top"), df))
    if len(bos) >= 2:
        assert bos[0].drought is None  # 首次
        assert bos[1].drought is not None and bos[1].drought > 0


def test_event_id_unique():
    closes = [10.0] * 5 + [12.0] + [10.0] * 5 + [13.0]
    df = make_df(closes)
    bos = list(run(BODetector(total_window=10, min_side_bars=2, min_relative_height=0.05,
                              peak_measure="body_top", breakout_measure="body_top"), df))
    ids = [e.event_id for e in bos]
    assert len(ids) == len(set(ids))


def test_supersede_removes_old_peak():
    """I2 真测:supersede 后,同一 peak 不应被后续小幅突破再次计入。

    构造:peak1 在 idx 5 (price=12)。
      - idx 11:第一次突破到 ~15(>12*1.03),应**supersede** peak1(移除)
      - idx 17 起再次小幅突破到 ~12.2(若 peak1 仍在 active 中且 supersede 失效,
        会被再次"突破";若 supersede 生效,peak1 已不在 active,12.2 无 peak 可破)

    判据:若 supersede 生效 → 第二次小幅突破不命中(因为 peak1 已被移除);
          若 supersede 失效(回归) → 第二次小幅突破仍命中。
    """
    closes = ([10.0] * 5 + [12.0]      # idx 0-5: peak1 形成
              + [10.0] * 5             # idx 6-10
              + [15.0]                 # idx 11: 突破 + supersede(>12*1.03)
              + [10.0] * 5             # idx 12-16: 回落,如 peak1 仍在 active 会再次被突破
              + [12.2])                # idx 17: 若 supersede 失效则又突破 peak1
    df = make_df(closes)
    bos = list(run(BODetector(
        total_window=10, min_side_bars=2, min_relative_height=0.05,
        exceed_threshold=0.005, peak_supersede_threshold=0.03,
        peak_measure="body_top", breakout_measure="body_top",
    ), df))
    # 末 bar (idx 17) 不应再因 peak1 被突破 — peak1 已 supersede。
    # (若 idx 17 之间窗内形成了新 peak 才会有 BO,但本 fixture 无此条件。)
    last_bo_indices = [b.start_idx for b in bos]
    assert 11 in last_bo_indices, "idx 11 应为首次突破(BO)"
    assert 17 not in last_bo_indices, (
        "idx 17 不应有 BO — peak1 已 supersede;若出现则 supersede 回归失效"
    )


def test_breakout_invalid_measure_raises():
    with pytest.raises(ValueError, match="peak_measure"):
        BODetector(peak_measure="foo")
    with pytest.raises(ValueError, match="breakout_measure"):
        BODetector(breakout_measure="bar")


def test_breakout_peak_measure_high_vs_body_top():
    """peak_measure='high' 给峰更高(因长上影),令 body_top 模式触发 BO 而 high 模式不触发。

    Fixture 设计:
      side 段:open=close=100, high=100.1, low=99.9  → body_top=100, high=100.1
      peak 段:open=close=101, high=104,   low=100.9 → body_top=101, high=104(长上影)
      BO bar:open=101, close=102, high=102.1, low=100.9 → body_top=102, high=102.1
    peak_measure='body_top':peak.price=101,BO 价格 body_top=102 > 101*1.005=101.505 → 触发。
    peak_measure='high':   peak.price=104,BO 价格 high=102.1 < 104*1.005=104.52    → 不触发。
    """
    n = 25
    opens = [100.0] * n
    closes = [100.0] * n
    highs = [100.1] * n
    lows = [99.9] * n

    def _set_peak(idx):
        opens[idx] = 101.0
        closes[idx] = 101.0
        highs[idx] = 104.0  # 长上影,high 远高于 body_top
        lows[idx] = 100.9

    def _set_break(idx):
        opens[idx] = 101.0
        closes[idx] = 102.0
        highs[idx] = 102.1  # 上影很短
        lows[idx] = 100.9

    # 两组 peak (idx 4,5 / 16,17) + 两个 BO 候选 (idx 10 / 22)
    _set_peak(4)
    _set_peak(5)
    _set_break(10)
    _set_peak(16)
    _set_peak(17)
    _set_break(22)

    df = pd.DataFrame({
        'open': opens, 'high': highs, 'low': lows, 'close': closes,
        'volume': [1e6] * n,
    })

    det_body = BODetector(total_window=10, min_side_bars=2,
                          min_relative_height=0.001,
                          exceed_threshold=0.005,
                          peak_measure="body_top", breakout_measure="body_top")
    det_high = BODetector(total_window=10, min_side_bars=2,
                          min_relative_height=0.001,
                          exceed_threshold=0.005,
                          peak_measure="high", breakout_measure="body_top")
    bos_body = list(det_body.detect(df))
    bos_high = list(det_high.detect(df))

    # body_top peak 较低 → 触发 BO;high peak 含长上影 → 同一 bar 不触发
    assert len(bos_body) >= 1, f"body_top 模式应触发 BO,实际 {len(bos_body)}"
    assert len(bos_high) < len(bos_body), (
        f"high 模式 peak 更高,应少于 body_top 模式 BO 数;"
        f"实际 body={len(bos_body)} high={len(bos_high)}"
    )
    # 顺带 verify helper 性质(high series >= body_top series)
    series_body = measure_series(df, "body_top")
    series_high = measure_series(df, "high")
    assert (series_high >= series_body).all()


def test_breakout_measure_close_filters_strict():
    """breakout_measure='close' 比 'body_top' 严格(阴线 close < open):同 peak 同 BO bar 下,
    body_top 触发而 close 不触发。

    Fixture 设计(全阴线 open > close → body_top = open):
      side 段:open=100.5, close=100   → body_top=100.5
      peak 段:open=101.5, close=101   → body_top=101.5
      BO bar:open=102.5, close=101.6  → body_top=102.5, close=101.6
    peak_measure 显式钉 body_top,peak.price = 101.5。
    body_top BO 价格 = 102.5 > 101.5*1.005 = 102.0075 → 触发。
    close    BO 价格 = 101.6 < 102.0075                → 不触发。
    """
    pattern_side = [(100.5, 100.0)] * 4
    pattern_peak = [(101.5, 101.0)] * 2
    pattern_break = [(102.5, 101.6)]
    bars = (pattern_side + pattern_peak + pattern_side + pattern_break
            + pattern_side + pattern_peak + pattern_side + pattern_break
            + pattern_side)
    opens = [b[0] for b in bars]
    closes = [b[1] for b in bars]
    highs = [o + 0.1 for o in opens]
    lows = [c - 0.1 for c in closes]
    n = len(bars)
    df = pd.DataFrame({
        'open': opens, 'high': highs, 'low': lows, 'close': closes,
        'volume': [1e6] * n,
    })

    det_body = BODetector(total_window=10, min_side_bars=2,
                          min_relative_height=0.001,
                          exceed_threshold=0.005,
                          peak_measure="body_top", breakout_measure="body_top")
    det_close = BODetector(total_window=10, min_side_bars=2,
                           min_relative_height=0.001,
                           exceed_threshold=0.005,
                           peak_measure="body_top", breakout_measure="close")
    bos_body = list(det_body.detect(df))
    bos_close = list(det_close.detect(df))

    # body_top 模式应至少触发一个 BO,close 模式应严格更少
    assert len(bos_body) >= 1, f"body_top 模式应触发 BO,实际 {len(bos_body)}"
    assert len(bos_close) < len(bos_body), (
        f"close 模式应比 body_top 模式严格(BO 更少);"
        f"实际 body={len(bos_body)} close={len(bos_close)}"
    )


def test_emit_populates_referenced_points_with_pk_meta():
    """BODetector.emit 应把每个被突破的 Peak 序列化为 (index, price, f'pk{pk_id}') 入 referenced_points。"""
    # 同 test_simple_bo 的构造: peak at idx 5, BO at idx 11
    closes = [10.0] * 5 + [12.0] + [10.0] * 5 + [13.0]
    df = make_df(closes)
    bos = list(run(BODetector(total_window=10, min_side_bars=2,
                              min_relative_height=0.05, exceed_threshold=0.005,
                              peak_measure="body_top", breakout_measure="body_top"), df))
    assert len(bos) >= 1
    bo = bos[-1]
    assert len(bo.referenced_points) == bo.pk_count   # 与 pk_count 等长
    assert len(bo.referenced_points) == len(bo.broken_peak_ids)
    for (bar_idx, price, label), pk_id in zip(bo.referenced_points, bo.broken_peak_ids):
        assert isinstance(bar_idx, int) and bar_idx >= 0
        assert isinstance(price, float) and price > 0
        assert label == f"pk{pk_id}"   # label 格式锁定


# ─── dev breakout_detector.py 对齐:elevation + peak-peak supersede(2026-06-22)──
def test_elevation_prevents_repeated_breakout_of_same_peak():
    """同一 peak 被多次小幅突破时,elevation 生效后 peak.price 抬到 BO measure,
    下次必须超过 elevated 价格才再触发 BO。否则同 peak 反复进 broken_peak_ids,
    现象 = web UI 同一 pk_id 在相差不远的多个 bo 处重复出现。

    Fixture(peak_measure=body_top, breakout_measure=body_top):
      idx 5  peak1 body_top=13
      idx 11 BO1   body_top=13.07  (>13*1.005=13.065 触发 → elevate 到 13.07)
      idx 14 BO?   body_top=13.10
        - elevation 生效:13.10 < 13.07*1.005=13.1352 → 不触发
        - elevation 失效(当前 path2):13.10 > 13(原)*1.005=13.065 → 触发,broken_peak_ids 重复 0
    """
    n = 15
    opens = [10.0] * n; closes = [10.0] * n; highs = [10.1] * n; lows = [9.9] * n
    opens[5] = closes[5] = 13.0; highs[5] = 13.1; lows[5] = 12.9       # peak1
    opens[11] = closes[11] = 13.07; highs[11] = 13.17; lows[11] = 12.97  # BO1 小幅
    opens[14] = closes[14] = 13.10; highs[14] = 13.20; lows[14] = 13.00  # BO2 仍小幅
    df = pd.DataFrame({'open': opens, 'high': highs, 'low': lows, 'close': closes,
                       'volume': [1e6] * n})
    bos = list(BODetector(total_window=10, min_side_bars=2, min_relative_height=0.05,
                          exceed_threshold=0.005, peak_supersede_threshold=0.03,
                          peak_measure='body_top', breakout_measure='body_top').detect(df))
    bos_14 = [b for b in bos if b.start_idx == 14]
    # GREEN 期望:idx 14 不再触发 BO(13.10 不超过 elevated 13.07 的 exceed 阈值)。
    # peak1 在 idx 12-14 期间可能被 detect 为新 peak(idx 11 进窗口),
    # 但 idx 11 自身的 body_top=13.07 在 idx 14 也不会被自身 BO 突破。
    assert not bos_14, (
        f"elevation 生效后 idx 14 不应触发 BO — 13.10 未超过 elevated 13.07 的 exceed 阈值;"
        f"实际触发了 {len(bos_14)} 个 BO,broken_peak_ids={bos_14[0].broken_peak_ids if bos_14 else None}"
    )


def test_peak_peak_supersede_prevents_oneshot_cleanup_of_old_peaks():
    """新高 peak 出现时应淘汰显著较低的老 peak(>3%),防止后续一次大涨把多个老 peak 一锅端。
    web UI 现象 = 顶部 bo box [1,2,3,4,5,6,7,9,10,11,12,16] 把大批历史低位 peak 全列上。

    Fixture(peak_measure=body_top, breakout_measure=close):
      idx 5  peak1 body_top=10
      idx 18 peak2 candidate:body_top=15(open=15)、close=9(阴线)、low=8
             —— close=9 不触发 BO,但 body_top=15 在后续 detect 窗口里成 peak2 candidate
      idx 31 BO    close=16 同时破 peak1+peak2

    GREEN(peak-peak supersede 生效):peak2 创建期 peak1 被淘汰(15>10*1.03=10.3),
                                    idx 31 BO broken_peak_ids 长度=1(仅 peak2)。
    RED (当前 path2):peak1 长期残留,idx 31 broken_peak_ids 长度=2(peak1+peak2)。
    """
    n = 35
    opens = [9.0] * n; closes = [9.0] * n; highs = [9.1] * n; lows = [8.9] * n
    # peak1 idx 5: body_top=10
    opens[5] = closes[5] = 10.0; highs[5] = 10.1; lows[5] = 9.9
    # peak2 idx 18: body_top=15(open=15) + close=9 阴线 → BO 看 close=9 不触发
    opens[18] = 15.0; closes[18] = 9.0; highs[18] = 15.1; lows[18] = 8.0
    # idx 31 BO close=16
    opens[31] = 9.5; closes[31] = 16.0; highs[31] = 16.1; lows[31] = 9.4
    df = pd.DataFrame({'open': opens, 'high': highs, 'low': lows, 'close': closes,
                       'volume': [1e6] * n})
    bos = list(BODetector(total_window=10, min_side_bars=2, min_relative_height=0.05,
                          exceed_threshold=0.005, peak_supersede_threshold=0.03,
                          peak_measure='body_top', breakout_measure='close').detect(df))
    bo_31 = next((b for b in bos if b.start_idx == 31), None)
    assert bo_31 is not None, "idx 31 大涨 close=16 应触发 BO"
    assert len(bo_31.broken_peak_ids) == 1, (
        f"peak-peak supersede 生效后:peak1(idx5 body_top=10) 应在 peak2(idx18 body_top=15) "
        f"出现时被淘汰(15>10*1.03=10.3),idx 31 BO 只剩 peak2 可破;"
        f"实际 broken_peak_ids={bo_31.broken_peak_ids}(>1 = supersede 失效,老低位 peak 残留)"
    )
