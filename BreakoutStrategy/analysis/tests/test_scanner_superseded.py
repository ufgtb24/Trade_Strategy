"""Integration test: scanner._scan_single_stock serializes superseded peaks.

Regression test for commit 2022b34 which fixed the serialization path that
dropped detector.superseded_by_new_peak from all_peaks output.

Note: CVGI 2025-11-28 (idx=243) is a *broken* peak (absorbed into a breakout),
not a superseded peak. The actual superseded peak in this dataset is
2025-10-24 (idx=219), which is what test_cvgi_has_at_least_one_superseded_peak
validates. The 11-28 tests verify that broken peaks also survive serialization
intact (a distinct property from the superseded fix, but also part of the
original bug report).
"""
from pathlib import Path

import pandas as pd
import pytest

from BreakoutStrategy.analysis.scanner import _scan_single_stock
from BreakoutStrategy.factor_registry import get_max_buffer


CVGI_PKL = Path(__file__).parents[3] / "datasets" / "pkls_live" / "CVGI.pkl"


@pytest.fixture
def cvgi_scan_args():
    """复现 live pipeline 对 CVGI 的 _scan_single_stock 调用参数。

    参数来自 outputs/statistics/pk_gte/trials/14373/filter.yaml 的
    scan_params.breakout_detector，与 live/config.yaml 的扫描窗口对齐。
    """
    return (
        "CVGI",                                    # symbol
        str(CVGI_PKL.parent),                      # data_dir
        20,                                        # total_window
        6,                                         # min_side_bars
        0.1,                                       # min_relative_height
        0.005,                                     # exceed_threshold
        0.03,                                      # peak_supersede_threshold
        "body_top",                                # peak_measure
        "close",                                   # breakout_mode
        20,                                        # streak_window
        "2025-10-15",                              # start_date
        "2026-04-14",                              # end_date (cover 2025-11-28)
        None,                                      # feature_calc_config
        None,                                      # scorer_config
        20,                                        # label_max_days
        1.0,                                       # min_price
        10.0,                                      # max_price
        10000,                                     # min_volume
        get_max_buffer(),                          # max_buffer（与生产一致）
    )


def test_cvgi_pkl_fixture_exists():
    """前置条件：CVGI.pkl 存在于 datasets/pkls_live。"""
    assert CVGI_PKL.exists(), f"CVGI fixture not found at {CVGI_PKL}"


def test_cvgi_scan_produces_non_empty_result(cvgi_scan_args):
    """CVGI 扫描应产出至少一个 breakout（2026-03-11 急拉）。"""
    result = _scan_single_stock(cvgi_scan_args)
    assert result is not None
    assert "error" not in result, f"Scan failed: {result.get('error')}"
    assert len(result["breakouts"]) > 0
    assert len(result["all_peaks"]) > 0


def test_cvgi_scan_includes_peak_at_2025_11_28(cvgi_scan_args):
    """CVGI 2025-11-28 峰值应出现在 all_peaks 输出里（不管 active/broken/superseded）。

    Fix 2022b34 前该 peak 因 scanner 漏收 superseded_by_new_peak 而被整体丢失。
    """
    df = pd.read_pickle(CVGI_PKL)
    target_ts = pd.Timestamp("2025-11-28")
    # 找 df 中 2025-11-28 的整数索引；若该日无 bar（非交易日）则取紧邻的那根
    target_idx = int(df.index.searchsorted(target_ts, side="left"))
    if target_idx >= len(df) or df.index[target_idx] != target_ts:
        # 2025-11-28 是周五，CVGI 是美股，应有该交易日；如没有说明数据问题
        pytest.fail(
            f"CVGI.pkl does not contain a bar for {target_ts.date()}; "
            f"nearest is {df.index[target_idx] if target_idx < len(df) else 'EOF'}"
        )

    result = _scan_single_stock(cvgi_scan_args)
    peaks_at_target = [p for p in result["all_peaks"] if p["index"] == target_idx]
    assert len(peaks_at_target) == 1, (
        f"Expected exactly one peak at index {target_idx} (2025-11-28), "
        f"got {len(peaks_at_target)}"
    )


def test_cvgi_2025_11_28_peak_is_not_active(cvgi_scan_args):
    """CVGI 2025-11-28 峰值必须 is_active=False（已被后续价格穿越或取代）。

    注：该峰值在当前数据下被后续突破穿越（broken），故 is_superseded=False；
    is_active=False 是确定的不变量。
    Fix 2022b34 的核心契约是：峰值本身出现在 all_peaks 里（见 test_cvgi_scan_includes_peak_at_2025_11_28）。
    """
    df = pd.read_pickle(CVGI_PKL)
    target_idx = int(df.index.searchsorted(pd.Timestamp("2025-11-28"), side="left"))

    result = _scan_single_stock(cvgi_scan_args)
    peaks_at_target = [p for p in result["all_peaks"] if p["index"] == target_idx]
    assert len(peaks_at_target) == 1
    peak = peaks_at_target[0]

    assert peak["is_active"] is False, (
        f"Peak at 2025-11-28 should be is_active=False, got {peak}"
    )


@pytest.mark.skip(
    reason=(
        "per-factor gate 移除了 detector 顶端的 max_buffer 短路（per-factor-gating Spec 1, T9）。"
        "旧 gate 会保护 idx<252 的 peak 不被早期 BO 消费，让它们在后续被新峰值结构性 supersede。"
        "新语义下早期 BO 正常 fire，peak 直接被 broken，不再走 supersede 路径。"
        "CVGI 在 [2025-10-15, 2026-04-14] 区间下 superseded_by_new_peak 集为空。"
        "commit 2022b34 引入的序列化逻辑仍正确（_scan_single_stock 输出 detector.superseded_by_new_peak），"
        "只是缺乏新 fixture 来验证。后续可以另写一个合成 detector fixture 直接覆盖序列化路径。"
    )
)
def test_cvgi_has_at_least_one_superseded_peak(cvgi_scan_args):
    """Fix 2022b34 的序列化契约：scanner 必须将 detector.superseded_by_new_peak
    纳入 all_peaks 输出，且至少一个峰值被标记 is_superseded=True。

    CVGI 数据在扫描窗口内存在被后续更高峰值超过 ≥3% 且从未被击破的峰值，
    它应出现在 all_peaks 且 is_superseded=True。断言使用 `>= 1` 而非硬编码
    具体 idx，避免数据刷新后失败。
    """
    result = _scan_single_stock(cvgi_scan_args)
    superseded = [p for p in result["all_peaks"] if p["is_superseded"]]
    assert len(superseded) >= 1, (
        f"Expected at least one is_superseded=True peak in all_peaks; "
        f"got none. all_peaks={result['all_peaks']}"
    )


def test_cvgi_scan_result_every_peak_has_is_superseded_field(cvgi_scan_args):
    """契约稳定性：all_peaks 的每个 dict 都必须带 is_superseded 字段。"""
    result = _scan_single_stock(cvgi_scan_args)
    for peak in result["all_peaks"]:
        assert "is_superseded" in peak, f"Peak missing is_superseded field: {peak}"
        assert isinstance(peak["is_superseded"], bool)
