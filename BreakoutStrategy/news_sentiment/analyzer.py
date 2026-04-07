"""
情感分析编排器

两阶段分析:
  Stage 1: 委托给可插拔的 backend (GLM / DeepSeek / FinBERT+RoBERTa) 完成逐条分析
  Stage 2: 确定性公式聚合，返回 SummaryResult
"""

import logging
import math

from datetime import date
from BreakoutStrategy.news_sentiment.cache import SentimentCache, news_fingerprint
from BreakoutStrategy.news_sentiment.config import AnalyzerConfig, TimeDecayConfig
from BreakoutStrategy.news_sentiment.models import (
    AnalyzedItem,
    NewsItem,
    SentimentResult,
    SummaryResult,
)

logger = logging.getLogger(__name__)


# ── certainty × sufficiency 聚合参数 ──
# 设计原则：每个参数控制一个独立语义维度，无跨层级级联
# 详见 docs/research/rho-confidence-sentiment-score.md

# 方向判定层（rho）
_W0_RHO = 0.1         # neutral 在 rho 分母中的权重
_DELTA = 0.07         # 标签阈值（|rho| < DELTA → neutral 标签，仅用于显示，不影响 score）
_EMPH = 2.1           # impact emphasis 指数（极端事件非线性权重，用于 rho 方向判定）
_LA = 1.26            # 损失厌恶系数（rho 中负面加权，仅影响方向判定）

# 证据强度层（evidence + sufficiency）
_K = 0.60             # evidence 饱和速度（已适配归一化 evidence [0,1]）
_SCARCITY_N = 1.5     # 方向性新闻最少条数阈值（稀缺性保护）
_BLEND_N = 4.0        # evidence 混合过渡点（n_dir > BLEND_N 时引入 impact-weighted mean）

# 信心层（certainty × sufficiency × opp_penalty）
_K_TANH = 2.0         # tanh certainty 斜率（替代硬截断 min(|rho|×1.54, 1.0)）
_GAMMA = 0.70         # positive 被 negative 反对的惩罚系数（基于 raw weights）
_OPP_NEG = 0.35       # negative 被 positive 反对的惩罚系数（基于 raw weights）
_NEG_AMP = 1.40       # 负面 confidence 统一放大（合并旧 BETA 不对称 + LA_NEG）


def _impact_emphasis(iv: float) -> float:
    """
    超线性 impact 强调函数（用于 rho 方向判定）

    金融直觉：极端事件（FDA 批准、破产）的市场冲击是非线性的。
    单条 extreme 新闻的影响力远超多条 low 新闻的线性叠加，
    这与量化金融中的跳跃扩散模型和厚尾分布一致。

    iv ≤ 0.5 (medium 及以下): 原样返回
    iv > 0.5 (high/extreme): 指数增强 iv × exp(EMPH × (iv - 0.5))
    """
    return iv * math.exp(_EMPH * max(0.0, iv - 0.5))


def _get_backend_registry():
    """延迟导入 backend，避免未安装 transformers/torch 时失败"""
    from .backends.glm_backend import GLMBackend
    from .backends.deepseek_backend import DeepSeekBackend
    registry = {"glm": GLMBackend, "deepseek": DeepSeekBackend}
    try:
        from .backends.finbert_roberta_backend import FinBERTRoBERTaBackend
        registry["finbert_roberta"] = FinBERTRoBERTaBackend
    except ImportError:
        pass
    return registry


def _compute_time_weights(
    items: list[NewsItem], reference_date: str, half_life: float,
) -> list[float]:
    """计算每条新闻的时间衰减权重"""
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


class SentimentAnalyzer:
    """可插拔后端的两阶段情感分析编排器"""

    def __init__(self, config: AnalyzerConfig, cache: SentimentCache | None = None):
        self._config = config
        self._cache = cache
        registry = _get_backend_registry()
        backend_cls = registry.get(config.backend)
        if backend_cls is None:
            raise ValueError(
                f"Unknown backend: {config.backend}. "
                f"Available: {list(registry.keys())}"
            )
        self._backend = backend_cls(config)

    def analyze(self, items: list[NewsItem], ticker: str,
                date_from: str, date_to: str,
                time_decay: TimeDecayConfig | None = None,
    ) -> tuple[list[AnalyzedItem], SummaryResult]:
        """
        执行两阶段情感分析

        Returns:
            (逐条分析结果, 综合汇总)
        """
        if not items:
            return [], SummaryResult(
                sentiment="neutral", confidence=0.0,
                reasoning="No news found in the specified period.",
                positive_count=0, negative_count=0, neutral_count=0,
                total_count=0, fail_count=0,
            )

        # Stage 1: 缓存查找 + backend 分析
        if self._cache:
            backend_name = self._config.backend
            model_name = self._config.model
            cached_results: dict[int, SentimentResult] = {}
            uncached_indices: list[int] = []
            uncached_items: list[NewsItem] = []

            for i, item in enumerate(items):
                fp = news_fingerprint(item)
                cached = self._cache.get_sentiment(fp, backend_name, model_name)
                if cached is not None:
                    cached_results[i] = cached
                else:
                    uncached_indices.append(i)
                    uncached_items.append(item)

            logger.info(
                f"[Cache] {len(cached_results)} hits, {len(uncached_items)} misses"
            )

            if uncached_items:
                new_sentiments = self._backend.analyze_all(uncached_items, ticker)
                for idx, sent in zip(uncached_indices, new_sentiments):
                    if sent.impact_value > 0:
                        fp = news_fingerprint(items[idx])
                        self._cache.put_sentiment(fp, backend_name, model_name, sent)
                    cached_results[idx] = sent

            sentiments = [cached_results[i] for i in range(len(items))]
        else:
            sentiments = self._backend.analyze_all(items, ticker)

        analyzed_items = [
            AnalyzedItem(news=item, sentiment=sent)
            for item, sent in zip(items, sentiments)
        ]

        # Stage 2: aggregation (unchanged)
        summary = self._summarize(analyzed_items, ticker, date_from, date_to, time_decay=time_decay)
        return analyzed_items, summary

    def _summarize(self, analyzed_items: list[AnalyzedItem],
                   ticker: str, date_from: str, date_to: str,
                   time_decay: TimeDecayConfig | None = None,
    ) -> SummaryResult:
        """
        Stage 2: certainty × sufficiency 连续映射聚合

        参数解耦设计：
        - 方向判定层：LA 仅影响 rho，不影响 confidence 幅度
        - 信心层：tanh(K_TANH × |rho|) 对称用于正负分支，NEG_AMP 统一放大负面
        - 证据层：SCARCITY_N（稀缺性）与 BLEND_N（混合过渡）独立
        - opp_penalty 使用 raw weights（与 rho 的 emphasized weights 解耦，消除 double-counting）

        算法：
        0. 有效/无效分离 + 分组统计
           - raw weights: 用于 evidence/sufficiency/opp_penalty
           - emphasized weights: 仅用于 rho 方向判定
        1. 极性分数 rho = (W_p_emph - W_n_emph×LA) / (...)
        2. sentiment 标签判定（|rho| < DELTA → neutral，仅用于显示）
        3. confidence（统一路径，纯 neutral 特判）:
           - n_dir > 0: tanh(K_TANH×|rho|) × sufficiency × (1 - opp_penalty)
           - n_dir == 0: 0（无方向性新闻）
           - 负面分支额外 × NEG_AMP
        4. clamp confidence ∈ [0, 1]
        5. sentiment_score = sign(rho) × confidence（连续映射，无死区截断）
           选股阈值：>+0.30 正面 | [-0.15, +0.30] 中性 | <-0.15 负面 | <-0.40 强否决
        """
        n_total = len(analyzed_items)

        # Step 0: 有效/无效分离 + 分组统计（可选时间加权）
        # 保存 raw 和 emphasized 两套 impact values：
        #   - raw: 用于 evidence/sufficiency/opp_penalty
        #   - emphasized: 仅用于 rho 方向判定（极端事件权重更高）
        pos_impacts: list[float] = []
        neg_impacts: list[float] = []
        pos_impacts_emph: list[float] = []
        neg_impacts_emph: list[float] = []
        pos_tw: list[float] = []
        neg_tw: list[float] = []
        neu_tw_sum = 0.0
        neu_valid = 0
        fail_count = 0

        # 预计算时间权重
        if time_decay and time_decay.enable:
            item_tw = _compute_time_weights(
                [a.news for a in analyzed_items], date_to, time_decay.half_life,
            )
        else:
            item_tw = [1.0] * len(analyzed_items)

        for i, item in enumerate(analyzed_items):
            s = item.sentiment.sentiment
            iv = item.sentiment.impact_value
            tw = item_tw[i]
            if iv == 0.0:
                fail_count += 1
                continue
            iv_emph = _impact_emphasis(iv)
            if s == 'positive':
                pos_impacts.append(iv)
                pos_impacts_emph.append(iv_emph)
                pos_tw.append(tw)
            elif s == 'negative':
                neg_impacts.append(iv)
                neg_impacts_emph.append(iv_emph)
                neg_tw.append(tw)
            else:
                neu_valid += 1
                neu_tw_sum += tw

        n_p, n_n, n_u = len(pos_impacts), len(neg_impacts), neu_valid
        # raw weights（用于 evidence/opp_penalty）
        w_p = sum(c * t for c, t in zip(pos_impacts, pos_tw))
        w_n = sum(c * t for c, t in zip(neg_impacts, neg_tw))
        # emphasized weights（用于 rho 方向判定）
        w_p_emph = sum(c * t for c, t in zip(pos_impacts_emph, pos_tw))
        w_n_emph = sum(c * t for c, t in zip(neg_impacts_emph, neg_tw))

        # Step 1: 极性分数（使用 emphasized weights + 损失厌恶）
        # emphasis 让 extreme >> high >> medium 的非线性差距体现在方向判定中
        w_n_emph_adj = w_n_emph * _LA
        rho_denom = w_p_emph + w_n_emph_adj + neu_tw_sum * _W0_RHO
        rho = (w_p_emph - w_n_emph_adj) / rho_denom if rho_denom > 0 else 0.0

        # Step 2: 标签判定
        if rho > _DELTA:
            sentiment = 'positive'
        elif rho < -_DELTA:
            sentiment = 'negative'
        else:
            sentiment = 'neutral'

        # Step 3: confidence（certainty × sufficiency，统一路径）
        # evidence 混合：小样本用 mean，大样本引入 impact-weighted mean
        # BLEND_N 独立于 SCARCITY_N，分别控制混合过渡和稀缺性保护
        n_dir = n_p + n_n
        if n_dir == 0:
            # 纯 neutral：无方向性新闻，confidence = 0
            base_conf = 0.0
        else:
            tw_sum_dir = sum(pos_tw) + sum(neg_tw)
            evidence_mean = (w_p + w_n) / tw_sum_dir if tw_sum_dir > 0 else 0.0
            alpha = min(1.0, _BLEND_N / n_dir)
            if alpha < 1.0 and (w_p + w_n) > 0:
                sum_sq = (
                    sum(c * c * t for c, t in zip(pos_impacts, pos_tw))
                    + sum(c * c * t for c, t in zip(neg_impacts, neg_tw))
                )
                evidence_iw = sum_sq / (w_p + w_n)
                evidence = alpha * evidence_mean + (1.0 - alpha) * evidence_iw
            else:
                evidence = evidence_mean
            scarcity = min(1.0, n_dir / _SCARCITY_N)

            # certainty: tanh 平滑映射（替代 min 硬截断，消除 cap 信息丢失）
            certainty = math.tanh(_K_TANH * abs(rho))
            sufficiency = (1.0 - math.exp(-evidence / _K)) * scarcity
            # opp_penalty: 使用 raw weights（与 rho 的 emphasized weights 解耦，消除 double-counting）
            w_total_raw = w_p + w_n
            if rho >= 0:
                opp_penalty = _GAMMA * (w_n / w_total_raw) if w_n > 0 else 0.0
                base_conf = certainty * sufficiency * (1.0 - opp_penalty)
            else:
                opp_penalty = _OPP_NEG * (w_p / w_total_raw) if w_p > 0 else 0.0
                base_conf = certainty * sufficiency * (1.0 - opp_penalty)
                base_conf *= _NEG_AMP  # 损失厌恶：统一放大负面 confidence

        # Step 4: clamp confidence（失败项在 Step 0 已过滤，对公式透明）
        n = n_p + n_n + n_u  # 有效项数
        confidence = round(max(0.0, min(1.0, base_conf)), 4)

        # Step 5: sentiment_score + reasoning
        # score 基于 rho 符号（连续映射，不依赖死区分支）
        if n_dir == 0:
            s_score = 0.0
        else:
            s_sign = 1 if rho >= 0 else -1
            s_score = round(s_sign * confidence, 4)

        reasoning = self._generate_reasoning(
            ticker, date_from, date_to,
            n_total, n_p, n_n, n_u, w_p, w_n, rho, sentiment,
            confidence, s_score, fail_count, analyzed_items,
        )

        logger.info(
            f"[Summarize] sentiment_score={s_score:+.4f} "
            f"(rho={rho:+.3f}, conf={confidence:.4f}, "
            f"n={n_total}, p/n/u={n_p}/{n_n}/{n_u})"
        )

        return SummaryResult(
            sentiment=sentiment,
            confidence=confidence,
            reasoning=reasoning,
            positive_count=n_p,
            negative_count=n_n,
            neutral_count=n_u,
            total_count=n_total,
            fail_count=fail_count,
            rho=round(rho, 4),
            sentiment_score=s_score,
        )

    @staticmethod
    def _generate_reasoning(
        ticker: str, date_from: str, date_to: str,
        n: int, n_p: int, n_n: int, n_u: int,
        w_p: float, w_n: float, rho: float, sentiment: str,
        confidence: float, sentiment_score: float,
        fail_count: int, analyzed_items: list[AnalyzedItem],
    ) -> str:
        """基于计算结果的模板化 reasoning 生成"""
        parts = []

        parts.append(
            f"{date_from}~{date_to} period, {n} news analyzed for {ticker}: "
            f"{n_p} positive (strength {w_p:.1f}), "
            f"{n_n} negative (strength {w_n:.1f}), "
            f"{n_u} neutral."
        )

        if n_p == 0 and n_n == 0:
            parts.append(
                f"Sentiment score {sentiment_score:+.4f} (neutral). "
                f"No directional news detected."
            )
        else:
            parts.append(
                f"Sentiment score {sentiment_score:+.4f} ({sentiment}). "
                f"Polarity {rho:+.2f}, confidence {confidence:.4f}."
            )

        if fail_count > 0:
            parts.append(
                f"Note: {fail_count}/{n} items failed analysis "
                f"(excluded from aggregation)."
            )

        valid_items = [a for a in analyzed_items if a.sentiment.impact_value > 0]
        if valid_items:
            top = sorted(valid_items, key=lambda a: a.sentiment.impact_value, reverse=True)[:3]
            headlines = "; ".join(
                f"[{a.sentiment.sentiment}|{a.sentiment.impact}] {a.news.title[:60]}"
                for a in top
            )
            parts.append(f"Key signals: {headlines}.")

        return " ".join(parts)
