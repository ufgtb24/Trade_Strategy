"""
DeepSeek-V3 benchmark 包装器

使用 OpenAI 兼容 API，复用与 GLM 相同的 prompt。
"""

import json
import logging
import time
from pathlib import Path

import httpx
import yaml
from openai import OpenAI

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


def _load_config() -> tuple[str, str]:
    """返回 (api_key, proxy)"""
    api_key = ''
    if API_KEYS_PATH.exists():
        with open(API_KEYS_PATH, 'r', encoding='utf-8') as f:
            keys = yaml.safe_load(f) or {}
        api_key = keys.get('deepseek', '')

    proxy = ''
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f) or {}
        proxy = cfg.get('proxy', '')

    return api_key, proxy


class DeepSeekModel(BaseSentimentModel):
    """DeepSeek-V3 情感分析"""
    name = "DeepSeek-V3"

    def __init__(self):
        api_key, proxy = _load_config()
        http_client = httpx.Client(proxy=proxy) if proxy else None
        self._client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com",
            http_client=http_client,
        )

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
                    model="deepseek-chat",
                    messages=[
                        {"role": "system", "content": BATCH_SYSTEM_PROMPT},
                        {"role": "user", "content": user_message},
                    ],
                    temperature=0.1,
                    max_tokens=4096,
                    response_format={"type": "json_object"},
                )
                content = response.choices[0].message.content or ''
                return self._parse_response(content, len(texts), fallback=(attempt == 1))

            except json.JSONDecodeError:
                if attempt == 0:
                    logger.warning("[DeepSeek] JSON parse failed, retrying...")
                    time.sleep(1.0)
                    continue
                logger.error("[DeepSeek] JSON parse failed after retry")
            except Exception as e:
                if attempt == 0:
                    logger.warning(f"[DeepSeek] Call failed: {e}, retrying...")
                    time.sleep(1.0)
                    continue
                logger.error(f"[DeepSeek] Call failed after retry: {e}")

        return [FAILED_RESULT] * len(texts)

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
            # 兜底：提取 JSON 对象
            results_raw = self._extract_json_objects(text)
            if not results_raw:
                return [FAILED_RESULT] * expected_count

        # 处理 DeepSeek 可能返回 {"results": [...]} 而非裸数组
        if isinstance(results_raw, dict):
            for key in ('results', 'data', 'items', 'analysis'):
                if key in results_raw and isinstance(results_raw[key], list):
                    results_raw = results_raw[key]
                    break
            else:
                results_raw = [results_raw]

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
