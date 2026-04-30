"""Librarian — Beta-Binomial 累积 + L0 merge + features 库管理。

核心 API：
- upsert_candidate(candidate, batch_sample_ids, source)
- lookup_by_cosine(embedding, threshold)
- update(feature_id, event)
- recompute(feature_id)

Phase 1 简化：
- 不实施 epoch_tag / superseded_by 实际逻辑（schema 占位）
- LAMBDA_DECAY = 1.0（无时间衰减）
- GAMMA = 1.0 + C 始终 0（无 counter 加权）
- 不防 ObservationLog 重复 entry（暂允许，Phase 1.5 加去重）
"""

from datetime import datetime

import numpy as np
import scipy.stats

from BreakoutStrategy.feature_library.embedding_l0 import embed_text, cosine_similarity
from BreakoutStrategy.feature_library.feature_models import (
    Candidate, Event, Feature, ObservationLogEntry,
)
from BreakoutStrategy.feature_library.feature_store import FeatureStore
from BreakoutStrategy.feature_library.observation_log import new_entry_id

# Beta-Binomial 常量（主 spec §3 + Phase 1 简化）
ALPHA_PRIOR = 0.5
BETA_PRIOR = 0.5
LAMBDA_DECAY = 1.0    # Phase 1 无衰减
GAMMA = 1.0           # Phase 1 不参与（C 始终 0）

# L0 合并阈值（Phase 1 brainstorming 决策）
L0_MERGE_THRESHOLD = 0.85


class Librarian:
    """Beta-Binomial 累积器 + L0 merge + features 库管理。"""

    def __init__(self, store: FeatureStore, embedder=None):
        self.store = store
        self.embedder = embedder if embedder is not None else _DefaultEmbedder()

    def upsert_candidate(
        self,
        candidate: Candidate,
        *,
        batch_sample_ids: list[str],
        source: str = "ai_induction",
    ) -> Feature:
        """处理 Inducer 一条 candidate：合并到老 feature 或新建。

        步骤：
        1. embed candidate.text → embedding
        2. lookup_by_cosine 找命中的老 feature（取 cosine 最高）
        3a. 命中 → 用老 feature.id；3b. 未命中 → create_new_feature
        4. 对 batch_sample_ids 中每个 sample 写一条 ObservationLogEntry
           （在 supporting_sample_ids 内 K=1，否则 K=0；N 始终 1）
        5. recompute(feature_id) → 重算 (α, β) + signal
        """
        embedding = self.embedder.embed_text(candidate.text)
        matches = self.lookup_by_cosine(embedding, threshold=L0_MERGE_THRESHOLD)

        if matches:
            target_id = matches[0].id  # cosine 最高的
        else:
            target_id = self._create_new_feature(
                text=candidate.text,
                embedding=embedding,
                provenance=source,
            )

        supporting_set = set(candidate.supporting_sample_ids)
        for sid in batch_sample_ids:
            in_support = sid in supporting_set
            event = Event(
                sample_id=sid,
                K=1 if in_support else 0,
                N=1,
                source=source,
            )
            self.update(target_id, event)

        return self.recompute(target_id)

    def lookup_by_cosine(
        self, embedding: np.ndarray, threshold: float = L0_MERGE_THRESHOLD,
    ) -> list[Feature]:
        """返回 cosine ≥ threshold 的 features，按 cosine 降序。"""
        all_features = self.store.list_all()
        scored: list[tuple[float, Feature]] = []
        for f in all_features:
            f_emb = np.array(f.embedding)
            sim = self.embedder.cosine_similarity(embedding, f_emb)
            if sim >= threshold:
                scored.append((sim, f))
        scored.sort(key=lambda x: (-x[0], x[1].id))  # cosine 降序，并列 id 升序
        return [f for _, f in scored]

    def update(self, feature_id: str, event: Event) -> None:
        """单条 ObservationLog 事件入库（不立即 recompute）。

        signal_after / alpha_after / beta_after 在此处用临时计算值占位，
        recompute() 会从全部 active obs 重算并覆盖最后一条 obs 的快照。
        """
        feature = self.store.load(feature_id)
        # 计算事件后的临时 (α, β)（不含此事件后的衰减，供 obs 快照）
        tmp_alpha = feature.alpha + event.K
        tmp_beta = feature.beta + (event.N - event.K - event.C) + GAMMA * event.C
        tmp_signal = _safe_p5(tmp_alpha, tmp_beta)

        entry = ObservationLogEntry(
            id=new_entry_id(),
            ts=datetime.now(),
            source=event.source,
            sample_id=event.sample_id,
            K=event.K,
            N=event.N,
            C=event.C,
            alpha_after=tmp_alpha,
            beta_after=tmp_beta,
            signal_after=tmp_signal,
            epoch_tag=event.epoch_tag,
            notes=event.notes,
        )
        # 也更新 feature 的 observed_samples + total_K/N 即时（recompute 会覆盖 alpha/beta）
        if event.sample_id not in feature.observed_samples:
            feature.observed_samples.append(event.sample_id)
        feature.total_K += event.K
        feature.total_N += event.N
        feature.total_C_weighted += GAMMA * event.C
        feature.alpha = tmp_alpha
        feature.beta = tmp_beta
        feature.last_update_ts = datetime.now()
        feature.observations.append(entry)
        self.store.save(feature)

    def recompute(self, feature_id: str) -> Feature:
        """从 ObservationLog 重放计算 (α, β)，更新 features yaml + 派生 signal。"""
        feature = self.store.load(feature_id)
        active = [o for o in feature.observations if o.superseded_by is None]

        alpha = ALPHA_PRIOR + sum(o.K for o in active)
        beta = (
            BETA_PRIOR
            + sum(o.N - o.K - o.C for o in active)
            + GAMMA * sum(o.C for o in active)
        )

        feature.alpha = alpha
        feature.beta = beta
        # 与 alpha/beta 一起 reconcile（防 Phase 1.5 supersede 后 total_* 与
        # alpha/beta 发散；Phase 1 active = 全部 obs，行为不变）
        feature.total_K = sum(o.K for o in active)
        feature.total_N = sum(o.N for o in active)
        feature.total_C_weighted = GAMMA * sum(o.C for o in active)
        feature.last_update_ts = datetime.now()

        # 更新最后一条 obs 的快照（让人眼能看到当前 signal）
        if active:
            last_signal = _safe_p5(alpha, beta)
            active[-1].alpha_after = alpha
            active[-1].beta_after = beta
            active[-1].signal_after = last_signal

        self.store.save(feature)
        return feature

    def _create_new_feature(
        self, text: str, embedding: np.ndarray, provenance: str,
    ) -> str:
        new_id = self.store.next_id()
        feature = Feature(
            id=new_id,
            text=text,
            embedding=embedding.tolist(),
            alpha=ALPHA_PRIOR,
            beta=BETA_PRIOR,
            last_update_ts=datetime.now(),
            provenance=provenance,
            observed_samples=[],
            total_K=0,
            total_N=0,
            total_C_weighted=0.0,
            observations=[],
        )
        self.store.save(feature)
        return new_id


class _DefaultEmbedder:
    """默认 embedder = embedding_l0 模块函数（避免 Librarian 强依赖具体类）。"""

    def embed_text(self, text: str) -> np.ndarray:
        return embed_text(text)

    def cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        return cosine_similarity(a, b)


def _safe_p5(alpha: float, beta: float) -> float:
    """计算 P5 = beta.ppf(0.05, α, β)，加防御以避免 scipy 的边界 NaN。"""
    if alpha <= 0 or beta <= 0:
        return 0.0
    try:
        return float(scipy.stats.beta.ppf(0.05, alpha, beta))
    except (ValueError, FloatingPointError):
        return 0.0
