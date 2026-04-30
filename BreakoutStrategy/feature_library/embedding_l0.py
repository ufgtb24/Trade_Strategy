"""L0 embedding 层 — 薄封装 news_sentiment 的 fastembed 接口。

为 feature_library 提供干净的单文本嵌入 + 两向量 cosine API，
避免 librarian 等模块直接依赖 news_sentiment 的批量 / 矩阵 API。
模型：bge-small-en-v1.5（384 维），由 news_sentiment.embedding 加载并缓存。
"""

import numpy as np

from BreakoutStrategy.news_sentiment.embedding import (
    embed_texts as _embed_texts,
    cosine_similarity_matrix as _cosine_similarity_matrix,
)


def embed_text(text: str) -> np.ndarray:
    """单条文本嵌入为 1D np.ndarray（384 维）。"""
    embeddings = _embed_texts([text])
    return embeddings[0]


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """两个 1D embedding 的余弦相似度，返回 Python float（便于 YAML 序列化）。"""
    a_2d = a.reshape(1, -1)
    b_2d = b.reshape(1, -1)
    sim_matrix = _cosine_similarity_matrix(a_2d, b_2d)
    return float(sim_matrix[0, 0])
