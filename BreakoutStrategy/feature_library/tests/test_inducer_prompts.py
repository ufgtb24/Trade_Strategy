"""Tests for inducer_prompts."""
from BreakoutStrategy.feature_library.inducer_prompts import (
    INDUCER_SYSTEM_PROMPT, build_batch_user_message,
)


def test_system_prompt_requires_yaml_format():
    """SYSTEM_PROMPT 应明确要求 YAML 输出，不允许 markdown 代码块。"""
    assert "yaml" in INDUCER_SYSTEM_PROMPT.lower() or "YAML" in INDUCER_SYSTEM_PROMPT
    assert "candidates:" in INDUCER_SYSTEM_PROMPT


def test_system_prompt_requires_K_at_least_2():
    """SYSTEM_PROMPT 应要求 K ≥ 2 以排除单图噪声。"""
    assert "≥ 2" in INDUCER_SYSTEM_PROMPT or ">= 2" in INDUCER_SYSTEM_PROMPT or "至少 2" in INDUCER_SYSTEM_PROMPT


def test_system_prompt_requires_supporting_sample_ids():
    assert "supporting_sample_ids" in INDUCER_SYSTEM_PROMPT


def test_build_batch_user_message_contains_figure_indices():
    """脱敏后 user message 应含 [1]/[2] 匿名编号，而不含 ticker/bo_date。"""
    metas = [
        {
            "sample_id": "BO_AAPL_20210617",
            "ticker": "AAPL", "bo_date": "2021-06-17",
            "breakout_day": {"open": 130, "high": 135, "low": 129, "close": 134, "volume": 100_000_000},
            "consolidation": {
                "consolidation_length_bars": 30,
                "consolidation_height_pct": 5.2,
                "consolidation_position_vs_52w_high": -3.1,
                "consolidation_volume_ratio": 0.55,
                "consolidation_tightness_atr": 1.8,
                "pivot_close": 125.0,
            },
        },
        {
            "sample_id": "BO_MSFT_20220301",
            "ticker": "MSFT", "bo_date": "2022-03-01",
            "breakout_day": {"open": 290, "high": 300, "low": 289, "close": 298, "volume": 50_000_000},
            "consolidation": {
                "consolidation_length_bars": 25,
                "consolidation_height_pct": 4.0,
                "consolidation_position_vs_52w_high": -1.0,
                "consolidation_volume_ratio": 0.62,
                "consolidation_tightness_atr": 1.5,
                "pivot_close": 280.0,
            },
        },
    ]
    msg = build_batch_user_message(metas)
    # 脱敏后不应含真实 ticker / bo_date / sample_id
    assert "AAPL" not in msg
    assert "MSFT" not in msg
    assert "2021-06-17" not in msg
    assert "2022-03-01" not in msg
    # 应含 [1] / [2] 匿名编号
    assert "[1]" in msg
    assert "[2]" in msg


def test_build_batch_user_message_handles_null_consolidation_field():
    metas = [
        {
            "sample_id": "BO_TEST_20240101",
            "ticker": "TEST", "bo_date": "2024-01-01",
            "breakout_day": {"open": 10, "high": 11, "low": 10, "close": 11, "volume": 1_000_000},
            "consolidation": {
                "consolidation_length_bars": 5,
                "consolidation_height_pct": None,
                "consolidation_position_vs_52w_high": None,
                "consolidation_volume_ratio": 0.7,
                "consolidation_tightness_atr": None,
                "pivot_close": 9.5,
            },
        },
    ]
    msg = build_batch_user_message(metas)
    assert "N/A" in msg or "未知" in msg


def test_build_batch_user_message_numbers_each_sample():
    """user message 中每个 sample 应有 [1] [2] 这样的编号便于模型对应图序。"""
    metas = [
        {"sample_id": f"BO_S{i}_20240101", "ticker": "S", "bo_date": "2024-01-01",
         "breakout_day": {"open": 10, "high": 11, "low": 9, "close": 10, "volume": 1},
         "consolidation": {"consolidation_length_bars": 1, "consolidation_height_pct": 1.0,
                           "consolidation_position_vs_52w_high": 0.0,
                           "consolidation_volume_ratio": 1.0,
                           "consolidation_tightness_atr": 1.0,
                           "pivot_close": 10.0}}
        for i in range(3)
    ]
    msg = build_batch_user_message(metas)
    assert "[1]" in msg
    assert "[2]" in msg
    assert "[3]" in msg


def test_build_batch_user_message_anonymizes_each_sample():
    """归一化方案 B：每个 sample 块不应泄漏 ticker / bo_date / 绝对价。"""
    samples = [
        {
            "sample_id": "BO_AAPL_20210617",
            "ticker": "AAPL",
            "bo_date": "2021-06-17",
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
                "pivot_close": 127.50,
            },
        },
        {
            "sample_id": "BO_MSFT_20220301",
            "ticker": "MSFT",
            "bo_date": "2022-03-01",
            "breakout_day": {
                "open": 285.0, "high": 290.0, "low": 282.0,
                "close": 289.0, "volume": 30000000.0,
            },
            "consolidation": {
                "consolidation_length_bars": 18,
                "consolidation_height_pct": 4.0,
                "consolidation_position_vs_52w_high": -2.5,
                "consolidation_volume_ratio": 0.9,
                "consolidation_tightness_atr": 2.8,
                "pivot_close": 280.0,
            },
        },
    ]
    msg = build_batch_user_message(samples)

    # 不应含 ticker
    for ticker in ("AAPL", "MSFT"):
        assert ticker not in msg, f"batch_user_message 不应含 {ticker}: {msg[:200]!r}"
    # 不应含 bo_date
    for date in ("2021-06-17", "2022-03-01"):
        assert date not in msg, f"batch_user_message 不应含 {date}: {msg[:200]!r}"
    # 不应含 sample_id（含 ticker + 日期）
    for sid in ("BO_AAPL_20210617", "BO_MSFT_20220301"):
        assert sid not in msg, f"batch_user_message 不应含 sample_id {sid}"
    # 不应含绝对价
    for absolute_price in ("132.50", "134.80", "285.00", "290.00"):
        assert absolute_price not in msg, \
            f"batch_user_message 不应含绝对价 {absolute_price}"

    # 应使用 [1] / [2] 匿名编号
    assert "[1]" in msg and "[2]" in msg, "应使用 [1] / [2] 匿名图序"
    # 5 个盘整字段保留
    assert "5.20" in msg and "4.00" in msg, "盘整字段应保留"


def test_build_batch_user_message_returns_anonymous_id_mapping():
    """归一化后调用方需要知道 [1]/[2] → 真实 sample_id 的映射，
    用于 supporting_sample_ids 反向解析。返回 (msg, id_map)。"""
    samples = [
        {
            "sample_id": "BO_AAPL_20210617",
            "ticker": "AAPL", "bo_date": "2021-06-17",
            "breakout_day": {"open": 100.0, "high": 105.0, "low": 99.0,
                             "close": 104.0, "volume": 1e6},
            "consolidation": {
                "consolidation_length_bars": 10,
                "consolidation_height_pct": 3.0,
                "consolidation_position_vs_52w_high": -5.0,
                "consolidation_volume_ratio": 0.8,
                "consolidation_tightness_atr": 2.5,
                "pivot_close": 100.0,
            },
        },
    ]
    msg, id_map = build_batch_user_message(samples, return_id_map=True)
    assert id_map == {"[1]": "BO_AAPL_20210617"}
    assert "[1]" in msg
    assert "AAPL" not in msg


def test_build_batch_user_message_uses_bo_close_as_pivot():
    """D-08: 每条 sample 的 OHLC 相对参考用 bo['close']。"""
    metas = [
        {
            "sample_id": "BO_AAPL_20210617",
            "ticker": "AAPL", "bo_date": "2021-06-17",
            "breakout_day": {"open": 130.0, "high": 135.0, "low": 129.0,
                             "close": 134.0, "volume": 1e6},
            "consolidation": {
                "consolidation_length_bars": 30,
                "consolidation_height_pct": 5.2,
                "consolidation_position_vs_52w_high": -3.1,
                "consolidation_volume_ratio": 0.55,
                "consolidation_tightness_atr": 1.8,
                "pivot_close": 125.0,   # 不应再被 OHLC 段使用
            },
        },
    ]
    msg = build_batch_user_message(metas)
    # 标签改为 vs bo_close
    assert "vs bo_close" in msg, f"标签应为 'vs bo_close'，msg={msg!r}"
    assert "vs pk_close" not in msg, "不应再含 'vs pk_close'"
    # close 行恒为 +0.00%
    assert "close=+0.00%" in msg, f"close 行应为 +0.00%: {msg!r}"
    # open=130 vs bo_close=134 ≈ -2.99%
    assert "open=-2.99%" in msg, f"open 应相对 bo_close=134 计算: {msg!r}"
    # 不应使用 pivot_close=125（相对 125 的话 open=+4.00%）
    assert "+4.00%" not in msg, "OHLC 不应再用 consolidation.pivot_close 作锚点"


def test_build_batch_user_message_handles_missing_bo_close_gracefully():
    """bo['close'] 缺失或非正时降级为 N/A，不泄漏绝对价。"""
    metas = [{
        "sample_id": "BO_TEST_20240101",
        "ticker": "TEST", "bo_date": "2024-01-01",
        "breakout_day": {"open": 100.0, "high": 105.0, "low": 99.0,
                         "close": 0.0, "volume": 1e6},  # close=0
        "consolidation": {
            "consolidation_length_bars": 5,
            "consolidation_height_pct": 1.0,
            "consolidation_position_vs_52w_high": -1.0,
            "consolidation_volume_ratio": 0.8,
            "consolidation_tightness_atr": 1.5,
            "pivot_close": 95.0,
        },
    }]
    msg = build_batch_user_message(metas)
    assert "bo_close missing" in msg or "N/A" in msg
    for absolute in ("100.00", "105.00", "99.00"):
        assert absolute not in msg
