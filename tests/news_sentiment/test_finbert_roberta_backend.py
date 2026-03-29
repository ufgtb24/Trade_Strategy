"""测试 FinBERT+RoBERTa Backend（mock HuggingFace pipeline）"""

from unittest.mock import patch, MagicMock
from BreakoutStrategy.news_sentiment.backends.finbert_roberta_backend import (
    FinBERTRoBERTaBackend, _normalize_scores, _soft_vote, ROBERTA_LABEL_MAP,
)
from BreakoutStrategy.news_sentiment.config import AnalyzerConfig
from BreakoutStrategy.news_sentiment.models import NewsItem


def _make_config():
    return AnalyzerConfig(
        api_key="", backend="finbert_roberta", model="",
        temperature=0.0, max_concurrency=1, proxy="",
    )

def _make_item(title="Apple rises"):
    return NewsItem(
        title=title, summary="Good earnings", source="Yahoo",
        published_at="", url="", ticker="AAPL", category="news", collector="finnhub",
    )


def test_normalize_scores_finbert():
    raw = [{"label": "positive", "score": 0.8}, {"label": "negative", "score": 0.1}, {"label": "neutral", "score": 0.1}]
    scores = _normalize_scores(raw)
    assert scores == {"positive": 0.8, "negative": 0.1, "neutral": 0.1}


def test_normalize_scores_roberta_label_mapping():
    raw = [{"label": "LABEL_2", "score": 0.7}, {"label": "LABEL_0", "score": 0.2}, {"label": "LABEL_1", "score": 0.1}]
    scores = _normalize_scores(raw, label_map=ROBERTA_LABEL_MAP)
    assert scores == {"positive": 0.7, "negative": 0.2, "neutral": 0.1}


def test_soft_vote():
    fb = {"positive": 0.8, "negative": 0.1, "neutral": 0.1}
    rb = {"positive": 0.6, "negative": 0.3, "neutral": 0.1}
    sentiment, confidence = _soft_vote(fb, rb)
    assert sentiment == "positive"
    assert confidence == 0.7  # (0.8 + 0.6) / 2


def test_soft_vote_negative_wins():
    fb = {"positive": 0.1, "negative": 0.7, "neutral": 0.2}
    rb = {"positive": 0.2, "negative": 0.6, "neutral": 0.2}
    sentiment, confidence = _soft_vote(fb, rb)
    assert sentiment == "negative"
    assert confidence == 0.65


@patch("BreakoutStrategy.news_sentiment.backends.finbert_roberta_backend.pipeline")
@patch("BreakoutStrategy.news_sentiment.backends.finbert_roberta_backend.torch")
def test_analyze_all_with_mock_pipeline(mock_torch, mock_pipeline_fn):
    mock_torch.cuda.is_available.return_value = False

    finbert_pipe = MagicMock()
    roberta_pipe = MagicMock()
    mock_pipeline_fn.side_effect = [finbert_pipe, roberta_pipe]

    finbert_pipe.return_value = [
        [{"label": "positive", "score": 0.9}, {"label": "negative", "score": 0.05}, {"label": "neutral", "score": 0.05}]
    ]
    roberta_pipe.return_value = [
        [{"label": "LABEL_2", "score": 0.8}, {"label": "LABEL_0", "score": 0.1}, {"label": "LABEL_1", "score": 0.1}]
    ]

    backend = FinBERTRoBERTaBackend(_make_config())
    results = backend.analyze_all([_make_item()], "AAPL")
    assert len(results) == 1
    assert results[0].sentiment == "positive"
    assert results[0].impact == "high"
    assert results[0].impact_value == 0.80
