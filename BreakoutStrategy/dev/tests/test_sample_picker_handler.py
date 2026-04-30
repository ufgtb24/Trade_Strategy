"""sample_picker_handler 单元测试。

handler 是连接 KeyboardPicker 与 feature_library.preprocess 的胶水：
- 输入：(left_idx, right_idx, ticker, df, picked_at, backend, on_done)
- 输出：调用 preprocess_sample(...) + on_done 回调
- 切片策略：bo_index 前 200 bars，全局 → 局部 index 转换

注：plan 03(D-05)起，sample_renderer 的形参 pk_index 重命名为 left_index，
在 sample_picker_handler 这一层 local_pk 仍是数据语义的 anchor 候选（用户挑的左端
≡ consolidation anchor），preprocess_sample 收 pk_index= 时不变；只是渲染层视角下
它叫 left_index。本测试断言 kwargs["pk_index"] == 50 仍然有效（preprocess_sample
的 API 形参名未改 — 只有 sample_renderer 的形参名改了）。
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


@pytest.fixture
def df_300_bars():
    """300 bar 的 DataFrame，模拟 dev UI 的 current_df。"""
    return pd.DataFrame(
        {
            "open":   [100.0 + i * 0.1 for i in range(300)],
            "high":   [101.0 + i * 0.1 for i in range(300)],
            "low":    [99.0  + i * 0.1 for i in range(300)],
            "close":  [100.5 + i * 0.1 for i in range(300)],
            "volume": [1e6  + i * 1000 for i in range(300)],
        },
        index=pd.date_range("2023-01-01", periods=300, freq="B"),
    )


def test_handle_endpoints_picked_calls_preprocess_with_local_indices(
    df_300_bars,
):
    """当 left=100, right=250 时，应裁 [50:251] 作 df_window，
    传给 preprocess_sample 的 local bo=200, pk=50。"""
    from BreakoutStrategy.dev.sample_picker_handler import handle_endpoints_picked

    backend = MagicMock(name="GLM4VBackend")
    backend.describe_chart.return_value = "mocked nl description"
    on_done = MagicMock(name="on_done")

    with patch(
        "BreakoutStrategy.dev.sample_picker_handler.preprocess_sample"
    ) as mock_preprocess:
        mock_preprocess.return_value = "BO_AAPL_20230918"
        handle_endpoints_picked(
            left_idx=100,
            right_idx=250,
            ticker="AAPL",
            df=df_300_bars,
            picked_at=datetime(2024, 1, 1, 10, 0, 0),
            backend=backend,
            on_done=on_done,
        )

    assert mock_preprocess.called, "应调 preprocess_sample"
    kwargs = mock_preprocess.call_args.kwargs
    assert kwargs["ticker"] == "AAPL"
    assert kwargs["bo_date"] == df_300_bars.index[250]
    # window_start = max(0, 250 - 200) = 50；df_window = df.iloc[50:251] (201 bars)
    assert len(kwargs["df_window"]) == 201
    # 局部 bo_index = 250 - 50 = 200
    assert kwargs["bo_index"] == 200
    # pk_index 是 preprocess_sample API 形参名（数据层 anchor 语义）；
    # 渲染层在 plan 03 改名为 left_index，但本调用边界不影响。
    # 局部 pk_index = 100 - 50 = 50
    assert kwargs["pk_index"] == 50  # noqa: 数据层 anchor；渲染层改名为 left_index（D-05）
    assert kwargs["picked_at"] == datetime(2024, 1, 1, 10, 0, 0)
    assert kwargs["backend"] is backend

    # on_done 用 sample_id 调用
    on_done.assert_called_once_with("BO_AAPL_20230918")


def test_handle_endpoints_picked_clamps_window_start_at_zero(df_300_bars):
    """当 right < 200 时 window_start 应钳到 0，不应负数索引。"""
    from BreakoutStrategy.dev.sample_picker_handler import handle_endpoints_picked

    with patch(
        "BreakoutStrategy.dev.sample_picker_handler.preprocess_sample"
    ) as mock_preprocess:
        mock_preprocess.return_value = "BO_AAPL_20230301"
        handle_endpoints_picked(
            left_idx=20, right_idx=50,
            ticker="AAPL", df=df_300_bars,
            picked_at=datetime.now(), backend=MagicMock(),
            on_done=lambda sid: None,
        )

    kwargs = mock_preprocess.call_args.kwargs
    # window_start = max(0, 50 - 200) = 0；df_window = df.iloc[0:51] (51 bars)
    assert len(kwargs["df_window"]) == 51
    assert kwargs["bo_index"] == 50
    assert kwargs["pk_index"] == 20


def test_handle_endpoints_picked_propagates_preprocess_failure(df_300_bars):
    """preprocess_sample 抛异常时，handler 应捕获并调 on_done(None) +
    不让异常逃逸（避免 Tk 主循环挂掉）。"""
    from BreakoutStrategy.dev.sample_picker_handler import handle_endpoints_picked

    on_done = MagicMock()

    with patch(
        "BreakoutStrategy.dev.sample_picker_handler.preprocess_sample"
    ) as mock_preprocess:
        mock_preprocess.side_effect = RuntimeError("backend 调用失败")
        handle_endpoints_picked(
            left_idx=100, right_idx=250,
            ticker="AAPL", df=df_300_bars,
            picked_at=datetime.now(), backend=MagicMock(),
            on_done=on_done,
        )

    on_done.assert_called_once_with(None)   # 失败时传 None


def test_lazy_glm4v_singleton_caches_instance(tmp_path, monkeypatch):
    """get_glm4v_backend_lazy 多次调用应返回同一实例（单例）。"""
    from BreakoutStrategy.dev import sample_picker_handler

    # mock 一个最小 api_keys.yaml
    keys_file = tmp_path / "api_keys.yaml"
    keys_file.write_text("zhipuai: \"fake_key_for_test\"\n")
    monkeypatch.setattr(
        sample_picker_handler, "_API_KEYS_PATH", keys_file,
    )
    # 重置缓存
    sample_picker_handler._GLM4V_SINGLETON = None

    inst1 = sample_picker_handler.get_glm4v_backend_lazy()
    inst2 = sample_picker_handler.get_glm4v_backend_lazy()
    assert inst1 is inst2, "应返回同一单例"
    # 类型应为 GLM4VBackend
    from BreakoutStrategy.feature_library.glm4v_backend import GLM4VBackend
    assert isinstance(inst1, GLM4VBackend)


def test_lazy_glm4v_returns_none_when_api_key_missing(tmp_path, monkeypatch):
    """api_keys.yaml 缺失或 zhipuai key 为空时返回 None（picker 应禁用）。"""
    from BreakoutStrategy.dev import sample_picker_handler

    empty = tmp_path / "api_keys_missing.yaml"
    empty.write_text("zhipuai: \"\"\n")
    monkeypatch.setattr(
        sample_picker_handler, "_API_KEYS_PATH", empty,
    )
    sample_picker_handler._GLM4V_SINGLETON = None

    assert sample_picker_handler.get_glm4v_backend_lazy() is None
