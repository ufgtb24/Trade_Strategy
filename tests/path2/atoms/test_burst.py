import numpy as np
import pandas as pd
import pytest

from path2.atoms.breakout import BOEvent, BurstEvent, BurstDetector


def _bo(i, drought=None, peaks=(), vol=None):
    return BOEvent(event_id=f"bo:{i}:{i}", start_idx=i, end_idx=i, confirm_idx=i,
                   drought=drought, pk_count=len(peaks),
                   broken_peak_ids=peaks, vol_ratio=vol, peak_vol_max=0.0)


def _make_df(n=200, volume=None):
    """构造测试用 df，默认 volume=1.0 恒定（vol_ratio 基线期内全 NaN）。"""
    vols = volume if volume is not None else np.ones(n)
    return pd.DataFrame({"close": np.arange(n, dtype=float), "volume": vols})


def _detect(bos, gap_max=5, min_bos=3):
    return list(BurstDetector(gap_max=gap_max, min_bos=min_bos)
                .detect(bos, _make_df()))


def test_burst_event_child_api():
    members = (_bo(10, drought=60, peaks=(1, 2), vol=3.0),
               _bo(12, drought=5, peaks=(2, 3), vol=4.0),
               _bo(15, drought=3, peaks=(3,), vol=2.0))
    b = BurstEvent(event_id="burst:10:15", start_idx=10, end_idx=15, confirm_idx=10,
                   count=3, distinct_pk=3, max_bar_vol_ratio=4.0, first_drought=60,
                   members=members)
    assert b.class_id == "burst"
    assert b.child_slots() == {"members": members}
    assert b.children("members") == members
    assert b.child("first_bo") is members[0]
    assert b.child("last_bo") is members[-1]
    assert b.descendant_leaves == members
    with pytest.raises(KeyError):
        b.child("nope")


def test_burst_event_is_frozen():
    import dataclasses
    b = BurstEvent(event_id="burst:1:1", start_idx=1, end_idx=1, confirm_idx=1,
                   count=1, distinct_pk=0, max_bar_vol_ratio=0.0, first_drought=0,
                   members=(_bo(1),))
    with pytest.raises(dataclasses.FrozenInstanceError):
        b.count = 9


def test_chain_breaks_on_gap_exceeding_gap_max():
    """gap > gap_max 断链;两簇独立;< min_bos 的簇不 emit。"""
    bos = [_bo(0, drought=60, peaks=(1,), vol=3.0), _bo(2, drought=2, peaks=(2,), vol=4.0),
           _bo(5, drought=3, peaks=(3,), vol=2.0),    # 簇1 [0,2,5](相邻 gap 2,3 ≤5)
           _bo(40, drought=35, peaks=(9,), vol=1.0)]  # 簇2 [40] 单 bo,不 emit
    bursts = _detect(bos)
    assert len(bursts) == 1
    b = bursts[0]
    assert b.start_idx == 0 and b.end_idx == 5
    assert b.count == 3 and b.first_drought == 60
    assert b.distinct_pk == 3 and b.max_bar_vol_ratio == 0.0  # vol uniformly 1.0 → vol_ratio is NaN in baseline window → max=0.0


def test_all_ends_prefix_family():
    """试金石A:[0,1,2,3,4] → ends 2/3/4 三个前缀实例,start 恒=簇首 0。"""
    bos = [_bo(i, drought=(60 if i == 0 else 1), peaks=(i,), vol=1.0) for i in range(5)]
    bursts = _detect(bos, gap_max=5, min_bos=3)
    assert [(b.start_idx, b.end_idx) for b in bursts] == [(0, 2), (0, 3), (0, 4)]
    assert [b.count for b in bursts] == [3, 4, 5]
    assert all(b.members[0].start_idx == 0 for b in bursts)        # 共享簇首(first_bo 稳定)
    assert all(b.first_drought == 60 for b in bursts)              # 全族恒定
    assert [b.members[-1].start_idx for b in bursts] == [2, 3, 4]  # last_bo = 各自 end
    assert len({b.event_id for b in bursts}) == 3                  # 嵌套(同 start 异 end)不撞 id


def test_no_span_truncation_regression():
    """试金石B回归:相邻 gap 全=5、总跨 30 > 旧 max_span=20 → 整链一簇、起点不漂移。"""
    starts = [0, 5, 10, 15, 20, 25, 30]
    bos = [_bo(s, drought=(60 if s == 0 else 5), peaks=(s,), vol=1.0) for s in starts]
    bursts = _detect(bos, gap_max=5, min_bos=3)
    assert all(b.start_idx == 0 for b in bursts)                   # start 固定=簇首,从未漂移
    assert [b.end_idx for b in bursts] == [10, 15, 20, 25, 30]     # 每个够格 end 一个实例
    assert bursts[-1].count == 7                                   # 最长前缀含整链


def test_prefix_scalars_monotone():
    """前缀族上 distinct_pk / max_bar_vol_ratio 单调不减(where 最早够格 end 的语义基础)。"""
    bos = [_bo(0, drought=60, peaks=(1,), vol=1.0), _bo(1, drought=1, peaks=(1,), vol=5.0),
           _bo(2, drought=1, peaks=(2,), vol=2.0), _bo(3, drought=1, peaks=(3,), vol=3.0)]
    bursts = _detect(bos, gap_max=5, min_bos=2)
    pks = [b.distinct_pk for b in bursts]
    vols = [b.max_bar_vol_ratio for b in bursts]
    assert pks == sorted(pks) and vols == sorted(vols)


def test_output_sorted_by_end_and_two_clusters():
    """run() 要求 end 升序;断链后两簇各自出前缀族。"""
    bos = [_bo(i, drought=1, peaks=(i,), vol=1.0) for i in (0, 1, 2, 30, 31, 32)]
    bursts = _detect(bos, gap_max=5, min_bos=3)
    assert [b.end_idx for b in bursts] == sorted(b.end_idx for b in bursts)
    assert {(b.start_idx, b.end_idx) for b in bursts} == {(0, 2), (30, 32)}


def test_max_bar_vol_ratio_uses_bar_window():
    """max_bar_vol_ratio 扫描 burst [start,end] 区间内所有 bar，包含非 BO bar。

    构造方案:
    - 使用 vol_baseline_period=5，这样只需约 6 个 bar 就能产生非 NaN 的 vol_ratio。
    - 布局(索引 0-based):
        bars 0-5: volume=1.0（基线积累期）
        bar 6: volume=1.0（BO #1，start_idx=6，vol_ratio 接近 1.0）
        bar 7: volume=10.0（非 BO bar，高量 spike，vol_ratio >> 1）
        bar 8: volume=1.0（BO #2，start_idx=8，vol_ratio 接近 1.0）
        bar 9: volume=1.0（BO #3，start_idx=9，vol_ratio 接近 1.0）
        其余: volume=1.0
    - burst span = [6, 9]，非 BO bar 7 的 vol_ratio 最高。
    - 验证 max_bar_vol_ratio > BO bar 的 vol_ratio（即取到了非 BO bar）。
    - 同一 df 换 vol_baseline_period=10 结果不同（10 期基线使 bar 6 处 vol_ratio 为 NaN）。
    """
    n = 50
    volume = np.ones(n)
    volume[7] = 10.0  # 非 BO bar 有量 spike

    df = _make_df(n=n, volume=volume)

    bos = [
        _bo(6, drought=60, peaks=(1,)),
        _bo(8, drought=2, peaks=(2,)),
        _bo(9, drought=1, peaks=(3,)),
    ]

    # vol_baseline_period=5: bar 6 处 rolling(5).mean().shift(1) = mean(bars 1-5) = 1.0
    # bar 7 vol_ratio = 10.0 / 1.0 = 10.0（非 BO，span 内最大）
    bursts_p5 = list(
        BurstDetector(gap_max=5, min_bos=3, vol_baseline_period=5)
        .detect(bos, df)
    )
    assert len(bursts_p5) == 1
    b5 = bursts_p5[0]
    # bar 7 是非 BO bar 且 vol_ratio ≈ 10.0；BO bars 6/8/9 的 vol_ratio ≈ 1.0
    assert b5.max_bar_vol_ratio == pytest.approx(10.0)

    # vol_baseline_period=10: bar 6 处基线需要 bars 0-9（shift(1) 后即 bars -1..-10），
    # 刚好在 idx 6 时 rolling(10) 从 idx 6-10..6-1=idx 5 只有 6 个点 < min_periods=10，
    # 因此 bar 6 的 vol_ratio = NaN；bar 7 处同理（idx 7-10=-3 < 0），也是 NaN。
    # 整个 [6,9] 区间 vol_ratio 全 NaN → max_bar_vol_ratio = 0.0
    bursts_p10 = list(
        BurstDetector(gap_max=5, min_bos=3, vol_baseline_period=10)
        .detect(bos, df)
    )
    assert len(bursts_p10) == 1
    b10 = bursts_p10[0]
    assert b10.max_bar_vol_ratio == 0.0, (
        f"期望基线期不足时 max_bar_vol_ratio=0.0，实际 {b10.max_bar_vol_ratio}"
    )

    # 两个参数设置结果不同
    assert b5.max_bar_vol_ratio != b10.max_bar_vol_ratio
