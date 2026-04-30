"""GLM-4V-Flash 多模态后端 — 替代 spec 中的 Opus 多模态。

参考 BreakoutStrategy/news_sentiment/backends/glm_backend.py 的模式：
zhipuai SDK + 单次重试 + thinking 模式 reasoning_content 回收。
模型 ID 固定 glm-4v-flash（免费多模态）。

接口：describe_chart(chart_path, user_message) → str（纯文本描述）
"""

import base64
import logging
from pathlib import Path

from zhipuai import ZhipuAI

from BreakoutStrategy.feature_library.prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

GLM4V_MODEL_ID = "glm-4v-flash"
DEFAULT_TEMPERATURE = 0.3
MAX_RETRIES = 2
GLM4V_MAX_IMAGES = 5  # GLM-4V-Flash 服务端硬限（实验确认 n=8 报错 1210）


class GLM4VBackend:
    """GLM-4V-Flash 多模态调用封装。"""

    def __init__(self, api_key: str, temperature: float = DEFAULT_TEMPERATURE):
        if not api_key or not api_key.strip():
            raise ValueError("GLM4VBackend 需要非空 zhipuai api_key")
        self._client = ZhipuAI(api_key=api_key)
        self._temperature = temperature

    def describe_chart(self, chart_path: Path, user_message: str) -> str:
        """对单张 chart.png 调用 glm-4v-flash 生成自然语言描述。

        Args:
            chart_path: chart.png 的绝对路径
            user_message: 上下文 prompt（meta 字段 + 任务说明）

        Returns:
            模型生成的描述文本；失败时返回空字符串
        """
        image_data_url = _encode_image_as_data_url(chart_path)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": image_data_url}},
                {"type": "text", "text": user_message},
            ]},
        ]

        for attempt in range(MAX_RETRIES):
            try:
                response = self._client.chat.completions.create(
                    model=GLM4V_MODEL_ID,
                    messages=messages,
                    temperature=self._temperature,
                )
                return self._extract_content(response)
            except Exception as e:
                if attempt == 0:
                    logger.warning(f"[GLM4V] call failed: {e}, retrying...")
                    continue
                logger.error(f"[GLM4V] call failed after retry: {e}")

        return ""

    def batch_describe(
        self,
        chart_paths: list[Path],
        user_message: str,
        *,
        system_prompt: str | None = None,
    ) -> str:
        """对多张 chart.png 单次调用 glm-4v-flash 生成共性描述。

        Args:
            chart_paths: chart.png 路径列表（≤ GLM4V_MAX_IMAGES 张）
            user_message: 上下文 prompt（可含每张图的 sample_id / 元数据）
            system_prompt: 可选 system 角色 prompt（None 用 prompts.SYSTEM_PROMPT）

        Returns:
            模型回复文本；失败返回空字符串

        Raises:
            ValueError: chart_paths 为空 / 超过 GLM4V_MAX_IMAGES
        """
        if not chart_paths:
            raise ValueError("batch_describe needs at least 1 image")
        if len(chart_paths) > GLM4V_MAX_IMAGES:
            raise ValueError(
                f"too many images: {len(chart_paths)} > {GLM4V_MAX_IMAGES} "
                f"(GLM-4V-Flash 服务端硬限)"
            )

        sys_msg = system_prompt if system_prompt is not None else SYSTEM_PROMPT

        # user content：所有 image_url 在前，text 在后（图先于说明）
        user_content: list[dict] = [
            {"type": "image_url", "image_url": {"url": _encode_image_as_data_url(p)}}
            for p in chart_paths
        ]
        user_content.append({"type": "text", "text": user_message})

        messages = [
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": user_content},
        ]

        for attempt in range(MAX_RETRIES):
            try:
                response = self._client.chat.completions.create(
                    model=GLM4V_MODEL_ID,
                    messages=messages,
                    temperature=self._temperature,
                )
                return self._extract_content(response)
            except Exception as e:
                if attempt == 0:
                    logger.warning(f"[GLM4V batch] call failed: {e}, retrying...")
                    continue
                logger.error(f"[GLM4V batch] call failed after retry: {e}")

        return ""

    @staticmethod
    def _extract_content(response) -> str:
        msg = response.choices[0].message
        content = (msg.content or "").strip()
        if content:
            return content
        # thinking 模式回收
        reasoning = getattr(msg, "reasoning_content", "") or ""
        return reasoning.strip()


def _encode_image_as_data_url(chart_path: Path) -> str:
    """读取 PNG 文件，编码为 data: URL（zhipuai SDK 支持的图像传入格式）。"""
    raw = chart_path.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:image/png;base64,{b64}"
