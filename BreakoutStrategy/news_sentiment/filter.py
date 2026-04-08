"""
新闻预过滤管道（语义版）

四层过滤: 语义模板过滤 → 相关性过滤 → 语义去重 → 多样性采样截断。
使用 fastembed (bge-small-en-v1.5) embedding + numpy cosine similarity。
"""

import logging
from collections import Counter
from datetime import date

import numpy as np

from BreakoutStrategy.news_sentiment.config import FilterConfig
from BreakoutStrategy.news_sentiment.embedding import cosine_similarity_matrix, embed_texts
from BreakoutStrategy.news_sentiment.models import NewsItem

logger = logging.getLogger(__name__)

# 低价值新闻语义模板（与这些模板相似度高的新闻会被过滤）
LOW_VALUE_TEMPLATES = [
    "top stocks to buy for long term investment",
    "best growth stocks to buy and hold forever",
    "you won't believe how much money this stock made",
    "should you buy this stock right now before it's too late",
    "this dividend stock pays monthly income to investors",
    "stock price prediction and forecast for next year",
    "technical analysis chart pattern shows bullish signal",
    "options trading alert unusual activity detected",
    "penny stock could be the next big winner",
    "millionaire maker one stock that could change your life",
]

# 模板 embedding 缓存（模块级，只计算一次）
_template_embeddings: np.ndarray | None = None


def _get_template_embeddings() -> np.ndarray:
    """获取低价值模板的 embedding（懒加载，缓存）"""
    global _template_embeddings
    if _template_embeddings is None:
        _template_embeddings = embed_texts(LOW_VALUE_TEMPLATES)
    return _template_embeddings


def filter_news(
    items: list[NewsItem], config: FilterConfig,
    ticker: str = "", company_name: str = "",
    reference_date: str = "",
) -> list[NewsItem]:
    """
    四层预过滤管道（语义版）

    ①语义模板过滤 → ②相关性过滤 → ③语义去重 → ④多样性采样截断
    """
    if not items:
        return items

    # 一次性 embedding 所有标题
    titles = [item.title for item in items]
    embeddings = embed_texts(titles)
    logger.info(f"[Filter] Embedded {len(titles)} titles")

    # Stage 1: 语义模板过滤（去垃圾）
    filtered, filtered_embeddings = semantic_filter(
        items, embeddings, config.semantic_filter_threshold,
    )
    logger.info(f"[Filter] Semantic filter: {len(items)} -> {len(filtered)}")

    # Stage 2: 相关性过滤（去无关，O(n) 先缩小 n）
    if ticker:
        relevant, relevant_embeddings = relevance_filter(
            filtered, filtered_embeddings, ticker, config.relevance_threshold,
            company_name=company_name,
        )
        logger.info(f"[Filter] Relevance filter: {len(filtered)} -> {len(relevant)}")
    else:
        relevant, relevant_embeddings = filtered, filtered_embeddings

    # Stage 3: 语义去重（O(n²)，在缩小后的集合上执行）
    deduped, deduped_embeddings = semantic_dedup(
        relevant, relevant_embeddings, config.semantic_dedup_threshold,
    )
    logger.info(f"[Filter] Semantic dedup: {len(relevant)} -> {len(deduped)}")

    # Stage 4: 多样性采样（可选时间加权）
    if config.time_decay.enable and config.time_decay.sample_prefer_recent and reference_date:
        time_weights = _compute_time_weights(deduped, reference_date, config.time_decay.half_life)
        sampled = diversity_sample(
            deduped, deduped_embeddings, config.max_items,
            time_weights=time_weights, alpha=config.time_decay.sample_alpha,
        )
    else:
        sampled = diversity_sample(deduped, deduped_embeddings, config.max_items)
    logger.info(f"[Filter] Diversity sample: {len(deduped)} -> {len(sampled)}")

    return sampled


def semantic_filter(
    items: list[NewsItem],
    embeddings: np.ndarray,
    threshold: float = 0.5,
) -> tuple[list[NewsItem], np.ndarray]:
    """
    语义模板过滤

    每条新闻与低价值模板比较 cosine similarity，
    最大相似度 > threshold 则过滤。

    Returns:
        (过滤后的 items, 对应的 embeddings)
    """
    template_emb = _get_template_embeddings()
    sim_matrix = cosine_similarity_matrix(embeddings, template_emb)  # (n, templates)
    max_sim = sim_matrix.max(axis=1)  # (n,)

    keep_mask = max_sim < threshold
    kept_items = [item for item, keep in zip(items, keep_mask) if keep]
    kept_embeddings = embeddings[keep_mask]

    return kept_items, kept_embeddings


def _days_between(item_a: NewsItem, item_b: NewsItem) -> int:
    """计算两条新闻的发布日期差（天数）"""
    date_a = item_a.published_at[:10] if item_a.published_at else ''
    date_b = item_b.published_at[:10] if item_b.published_at else ''
    if not date_a or not date_b:
        return 0
    try:
        da = date.fromisoformat(date_a)
        db = date.fromisoformat(date_b)
        return abs((da - db).days)
    except ValueError:
        return 0


def _compute_time_weights(
    items: list[NewsItem], reference_date: str, half_life: float,
) -> list[float]:
    """
    计算每条新闻的时间衰减权重 w(t) = exp(-ln2/half_life * t)

    Args:
        items: 新闻列表
        reference_date: 参考日期 YYYY-MM-DD（通常为 date_to）
        half_life: 半衰期（天数）

    Returns:
        与 items 等长的权重列表，范围 (0, 1]
    """
    import math
    decay_lambda = math.log(2) / half_life
    ref = date.fromisoformat(reference_date)
    weights = []
    for item in items:
        date_str = item.published_at[:10] if item.published_at else ''
        if not date_str:
            weights.append(1.0)
            continue
        try:
            d = date.fromisoformat(date_str)
            days = max(0, (ref - d).days)
            weights.append(math.exp(-decay_lambda * days))
        except ValueError:
            weights.append(1.0)
    return weights


def semantic_dedup(
    items: list[NewsItem],
    embeddings: np.ndarray,
    threshold: float = 0.75,
    max_day_gap: int = 3,
) -> tuple[list[NewsItem], np.ndarray]:
    """
    全局语义去重

    计算全局 cosine similarity 矩阵，相似度 > 阈值且发布日期在 max_day_gap 天内的
    视为同一事件，保留 summary 更长的条目。

    Returns:
        (去重后的 items, 对应的 embeddings)
    """
    if len(items) <= 1:
        return items, embeddings

    # 预排序：summary 长度降序，等长时 published_at 降序，title 兜底（确保贪心去重确定性）
    order = sorted(range(len(items)),
                   key=lambda i: (len(items[i].summary), items[i].published_at or '', items[i].title),
                   reverse=True)
    items = [items[i] for i in order]
    embeddings = embeddings[order]

    # 全局 cosine similarity 矩阵
    sim = cosine_similarity_matrix(embeddings, embeddings)

    # 贪心去重
    kept: list[int] = []
    for i in range(len(items)):
        is_dup = False
        for j in kept:
            if sim[i, j] >= threshold and _days_between(items[i], items[j]) <= max_day_gap:
                # 保留 summary 更长的
                if len(items[i].summary) > len(items[j].summary):
                    kept.remove(j)
                    kept.append(i)
                is_dup = True
                break
        if not is_dup:
            kept.append(i)

    kept.sort()
    return [items[i] for i in kept], embeddings[kept]


# _infer_company_name 使用的停用词（标题中常见的非公司名专有名词）
_TITLE_STOP_WORDS = frozenset({
    'The', 'In', 'On', 'At', 'For', 'To', 'Of', 'A', 'An', 'And',
    'Is', 'Are', 'Was', 'Were', 'Has', 'Have', 'Had', 'Will', 'Its',
    'New', 'After', 'Over', 'With', 'From', 'By', 'Up', 'Down', 'Out',
    'About', 'How', 'Why', 'What', 'This', 'That', 'Says', 'Report',
    'Reports', 'Q1', 'Q2', 'Q3', 'Q4', 'CEO', 'Inc', 'Corp', 'Ltd',
    'Stock', 'Shares', 'Market', 'Price', 'Buy', 'Sell',
})


def _infer_company_name(items: list[NewsItem], ticker: str) -> str:
    """
    从新闻标题中推断公司名

    API 返回的新闻大部分与目标股票相关，公司名应是最频繁的专有名词。
    找不到时回退到 ticker 本身。
    """
    word_counts: Counter[str] = Counter()
    for item in items:
        for w in item.title.split():
            if len(w) > 1 and w[0].isupper() and w not in _TITLE_STOP_WORDS:
                word_counts[w] += 1
    # 排除 ticker 本身，避免 "AAPL AAPL" 这种冗余
    word_counts.pop(ticker, None)
    if not word_counts:
        return ticker
    # 按频次降序，同频次按字母升序（确保确定性，Counter.most_common 对同频次按插入序不确定）
    top = sorted(word_counts.items(), key=lambda x: (-x[1], x[0]))
    return top[0][0]


def relevance_filter(
    items: list[NewsItem],
    embeddings: np.ndarray,
    ticker: str,
    threshold: float = 0.55,
    company_name: str = "",
) -> tuple[list[NewsItem], np.ndarray]:
    """
    相关性过滤

    用 "{company_name} {ticker}" 作为参考向量，
    计算每条新闻的 cosine similarity，低于阈值则视为与目标股票无关。
    company_name 未提供时回退到标题频率推断。
    """
    if not company_name:
        company_name = _infer_company_name(items, ticker)
    ref_text = f"{company_name} {ticker}"
    logger.info(f"[Filter] Relevance ref: '{ref_text}'")

    ref_embedding = embed_texts([ref_text])
    sim = cosine_similarity_matrix(embeddings, ref_embedding).ravel()  # (n,)

    keep_mask = sim >= threshold
    kept_items = [item for item, keep in zip(items, keep_mask) if keep]
    kept_embeddings = embeddings[keep_mask]

    return kept_items, kept_embeddings


def diversity_sample(
    items: list[NewsItem], embeddings: np.ndarray, max_items: int,
    time_weights: list[float] | None = None,
    alpha: float = 0.25,
) -> list[NewsItem]:
    """
    Greedy Diversity Sampling（FPS cosine 版，可选时间加权）

    当提供 time_weights 时，调整评分: adjusted = max_sim - alpha * tw
    近期新闻（tw≈1）获得时间加分，在多样性相近时优先入选。
    alpha=0 或 time_weights=None 退化为原始 FPS。
    """
    if len(items) <= max_items:
        return items

    sim = cosine_similarity_matrix(embeddings, embeddings)

    norms = np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-10
    emb_norm = embeddings / norms

    # 种子选择
    if time_weights is not None:
        tw = np.array(time_weights)
        weighted_centroid = (emb_norm * tw[:, np.newaxis]).mean(axis=0)
        weighted_centroid = weighted_centroid / (np.linalg.norm(weighted_centroid) + 1e-10)
        seed = int(np.argmax(emb_norm @ weighted_centroid))
    else:
        centroid = emb_norm.mean(axis=0)
        seed = int(np.argmax(emb_norm @ centroid))

    selected = [seed]
    max_sim_arr = sim[:, seed].copy()

    for _ in range(max_items - 1):
        max_sim_arr[selected] = np.inf
        if time_weights is not None:
            adjusted = max_sim_arr - alpha * tw
            next_idx = int(np.argmin(adjusted))
        else:
            next_idx = int(np.argmin(max_sim_arr))
        selected.append(next_idx)
        max_sim_arr = np.maximum(max_sim_arr, sim[:, next_idx])

    selected.sort()
    return [items[i] for i in selected]
