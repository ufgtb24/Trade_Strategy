"""Tests for nl_description prompts."""
from BreakoutStrategy.feature_library.prompts import (
    SYSTEM_PROMPT, build_user_message,
)


def test_system_prompt_non_empty():
    assert SYSTEM_PROMPT
    assert "K-line" in SYSTEM_PROMPT or "K 线" in SYSTEM_PROMPT


def test_user_message_includes_meta_fields():
    """脱敏后 user_message 应含无量纲字段，不含 ticker / bo_date / 绝对价。"""
    meta = {
        "sample_id": "BO_AAPL_20230115",
        "ticker": "AAPL",
        "bo_date": "2023-01-15",
        "breakout_day": {
            "open": 130.0, "high": 135.0, "low": 129.0,
            "close": 134.0, "volume": 100_000_000,
        },
        "consolidation": {
            "consolidation_length_bars": 30,
            "consolidation_height_pct": 5.2,
            "consolidation_position_vs_52w_high": -3.1,
            "consolidation_volume_ratio": 0.55,
            "consolidation_tightness_atr": 1.8,
            "pivot_close": 125.0,
        },
    }
    msg = build_user_message(meta)
    # 脱敏：不含 ticker / bo_date / 绝对价
    assert "AAPL" not in msg
    assert "2023-01-15" not in msg
    assert "130.00" not in msg
    # 无量纲字段保留
    assert "30" in msg  # length_bars
    assert "5.20" in msg  # height_pct（fmt_num 格式化后）
    assert "%" in msg  # OHLC 相对 % 存在


def test_user_message_handles_null_fields():
    """盘整字段为 None 时应显示 N/A，不含 ticker / bo_date / 绝对价。"""
    meta = {
        "sample_id": "BO_AAPL_20230115",
        "ticker": "AAPL",
        "bo_date": "2023-01-15",
        "breakout_day": {
            "open": 130.0, "high": 135.0, "low": 129.0,
            "close": 134.0, "volume": 100_000_000,
        },
        "consolidation": {
            "consolidation_length_bars": 30,
            "consolidation_height_pct": None,
            "consolidation_position_vs_52w_high": None,
            "consolidation_volume_ratio": 0.55,
            "consolidation_tightness_atr": None,
            "pivot_close": 125.0,
        },
    }
    msg = build_user_message(meta)
    # None 字段显示 N/A
    assert "N/A" in msg or "null" in msg or "unknown" in msg.lower()
    # 脱敏：不含 ticker / bo_date / 绝对价
    assert "AAPL" not in msg
    assert "2023-01-15" not in msg
    assert "130.00" not in msg


def test_build_user_message_anonymizes_ticker_date_and_absolute_price():
    """归一化方案 B：user_message 不应泄漏 ticker / bo_date / 绝对价位。"""
    meta = {
        "sample_id": "BO_AAPL_20240105",
        "ticker": "AAPL",
        "bo_date": "2024-01-05",
        "picked_at": "2024-01-05T10:00:00",
        "breakout_day": {
            "open": 132.50, "high": 134.80, "low": 131.20,
            "close": 134.10, "volume": 85432100.0,
        },
        "consolidation": {
            "consolidation_length_bars": 22,
            "consolidation_height_pct": 5.20,
            "consolidation_position_vs_52w_high": -3.10,
            "consolidation_volume_ratio": 0.85,
            "consolidation_tightness_atr": 3.40,
            "pivot_close": 127.50,  # 新增字段：归一化的 pivot 基准
        },
    }
    msg = build_user_message(meta)

    # 不应含 ticker
    assert "AAPL" not in msg, f"user_message 不应含 ticker: {msg!r}"
    # 不应含具体日期
    assert "2024-01-05" not in msg, f"user_message 不应含 bo_date: {msg!r}"
    # 不应含绝对价位（132.50, 134.80, 131.20, 134.10）
    for absolute_price in ("132.50", "134.80", "131.20", "134.10"):
        assert absolute_price not in msg, \
            f"user_message 不应含绝对价 {absolute_price}: {msg!r}"
    # 不应含绝对成交量
    assert "85432100" not in msg and "85432100.00" not in msg, \
        f"user_message 不应含绝对成交量: {msg!r}"

    # 应含相对值（OHLC vs pivot）—— 132.50 vs 127.50 = +3.92%
    assert "%" in msg, f"应含百分比脱敏数值: {msg!r}"
    # 5 个盘整字段（已是无量纲）应保留
    assert "5.20" in msg, "盘整高度 5.20% 应保留"
    assert "22" in msg, "盘整 length 22 bars 应保留"


def test_build_user_message_handles_missing_pivot_close_gracefully():
    """pivot_close 缺失时降级为不显示绝对价（仍不泄漏）。"""
    meta = {
        "sample_id": "BO_TEST_20240101",
        "ticker": "TEST",
        "bo_date": "2024-01-01",
        "picked_at": "2024-01-01T00:00:00",
        "breakout_day": {
            "open": 100.0, "high": 105.0, "low": 99.0,
            "close": 104.0, "volume": 1e6,
        },
        "consolidation": {
            "consolidation_length_bars": 10,
            "consolidation_height_pct": 3.0,
            "consolidation_position_vs_52w_high": -5.0,
            "consolidation_volume_ratio": 0.8,
            "consolidation_tightness_atr": 2.5,
            # 没有 pivot_close
        },
    }
    msg = build_user_message(meta)
    # 仍不应泄漏
    assert "TEST" not in msg
    assert "100.00" not in msg and "104.00" not in msg


def test_build_user_message_uses_bo_close_as_pivot():
    """D-08: OHLC 相对参考改用 bo['close']（= 突破日 close，与 chart.png Y 轴零点一致）。"""
    meta = {
        "sample_id": "BO_TEST_20240101",
        "ticker": "TEST",
        "bo_date": "2024-01-01",
        "breakout_day": {
            "open": 130.0, "high": 135.0, "low": 129.0,
            "close": 134.0, "volume": 1e6,
        },
        "consolidation": {
            "consolidation_length_bars": 30,
            "consolidation_height_pct": 5.0,
            "consolidation_position_vs_52w_high": -3.0,
            "consolidation_volume_ratio": 0.6,
            "consolidation_tightness_atr": 1.5,
            "pivot_close": 125.0,  # 仍存在，但 prompt OHLC 不应再用它
        },
    }
    msg = build_user_message(meta)
    # 新文案应含"突破日 close"作锚点描述
    assert "突破日 close" in msg, f"应注明 BO close 为锚点: {msg!r}"
    # close 行应显示 +0.00%（BO close 相对自身）
    assert "close=+0.00%" in msg, f"close 行应为 +0.00%: {msg!r}"
    # open=130 vs bo_close=134 = -2.99%（不是相对 pivot_close=125 的 +4.00%）
    assert "open=-2.99%" in msg, f"open 应相对 bo_close=134 计算: {msg!r}"
    # 验证不再用 pivot_close=125（相对 125 的话 open 是 +4.00%）
    assert "+4.00%" not in msg, "OHLC 不应再用 consolidation.pivot_close 作锚点"


def test_build_user_message_handles_missing_bo_close_gracefully():
    """bo['close'] 缺失或非正时降级为'相对价段 N/A'，不泄漏绝对价。"""
    meta = {
        "sample_id": "BO_TEST_20240101",
        "ticker": "TEST", "bo_date": "2024-01-01",
        "breakout_day": {
            "open": 100.0, "high": 105.0, "low": 99.0,
            "close": 0.0, "volume": 1e6,   # close = 0，异常数据
        },
        "consolidation": {
            "consolidation_length_bars": 10,
            "consolidation_height_pct": 3.0,
            "consolidation_position_vs_52w_high": -5.0,
            "consolidation_volume_ratio": 0.8,
            "consolidation_tightness_atr": 2.5,
            "pivot_close": 95.0,
        },
    }
    msg = build_user_message(meta)
    # 应降级到 N/A 文本
    assert "N/A" in msg or "bo_close 缺失" in msg
    # 不应泄漏绝对价
    for absolute in ("100.00", "105.00", "99.00"):
        assert absolute not in msg, f"不应含绝对价 {absolute}"
