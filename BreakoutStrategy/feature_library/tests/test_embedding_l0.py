"""Tests for L0 embedding wrapper."""
import numpy as np
import pytest

from BreakoutStrategy.feature_library.embedding_l0 import (
    embed_text, cosine_similarity,
)


def test_embed_returns_1d_array():
    emb = embed_text("盘整缩量后突破")
    assert isinstance(emb, np.ndarray)
    assert emb.ndim == 1


def test_embed_dimension_is_384():
    """bge-small-en-v1.5 输出 384 维（与 news_sentiment/embedding.py 一致）。"""
    emb = embed_text("test text")
    assert emb.shape == (384,)


def test_cosine_self_similarity_is_one():
    emb = embed_text("盘整缩量后突破")
    assert cosine_similarity(emb, emb) == pytest.approx(1.0, abs=1e-5)


def test_cosine_similar_texts_above_zero():
    a = embed_text("盘整缩量后突破")
    b = embed_text("盘整阶段量能收缩然后突破")
    sim = cosine_similarity(a, b)
    assert 0 < sim <= 1.0  # 中文同语义应正相似


def test_cosine_returns_python_float():
    """避免 numpy.float32 序列化进 yaml 时出问题。"""
    a = embed_text("test")
    b = embed_text("test")
    sim = cosine_similarity(a, b)
    assert isinstance(sim, float)
