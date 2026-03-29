"""
DeepSeek-V3 分析器后端

使用 OpenAI 兼容 API，逐条独立并发推理。
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx
from openai import OpenAI

from BreakoutStrategy.news_sentiment.config import AnalyzerConfig
from BreakoutStrategy.news_sentiment.models import NewsItem, SentimentResult

from .base import BaseAnalyzerBackend
from ._llm_utils import (
    SYSTEM_PROMPT, DEFAULT_SENTIMENT,
    build_user_message, parse_single_response,
)

logger = logging.getLogger(__name__)


class DeepSeekBackend(BaseAnalyzerBackend):
    """DeepSeek-V3 情感分析后端"""

    def __init__(self, config: AnalyzerConfig):
        super().__init__(config)
        http_client = httpx.Client(proxy=config.proxy) if config.proxy else None
        self._client = OpenAI(
            api_key=config.api_key,
            base_url="https://api.deepseek.com",
            http_client=http_client,
        )

    def analyze_all(self, items: list[NewsItem], ticker: str) -> list[SentimentResult]:
        results = [DEFAULT_SENTIMENT] * len(items)
        with ThreadPoolExecutor(max_workers=self._config.max_concurrency) as pool:
            futures = {
                pool.submit(self._analyze_one, item, ticker): i
                for i, item in enumerate(items)
            }
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    logger.error(f"[DeepSeek] Item {idx} failed: {e}")
        return results

    def _analyze_one(self, item: NewsItem, ticker: str) -> SentimentResult:
        for attempt in range(2):
            try:
                response = self._client.chat.completions.create(
                    model=self._config.model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": build_user_message(item, ticker)},
                    ],
                    temperature=self._config.temperature,
                    response_format={"type": "json_object"},
                )
                content = response.choices[0].message.content or ''
                return parse_single_response(content)
            except Exception as e:
                if attempt == 0:
                    logger.warning(f"[DeepSeek] Call failed: {e}, retrying...")
                    continue
                logger.error(f"[DeepSeek] Call failed after retry: {e}")
        return DEFAULT_SENTIMENT
