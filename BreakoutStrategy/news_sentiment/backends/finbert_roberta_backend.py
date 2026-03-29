"""
FinBERT + RoBERTa 双模型软投票后端

- ProsusAI/finbert: 标签 positive/negative/neutral
- mrm8488/distilroberta-finetuned-financial-news-sentiment-analysis: 标签 LABEL_0/1/2
- top_k=None 获取完整概率分布，软投票取平均
"""

import logging

import torch
from transformers import pipeline

from BreakoutStrategy.news_sentiment.config import AnalyzerConfig
from BreakoutStrategy.news_sentiment.models import NewsItem, SentimentResult, IMPACT_MAP

from .base import BaseAnalyzerBackend

logger = logging.getLogger(__name__)

ROBERTA_LABEL_MAP = {
    "LABEL_0": "negative",
    "LABEL_1": "neutral",
    "LABEL_2": "positive",
}

FINBERT_MODEL = "ProsusAI/finbert"
ROBERTA_MODEL = "mrm8488/distilroberta-finetuned-financial-news-sentiment-analysis"


def _normalize_scores(raw_scores: list[dict], label_map: dict[str, str] | None = None) -> dict[str, float]:
    """将 pipeline 输出转为 {positive: p, negative: p, neutral: p}"""
    result = {"positive": 0.0, "negative": 0.0, "neutral": 0.0}
    for item in raw_scores:
        label = item["label"]
        if label_map and label in label_map:
            label = label_map[label]
        label = label.lower()
        if label in result:
            result[label] = item["score"]
    return result


def _soft_vote(fb: dict[str, float], rb: dict[str, float]) -> tuple[str, float]:
    """软投票：取两模型平均概率分布，返回 (sentiment, confidence)"""
    avg = {label: (fb.get(label, 0.0) + rb.get(label, 0.0)) / 2 for label in ("positive", "negative", "neutral")}
    sentiment = max(avg, key=avg.get)
    return sentiment, round(avg[sentiment], 10)


def _prob_to_impact(prob: float) -> tuple[str, float]:
    """将 soft-vote 概率映射为 impact 等级"""
    if prob >= 0.85:
        return "high", IMPACT_MAP["high"]
    elif prob >= 0.65:
        return "medium", IMPACT_MAP["medium"]
    elif prob >= 0.45:
        return "low", IMPACT_MAP["low"]
    else:
        return "negligible", IMPACT_MAP["negligible"]


class FinBERTRoBERTaBackend(BaseAnalyzerBackend):
    """FinBERT + RoBERTa 双模型集成后端"""

    def __init__(self, config: AnalyzerConfig):
        super().__init__(config)
        device = 0 if torch.cuda.is_available() else -1
        logger.info(f"Loading FinBERT + RoBERTa (device={'GPU' if device == 0 else 'CPU'})...")
        self._finbert = pipeline(
            "sentiment-analysis", model=FINBERT_MODEL,
            device=device, truncation=True, max_length=512, top_k=None,
        )
        self._roberta = pipeline(
            "sentiment-analysis", model=ROBERTA_MODEL,
            device=device, truncation=True, max_length=512, top_k=None,
        )
        logger.info("Models loaded.")

    def analyze_all(self, items: list[NewsItem], ticker: str) -> list[SentimentResult]:
        texts = [f"{item.title}: {item.summary}" if item.summary else item.title for item in items]

        finbert_outputs = self._finbert(texts, batch_size=32)
        roberta_outputs = self._roberta(texts, batch_size=32)

        results = []
        for i, (fb_raw, rb_raw) in enumerate(zip(finbert_outputs, roberta_outputs)):
            try:
                fb_scores = _normalize_scores(fb_raw)
                rb_scores = _normalize_scores(rb_raw, label_map=ROBERTA_LABEL_MAP)
                sentiment, confidence = _soft_vote(fb_scores, rb_scores)
                impact_label, impact_val = _prob_to_impact(confidence)
                results.append(SentimentResult(
                    sentiment=sentiment,
                    impact=impact_label,
                    impact_value=impact_val,
                    reasoning=f"FinBERT={fb_scores}, RoBERTa={rb_scores}",
                ))
            except Exception as e:
                logger.error(f"[FinBERT+RoBERTa] Item {i} failed: {e}")
                results.append(SentimentResult(
                    sentiment="neutral", impact="", impact_value=0.0, reasoning=f"Error: {e}",
                ))
        return results
