"""
FinBERT + RoBERTa 软投票集成

- ProsusAI/finbert: 标签 positive/negative/neutral
- mrm8488/distilroberta-finetuned-financial-news-sentiment-analysis: 标签 LABEL_0/1/2
- 使用 top_k=None 获取完整概率分布
- 软投票：取两模型平均概率，选最高类
"""

import logging

import torch
from transformers import pipeline

from .base import BaseSentimentModel, ItemResult

logger = logging.getLogger(__name__)

# RoBERTa 模型使用 LABEL_0/1/2，需要映射
ROBERTA_LABEL_MAP = {
    "LABEL_0": "negative",
    "LABEL_1": "neutral",
    "LABEL_2": "positive",
}

FINBERT_MODEL = "ProsusAI/finbert"
ROBERTA_MODEL = "mrm8488/distilroberta-finetuned-financial-news-sentiment-analysis"


def _select_device() -> int:
    """选择设备：GPU 可用返回 0，否则返回 -1 (CPU)"""
    if torch.cuda.is_available():
        logger.info(f"Using GPU: {torch.cuda.get_device_name(0)}")
        return 0
    logger.info("GPU not available, using CPU")
    return -1


def _normalize_scores(raw_scores: list[dict], label_map: dict[str, str] | None = None) -> dict[str, float]:
    """将 pipeline 输出转为 {positive: p, negative: p, neutral: p} 格式"""
    result = {"positive": 0.0, "negative": 0.0, "neutral": 0.0}
    for item in raw_scores:
        label = item["label"]
        if label_map and label in label_map:
            label = label_map[label]
        label = label.lower()
        if label in result:
            result[label] = item["score"]
    return result


def _soft_vote(finbert_scores: dict[str, float], roberta_scores: dict[str, float]) -> tuple[str, float]:
    """软投票：取两模型平均概率分布，返回 (sentiment, confidence)"""
    avg = {}
    for label in ("positive", "negative", "neutral"):
        avg[label] = (finbert_scores.get(label, 0.0) + roberta_scores.get(label, 0.0)) / 2
    sentiment = max(avg, key=avg.get)
    confidence = avg[sentiment]
    return sentiment, confidence


class FinBERTRoBERTaModel(BaseSentimentModel):
    """FinBERT + RoBERTa 双模型集成"""
    name = "FinBERT+RoBERTa"

    def __init__(self):
        device = _select_device()
        logger.info("Loading FinBERT...")
        self._finbert = pipeline(
            "sentiment-analysis",
            model=FINBERT_MODEL,
            device=device,
            truncation=True,
            max_length=512,
            top_k=None,
        )
        logger.info("Loading RoBERTa...")
        self._roberta = pipeline(
            "sentiment-analysis",
            model=ROBERTA_MODEL,
            device=device,
            truncation=True,
            max_length=512,
            top_k=None,
        )
        logger.info("Models loaded.")

    def analyze_batch(self, texts: list[str], ticker: str) -> list[ItemResult]:
        # batch 推理，获取完整概率分布
        finbert_outputs = self._finbert(texts, batch_size=16)
        roberta_outputs = self._roberta(texts, batch_size=16)

        results = []
        for i, (fb_raw, rb_raw) in enumerate(zip(finbert_outputs, roberta_outputs)):
            try:
                fb_scores = _normalize_scores(fb_raw)
                rb_scores = _normalize_scores(rb_raw, label_map=ROBERTA_LABEL_MAP)
                sentiment, confidence = _soft_vote(fb_scores, rb_scores)
                results.append(ItemResult(
                    sentiment=sentiment,
                    confidence=round(confidence, 4),
                    reasoning=f"FinBERT={fb_scores}, RoBERTa={rb_scores}",
                    failed=False,
                ))
            except Exception as e:
                logger.error(f"[FinBERT+RoBERTa] Item {i} failed: {e}")
                results.append(ItemResult(
                    sentiment="neutral",
                    confidence=0.0,
                    reasoning=f"Error: {e}",
                    failed=True,
                ))

        return results
