"""
GLM-4.7-Flash 分析器后端

使用 zhipuai SDK，逐条独立并发推理。
含思考模式处理（content 为空时从 reasoning_content 提取）。
"""

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from zhipuai import ZhipuAI

from BreakoutStrategy.news_sentiment.config import AnalyzerConfig
from BreakoutStrategy.news_sentiment.models import NewsItem, SentimentResult

from .base import BaseAnalyzerBackend
from ._llm_utils import (
    SYSTEM_PROMPT, DEFAULT_SENTIMENT,
    build_user_message, parse_single_response,
)

logger = logging.getLogger(__name__)


class GLMBackend(BaseAnalyzerBackend):
    """GLM-4.7-Flash 情感分析后端"""

    def __init__(self, config: AnalyzerConfig):
        super().__init__(config)
        self._client = ZhipuAI(api_key=config.api_key)

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
                    logger.error(f"[GLM] Item {idx} failed: {e}")
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
                content = self._extract_content(response)
                return parse_single_response(content)
            except Exception as e:
                if attempt == 0:
                    logger.warning(f"[GLM] Call failed: {e}, retrying...")
                    continue
                logger.error(f"[GLM] Call failed after retry: {e}")
        return DEFAULT_SENTIMENT

    @staticmethod
    def _extract_content(response) -> str:
        """从 GLM 响应中提取文本，处理思考模式下 content 为空的情况"""
        msg = response.choices[0].message
        content = msg.content or ''
        if not content.strip():
            reasoning = getattr(msg, 'reasoning_content', '') or ''
            if reasoning:
                json_match = re.search(r'```json\s*([\s\S]*?)```', reasoning)
                if json_match:
                    return json_match.group(1)
                matches = re.findall(r'\{[^{}]*\}', reasoning)
                if matches:
                    return matches[-1]
        return content
