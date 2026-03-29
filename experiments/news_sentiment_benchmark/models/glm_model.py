"""
GLM-4.7-Flash benchmark 包装器

复用生产代码的 prompt 和 JSON 解析逻辑。
"""

import json
import logging
import time
from pathlib import Path

import yaml
from zhipuai import ZhipuAI

from .base import BaseSentimentModel, ItemResult

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
API_KEYS_PATH = PROJECT_ROOT / "configs" / "api_keys.yaml"
CONFIG_PATH = PROJECT_ROOT / "configs" / "news_sentiment.yaml"

BATCH_SYSTEM_PROMPT = (
    "你是一个金融新闻情感分析专家。分析以下每条新闻对该股票的影响。\n"
    '仅返回JSON数组：[{"index": 0, "sentiment": "positive|negative|neutral", '
    '"confidence": 0.0-1.0, "reasoning": "一句话理由"}, ...]'
)

FAILED_RESULT = ItemResult(sentiment="neutral", confidence=0.0, reasoning="Analysis failed", failed=True)


def _load_key() -> str:
    if API_KEYS_PATH.exists():
        with open(API_KEYS_PATH, 'r', encoding='utf-8') as f:
            keys = yaml.safe_load(f) or {}
        return keys.get('zhipuai', '')
    return ''


class GLMModel(BaseSentimentModel):
    """GLM-4.7-Flash 情感分析"""
    name = "GLM-4.7-Flash"

    def __init__(self):
        self._client = ZhipuAI(api_key=_load_key())

    def analyze_batch(self, texts: list[str], ticker: str) -> list[ItemResult]:
        lines = [f"股票: {ticker}"]
        for i, text in enumerate(texts):
            lines.append(f"{i}. {text}")
        base_message = "\n".join(lines)

        for attempt in range(2):
            try:
                user_message = base_message
                if attempt == 1:
                    user_message += "\n\n注意：请严格只返回JSON数组，不要包含任何解释性文字。"

                response = self._client.chat.completions.create(
                    model="glm-4.7-flash",
                    messages=[
                        {"role": "system", "content": BATCH_SYSTEM_PROMPT},
                        {"role": "user", "content": user_message},
                    ],
                    temperature=0.1,
                    max_tokens=4096,
                    response_format={"type": "json_object"},
                )
                content = self._extract_content(response)
                return self._parse_response(content, len(texts), fallback=(attempt == 1))

            except json.JSONDecodeError:
                if attempt == 0:
                    logger.warning("[GLM] JSON parse failed, retrying...")
                    time.sleep(1.0)
                    continue
                logger.error("[GLM] JSON parse failed after retry")
            except Exception as e:
                if attempt == 0:
                    logger.warning(f"[GLM] Call failed: {e}, retrying...")
                    time.sleep(1.0)
                    continue
                logger.error(f"[GLM] Call failed after retry: {e}")

        return [FAILED_RESULT] * len(texts)

    @staticmethod
    def _extract_content(response) -> str:
        """从 GLM 响应中提取文本，处理思考模式"""
        import re
        msg = response.choices[0].message
        content = msg.content or ''
        if not content.strip():
            reasoning = getattr(msg, 'reasoning_content', '') or ''
            if reasoning:
                json_match = re.search(r'```json\s*([\s\S]*?)```', reasoning)
                if json_match:
                    content = json_match.group(1)
                else:
                    matches = re.findall(r'\[[\s\S]*?\](?=\s*$|\s*\n)', reasoning)
                    if matches:
                        content = matches[-1]
                    else:
                        matches = re.findall(r'\{[\s\S]*?\}(?=\s*$|\s*\n)', reasoning)
                        if matches:
                            content = matches[-1]
        return content

    def _parse_response(self, content: str, expected_count: int,
                        fallback: bool = False) -> list[ItemResult]:
        text = content.strip()
        if text.startswith('```'):
            lines = text.split('\n')
            text = '\n'.join(lines[1:-1] if lines[-1].strip() == '```' else lines[1:])

        try:
            results_raw = json.loads(text)
        except json.JSONDecodeError:
            if not fallback:
                raise
            results_raw = self._extract_json_objects(text)
            if not results_raw:
                return [FAILED_RESULT] * expected_count

        results_map: dict[int, ItemResult] = {}
        for item in results_raw:
            if not isinstance(item, dict):
                continue
            idx = item.get('index', -1)
            results_map[idx] = ItemResult(
                sentiment=item.get('sentiment', 'neutral'),
                confidence=float(item.get('confidence', 0.0)),
                reasoning=item.get('reasoning', ''),
                failed=False,
            )

        return [results_map.get(i, FAILED_RESULT) for i in range(expected_count)]

    @staticmethod
    def _extract_json_objects(text: str) -> list[dict]:
        decoder = json.JSONDecoder()
        objects = []
        idx = 0
        while idx < len(text):
            while idx < len(text) and text[idx] not in ('{', '['):
                idx += 1
            if idx >= len(text):
                break
            try:
                obj, end_idx = decoder.raw_decode(text, idx)
                if isinstance(obj, dict):
                    objects.append(obj)
                elif isinstance(obj, list):
                    objects.extend(item for item in obj if isinstance(item, dict))
                idx = end_idx
            except json.JSONDecodeError:
                idx += 1
        return objects
