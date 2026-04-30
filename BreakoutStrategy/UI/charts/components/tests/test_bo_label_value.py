"""Tests for BO label value marker rendering (tier classification + positioning)."""
import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
import pytest
from types import SimpleNamespace

from BreakoutStrategy.UI.charts.components.markers import MarkerComponent
from BreakoutStrategy.UI.styles import BO_LABEL_VALUE_TIER_STYLE


@pytest.fixture
def ax_and_df():
    # 20 根 K 线，close 逐日上涨；提供足够的未来数据使 label_n<=10 都可算
    fig, ax = plt.subplots(figsize=(6, 4))
    closes = [10.0 + i * 0.5 for i in range(20)]
    df = pd.DataFrame({
        "open":  closes,
        "high":  [c * 1.01 for c in closes],
        "low":   [c * 0.99 for c in closes],
        "close": closes,
        "volume": [1000] * 20,
    })
    ax.plot(range(20), df["close"])
    ax.set_ylim(8, 25)
    yield ax, df
    plt.close(fig)


def _find_annotation_by_bbox_facecolor(ax, hex_color: str):
    """返回 bbox facecolor 匹配 hex_color 的所有 annotation。"""
    from matplotlib.colors import to_hex
    matches = []
    for t in ax.texts:
        bbox = t.get_bbox_patch()
        if bbox is None:
            continue
        fc = to_hex(bbox.get_facecolor(), keep_alpha=False).lower()
        if fc == hex_color.lower():
            matches.append(t)
    return matches


def test_show_label_off_by_default_no_label_value_annotation(ax_and_df):
    ax, df = ax_and_df
    bo = SimpleNamespace(index=2, price=df.iloc[2]["close"], broken_peak_ids=[5], quality_score=80.0)
    MarkerComponent.draw_breakouts(ax, df, [bo], peaks=[])
    yellow = _find_annotation_by_bbox_facecolor(ax, "#FFD700")
    orange = _find_annotation_by_bbox_facecolor(ax, "#FFA500")
    assert yellow == []
    assert orange == []


def test_single_bo_with_show_label_is_max_tier(ax_and_df):
    ax, df = ax_and_df
    bo = SimpleNamespace(index=2, price=df.iloc[2]["close"], broken_peak_ids=[5], quality_score=80.0)
    MarkerComponent.draw_breakouts(
        ax, df, [bo], peaks=[],
        show_label=True, label_n=5,
    )
    yellow = _find_annotation_by_bbox_facecolor(ax, "#FFD700")
    assert len(yellow) == 1
    # 单值即是 max；应为百分比格式，带 + 号（closes 逐日上涨故 value > 0）
    assert "%" in yellow[0].get_text()
    assert yellow[0].get_text().startswith("+")


def test_multi_bo_max_vs_other_tier(ax_and_df):
    ax, df = ax_and_df
    # index=2 close=11.0；label_n=3 future max in [3:6] = max(11.5,12,12.5)=12.5 → (12.5-11)/11 ≈ 0.1364
    # index=5 close=12.5；future in [6:9] = max(13,13.5,14)=14 → (14-12.5)/12.5 = 0.12
    # index=10 close=15.0；future in [11:14] = max(15.5,16,16.5)=16.5 → (16.5-15)/15 = 0.1
    # 故 index=2 的 BO 为 max
    bos = [
        SimpleNamespace(index=2,  price=df.iloc[2]["close"],  broken_peak_ids=[1], quality_score=70.0),
        SimpleNamespace(index=5,  price=df.iloc[5]["close"],  broken_peak_ids=[2], quality_score=75.0),
        SimpleNamespace(index=10, price=df.iloc[10]["close"], broken_peak_ids=[3], quality_score=80.0),
    ]
    MarkerComponent.draw_breakouts(
        ax, df, bos, peaks=[],
        show_label=True, label_n=3,
    )
    yellow = _find_annotation_by_bbox_facecolor(ax, "#FFD700")
    orange = _find_annotation_by_bbox_facecolor(ax, "#FFA500")
    assert len(yellow) == 1
    assert len(orange) == 2


def test_insufficient_future_data_skipped(ax_and_df):
    ax, df = ax_and_df
    # 位于倒数第 2 行，label_n=5 未来不够 5 天
    bo = SimpleNamespace(index=18, price=df.iloc[18]["close"], broken_peak_ids=[1], quality_score=70.0)
    MarkerComponent.draw_breakouts(
        ax, df, [bo], peaks=[],
        show_label=True, label_n=5,
    )
    yellow = _find_annotation_by_bbox_facecolor(ax, "#FFD700")
    orange = _find_annotation_by_bbox_facecolor(ax, "#FFA500")
    assert yellow == []
    assert orange == []


def test_all_none_values_no_annotation(ax_and_df):
    ax, df = ax_and_df
    # 所有 BO 都在 df 末端，label_n=10 数据不够
    bos = [
        SimpleNamespace(index=18, price=df.iloc[18]["close"], broken_peak_ids=[1], quality_score=70.0),
        SimpleNamespace(index=19, price=df.iloc[19]["close"], broken_peak_ids=[2], quality_score=75.0),
    ]
    MarkerComponent.draw_breakouts(
        ax, df, bos, peaks=[],
        show_label=True, label_n=10,
    )
    yellow = _find_annotation_by_bbox_facecolor(ax, "#FFD700")
    orange = _find_annotation_by_bbox_facecolor(ax, "#FFA500")
    assert yellow == []
    assert orange == []


def test_tied_max_values_all_get_max_tier(ax_and_df):
    """多个 BO value 并列最大时，全部标为 max tier。"""
    ax, df = ax_and_df
    # 构造 df 使 index=2 和 index=5 的 3-day future max 都等于 11.0
    closes = [10.0] * 20
    closes[3] = 11.0
    closes[4] = 11.0
    closes[6] = 11.0
    closes[7] = 11.0
    df_tied = pd.DataFrame({
        "open": closes, "high": [c * 1.01 for c in closes],
        "low": [c * 0.99 for c in closes], "close": closes, "volume": [1000] * 20,
    })
    bos = [
        SimpleNamespace(index=2, price=10.0, broken_peak_ids=[1], quality_score=70.0),
        SimpleNamespace(index=5, price=10.0, broken_peak_ids=[2], quality_score=75.0),
    ]
    MarkerComponent.draw_breakouts(
        ax, df_tied, bos, peaks=[],
        show_label=True, label_n=3,
    )
    yellow = _find_annotation_by_bbox_facecolor(ax, "#FFD700")
    orange = _find_annotation_by_bbox_facecolor(ax, "#FFA500")
    assert len(yellow) == 2
    assert len(orange) == 0


def test_label_value_offset_above_bo_score(ax_and_df):
    """label_value annotation y offset (pure BO, no peak, with score+label):
    bo_label(14) + bo_score(30) + bo_label_value(30) = 74.
    """
    ax, df = ax_and_df
    bo = SimpleNamespace(index=2, price=df.iloc[2]["close"], broken_peak_ids=[5], quality_score=80.0)
    MarkerComponent.draw_breakouts(
        ax, df, [bo], peaks=[],
        show_score=True, show_label=True, label_n=3,
    )
    yellow = _find_annotation_by_bbox_facecolor(ax, "#FFD700")
    assert len(yellow) == 1
    assert yellow[0].xyann[1] == pytest.approx(74)


def test_label_value_without_score_takes_score_slot(ax_and_df):
    """开 BO Label、关 BO Score：label_value 退到 bo_score 原本的位置。
    bo_label(14) + bo_label_value(30) = 44 (pure BO, no peak).
    """
    ax, df = ax_and_df
    bo = SimpleNamespace(index=2, price=df.iloc[2]["close"], broken_peak_ids=[5], quality_score=80.0)
    MarkerComponent.draw_breakouts(
        ax, df, [bo], peaks=[],
        show_score=False, show_label=True, label_n=3,
    )
    yellow = _find_annotation_by_bbox_facecolor(ax, "#FFD700")
    assert len(yellow) == 1
    assert yellow[0].xyann[1] == pytest.approx(44)


def test_max_tier_has_higher_zorder_than_other_tier(ax_and_df):
    """Max tier (yellow) 的 zorder 必须高于 other tier (orange)，保证重合时黄色可见。"""
    ax, df = ax_and_df
    # 使用 test_multi_bo_max_vs_other_tier 相同的数据结构
    bos = [
        SimpleNamespace(index=2,  price=df.iloc[2]["close"],  broken_peak_ids=[1], quality_score=70.0),
        SimpleNamespace(index=5,  price=df.iloc[5]["close"],  broken_peak_ids=[2], quality_score=75.0),
        SimpleNamespace(index=10, price=df.iloc[10]["close"], broken_peak_ids=[3], quality_score=80.0),
    ]
    MarkerComponent.draw_breakouts(
        ax, df, bos, peaks=[],
        show_label=True, label_n=3,
    )
    yellow_annots = _find_annotation_by_bbox_facecolor(ax, "#FFD700")
    orange_annots = _find_annotation_by_bbox_facecolor(ax, "#FFA500")
    assert len(yellow_annots) == 1 and len(orange_annots) >= 1
    max_orange_zorder = max(a.get_zorder() for a in orange_annots)
    assert yellow_annots[0].get_zorder() > max_orange_zorder
