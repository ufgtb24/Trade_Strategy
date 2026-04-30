"""Tests for GLM-4V-Flash multimodal backend."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from BreakoutStrategy.feature_library.glm4v_backend import GLM4VBackend


@pytest.fixture
def fake_chart(tmp_path) -> Path:
    p = tmp_path / "chart.png"
    p.write_bytes(b"fake-png-bytes-for-test")
    return p


def test_describe_chart_returns_string(fake_chart):
    backend = GLM4VBackend(api_key="test-key")
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(
        content="这是一段 GLM-4V-Flash 返回的 K 线描述。",
        reasoning_content=None,
    ))]
    with patch.object(backend._client.chat.completions, "create",
                      return_value=fake_response) as mock_create:
        result = backend.describe_chart(
            chart_path=fake_chart,
            user_message="标的：AAPL\n突破日：2023-01-15",
        )

    assert result == "这是一段 GLM-4V-Flash 返回的 K 线描述。"
    mock_create.assert_called_once()
    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["model"] == "glm-4v-flash"
    assert call_kwargs["temperature"] == 0.3
    messages = call_kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    user_content = messages[1]["content"]
    assert isinstance(user_content, list)
    assert any(c["type"] == "image_url" for c in user_content)
    assert any(c["type"] == "text" for c in user_content)


def test_describe_chart_image_is_base64_data_url(fake_chart):
    backend = GLM4VBackend(api_key="test-key")
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(
        content="ok", reasoning_content=None,
    ))]
    with patch.object(backend._client.chat.completions, "create",
                      return_value=fake_response) as mock_create:
        backend.describe_chart(
            chart_path=fake_chart, user_message="ctx",
        )
    user_content = mock_create.call_args.kwargs["messages"][1]["content"]
    image_block = next(c for c in user_content if c["type"] == "image_url")
    url = image_block["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")


def test_describe_chart_retries_once_on_exception(fake_chart):
    backend = GLM4VBackend(api_key="test-key")
    fake_ok = MagicMock()
    fake_ok.choices = [MagicMock(message=MagicMock(
        content="recovered", reasoning_content=None,
    ))]

    with patch.object(backend._client.chat.completions, "create",
                      side_effect=[Exception("transient"), fake_ok]) as mock_create:
        result = backend.describe_chart(
            chart_path=fake_chart, user_message="ctx",
        )
    assert result == "recovered"
    assert mock_create.call_count == 2


def test_describe_chart_returns_empty_after_two_failures(fake_chart):
    backend = GLM4VBackend(api_key="test-key")
    with patch.object(backend._client.chat.completions, "create",
                      side_effect=Exception("permanent")) as mock_create:
        result = backend.describe_chart(
            chart_path=fake_chart, user_message="ctx",
        )
    assert result == ""
    assert mock_create.call_count == 2  # 防退化检测


def test_extract_content_falls_back_to_reasoning(fake_chart):
    """thinking 模式下 content 为空时应从 reasoning_content 回收。"""
    backend = GLM4VBackend(api_key="test-key")
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(
        content="", reasoning_content="思考后输出：xxx 描述",
    ))]
    with patch.object(backend._client.chat.completions, "create",
                      return_value=fake_response):
        result = backend.describe_chart(
            chart_path=fake_chart, user_message="ctx",
        )
    assert "xxx 描述" in result


def test_init_raises_on_empty_api_key():
    with pytest.raises(ValueError, match="zhipuai api_key"):
        GLM4VBackend(api_key="")


def test_init_raises_on_whitespace_api_key():
    with pytest.raises(ValueError, match="zhipuai api_key"):
        GLM4VBackend(api_key="   ")


def test_batch_describe_sends_multiple_image_blocks(tmp_path):
    """batch_describe 应在一个 user content 中塞多个 image_url 块。"""
    from unittest.mock import MagicMock, patch
    from BreakoutStrategy.feature_library.glm4v_backend import GLM4VBackend

    # 准备 3 张假图
    chart_paths = []
    for i in range(3):
        p = tmp_path / f"chart_{i}.png"
        p.write_bytes(f"fake-png-{i}".encode())
        chart_paths.append(p)

    backend = GLM4VBackend(api_key="test-key")
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(
        content="batch result", reasoning_content=None,
    ))]

    with patch.object(backend._client.chat.completions, "create",
                      return_value=fake_response) as mock_create:
        result = backend.batch_describe(
            chart_paths=chart_paths,
            user_message="请归纳这 3 张图的共性",
        )

    assert result == "batch result"
    user_content = mock_create.call_args.kwargs["messages"][1]["content"]
    image_blocks = [c for c in user_content if c["type"] == "image_url"]
    text_blocks = [c for c in user_content if c["type"] == "text"]
    assert len(image_blocks) == 3
    assert len(text_blocks) == 1
    # 顺序：所有 image 在前，text 在后（Inducer 看完图再读说明）
    image_indices = [i for i, c in enumerate(user_content) if c["type"] == "image_url"]
    text_indices = [i for i, c in enumerate(user_content) if c["type"] == "text"]
    assert max(image_indices) < min(text_indices)


def test_batch_describe_raises_on_too_many_images(tmp_path):
    """超过 5 张应在调用 API 前 raise ValueError。"""
    from BreakoutStrategy.feature_library.glm4v_backend import GLM4VBackend, GLM4V_MAX_IMAGES

    chart_paths = []
    for i in range(GLM4V_MAX_IMAGES + 1):
        p = tmp_path / f"chart_{i}.png"
        p.write_bytes(b"fake")
        chart_paths.append(p)

    backend = GLM4VBackend(api_key="test-key")
    with pytest.raises(ValueError, match="too many images"):
        backend.batch_describe(chart_paths=chart_paths, user_message="x")


def test_batch_describe_raises_on_zero_images():
    """空列表抛 ValueError。"""
    from BreakoutStrategy.feature_library.glm4v_backend import GLM4VBackend

    backend = GLM4VBackend(api_key="test-key")
    with pytest.raises(ValueError, match="at least 1 image"):
        backend.batch_describe(chart_paths=[], user_message="x")


def test_batch_describe_uses_system_prompt_from_param(tmp_path):
    """batch_describe 接受可选 system_prompt 参数（Inducer 注入自己的 prompt）。"""
    from unittest.mock import MagicMock, patch
    from BreakoutStrategy.feature_library.glm4v_backend import GLM4VBackend

    p = tmp_path / "c.png"
    p.write_bytes(b"fake")
    backend = GLM4VBackend(api_key="test-key")
    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=MagicMock(content="ok", reasoning_content=None))]
    with patch.object(backend._client.chat.completions, "create",
                      return_value=fake_resp) as mock_create:
        backend.batch_describe(
            chart_paths=[p], user_message="x",
            system_prompt="custom inducer prompt",
        )
    messages = mock_create.call_args.kwargs["messages"]
    assert messages[0]["content"] == "custom inducer prompt"


def test_batch_describe_default_uses_glm4v_system_prompt(tmp_path):
    """不传 system_prompt 时使用现有 GLM4V SYSTEM_PROMPT 作为兜底。"""
    from unittest.mock import MagicMock, patch
    from BreakoutStrategy.feature_library.glm4v_backend import GLM4VBackend
    from BreakoutStrategy.feature_library.prompts import SYSTEM_PROMPT

    p = tmp_path / "c.png"
    p.write_bytes(b"fake")
    backend = GLM4VBackend(api_key="test-key")
    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=MagicMock(content="ok", reasoning_content=None))]
    with patch.object(backend._client.chat.completions, "create",
                      return_value=fake_resp) as mock_create:
        backend.batch_describe(chart_paths=[p], user_message="x")
    messages = mock_create.call_args.kwargs["messages"]
    assert messages[0]["content"] == SYSTEM_PROMPT
