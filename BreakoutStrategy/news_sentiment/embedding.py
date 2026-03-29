"""
Embedding 管理

使用 fastembed (bge-small-en-v1.5) 进行文本向量化，
numpy 计算 cosine similarity。单例模式避免重复加载模型。
"""

import logging

import numpy as np
from fastembed import TextEmbedding

logger = logging.getLogger(__name__)

_model: TextEmbedding | None = None

MODEL_NAME = "BAAI/bge-small-en-v1.5"


def _get_model() -> TextEmbedding:
    """单例获取 embedding 模型，首次调用时加载"""
    global _model
    if _model is None:
        logger.info(f"[Embedding] Loading model: {MODEL_NAME}")
        _model = TextEmbedding(model_name=MODEL_NAME)
        logger.info("[Embedding] Model loaded")
    return _model


def embed_texts(texts: list[str]) -> np.ndarray:
    """
    批量 embedding 文本

    Args:
        texts: 文本列表

    Returns:
        np.ndarray, shape (len(texts), embedding_dim)
    """
    if not texts:
        return np.empty((0, 384))
    model = _get_model()
    embeddings = list(model.embed(texts))
    return np.array(embeddings)


def cosine_similarity_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """
    计算两组向量间的 cosine similarity 矩阵

    Args:
        a: shape (m, d)
        b: shape (n, d)

    Returns:
        shape (m, n) 的相似度矩阵
    """
    if a.size == 0 or b.size == 0:
        return np.empty((a.shape[0], b.shape[0]))

    # L2 归一化
    a_norm = a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-10)
    b_norm = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-10)

    return a_norm @ b_norm.T
