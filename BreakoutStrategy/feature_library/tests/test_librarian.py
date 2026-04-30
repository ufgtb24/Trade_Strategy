"""Tests for Librarian (Beta-Binomial 累积 + L0 merge)."""
from datetime import datetime
from unittest.mock import MagicMock

import numpy as np
import pytest

from BreakoutStrategy.feature_library.feature_models import (
    Candidate, Event, Feature, StatusBand,
)
from BreakoutStrategy.feature_library.feature_store import FeatureStore
from BreakoutStrategy.feature_library.librarian import (
    ALPHA_PRIOR, BETA_PRIOR, L0_MERGE_THRESHOLD, Librarian,
)


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    from BreakoutStrategy.feature_library import paths
    monkeypatch.setattr(paths, "FEATURE_LIBRARY_ROOT", tmp_path / "feature_library")
    monkeypatch.setattr(paths, "SAMPLES_DIR", paths.FEATURE_LIBRARY_ROOT / "samples")
    monkeypatch.setattr(paths, "FEATURES_DIR", paths.FEATURE_LIBRARY_ROOT / "features")
    return FeatureStore()


@pytest.fixture
def fake_embedder():
    """每条不同 text 返回不同 embedding；相同 text 返回完全相同 embedding。"""
    embedder = MagicMock()
    cache = {}
    def _embed(text):
        if text not in cache:
            cache[text] = np.random.RandomState(hash(text) % 2**31).rand(384)
            cache[text] = cache[text] / np.linalg.norm(cache[text])  # 单位向量
        return cache[text]
    embedder.embed_text.side_effect = _embed
    embedder.cosine_similarity.side_effect = lambda a, b: float(np.dot(a, b))
    return embedder


@pytest.fixture
def lib(isolated_store, fake_embedder):
    return Librarian(store=isolated_store, embedder=fake_embedder)


def test_upsert_creates_new_feature_when_no_match(lib, isolated_store):
    cand = Candidate(
        text="盘整缩量后突破",
        supporting_sample_ids=["S1", "S2"],
        K=2, N=3,
    )
    feature = lib.upsert_candidate(
        candidate=cand,
        batch_sample_ids=["S1", "S2", "S3"],
        source="ai_induction",
    )
    assert feature.id == "F-001"
    assert feature.text == "盘整缩量后突破"
    assert feature.alpha == pytest.approx(ALPHA_PRIOR + 2)  # K=2
    assert feature.beta == pytest.approx(BETA_PRIOR + 1)    # N-K=1
    assert set(feature.observed_samples) == {"S1", "S2", "S3"}
    # 3 个 obs entry（每个 sample 一条）
    loaded = isolated_store.load("F-001")
    assert len(loaded.observations) == 3


def test_upsert_merges_when_cosine_above_threshold(lib, isolated_store):
    """两个完全一样的 text → cosine=1.0 → 合并。"""
    cand1 = Candidate(text="盘整缩量", supporting_sample_ids=["S1", "S2"], K=2, N=3)
    cand2 = Candidate(text="盘整缩量", supporting_sample_ids=["S4", "S5"], K=2, N=3)

    f1 = lib.upsert_candidate(cand1, batch_sample_ids=["S1", "S2", "S3"], source="ai_induction")
    f2 = lib.upsert_candidate(cand2, batch_sample_ids=["S4", "S5", "S6"], source="ai_induction")

    assert f1.id == f2.id == "F-001"  # 合并到同一 feature
    loaded = isolated_store.load("F-001")
    assert loaded.alpha == pytest.approx(ALPHA_PRIOR + 4)  # K=2+2
    assert loaded.beta == pytest.approx(BETA_PRIOR + 2)    # N-K=1+1
    assert set(loaded.observed_samples) == {"S1", "S2", "S3", "S4", "S5", "S6"}


def test_upsert_creates_new_when_cosine_below_threshold(lib, isolated_store):
    """两个完全不同的 text → cosine 低 → 各自新建。"""
    cand1 = Candidate(text="盘整缩量", supporting_sample_ids=["S1", "S2"], K=2, N=2)
    cand2 = Candidate(text="完全不相关的另一种规律", supporting_sample_ids=["S3", "S4"], K=2, N=2)

    f1 = lib.upsert_candidate(cand1, batch_sample_ids=["S1", "S2"], source="ai_induction")
    f2 = lib.upsert_candidate(cand2, batch_sample_ids=["S3", "S4"], source="ai_induction")

    assert f1.id == "F-001"
    assert f2.id == "F-002"
    assert isolated_store.load("F-001").text != isolated_store.load("F-002").text


def test_lookup_by_cosine_returns_above_threshold(lib, isolated_store, fake_embedder):
    cand = Candidate(text="规律 A", supporting_sample_ids=["S1", "S2"], K=2, N=2)
    lib.upsert_candidate(cand, batch_sample_ids=["S1", "S2"], source="ai_induction")

    target_emb = fake_embedder.embed_text("规律 A")
    matches = lib.lookup_by_cosine(target_emb, threshold=L0_MERGE_THRESHOLD)
    assert len(matches) == 1
    assert matches[0].id == "F-001"


def test_recompute_from_observations(lib, isolated_store):
    cand = Candidate(text="规律 A", supporting_sample_ids=["S1", "S2"], K=2, N=3)
    lib.upsert_candidate(cand, batch_sample_ids=["S1", "S2", "S3"], source="ai_induction")

    feature = lib.recompute("F-001")
    expected_alpha = ALPHA_PRIOR + 2
    expected_beta = BETA_PRIOR + 1
    assert feature.alpha == pytest.approx(expected_alpha)
    assert feature.beta == pytest.approx(expected_beta)


def test_signal_computed_via_p5(lib, isolated_store):
    """signal_after = beta.ppf(0.05, α, β)，应在 (0, 1) 之间。"""
    cand = Candidate(text="规律 A", supporting_sample_ids=["S1", "S2", "S3"], K=3, N=3)
    feature = lib.upsert_candidate(cand, batch_sample_ids=["S1", "S2", "S3"], source="ai_induction")
    loaded = isolated_store.load("F-001")
    last_obs = loaded.observations[-1]
    assert 0 < last_obs.signal_after < 1


def test_observation_entries_per_sample(lib, isolated_store):
    """每个 batch_sample 写一条 obs（按粒度 (sample, feature)）。"""
    cand = Candidate(text="规律 A", supporting_sample_ids=["S1"], K=1, N=3)
    # 注意：K=1 在真实流程会被 inducer 过滤，此处直接构造 cand 是允许的
    lib.upsert_candidate(cand, batch_sample_ids=["S1", "S2", "S3"], source="ai_induction")

    loaded = isolated_store.load("F-001")
    sample_ids_in_obs = [o.sample_id for o in loaded.observations]
    assert sorted(sample_ids_in_obs) == ["S1", "S2", "S3"]
    # 支持的 sample 是 K=1，未支持的是 K=0
    s1_obs = next(o for o in loaded.observations if o.sample_id == "S1")
    s2_obs = next(o for o in loaded.observations if o.sample_id == "S2")
    assert s1_obs.K == 1
    assert s2_obs.K == 0
    assert s1_obs.N == 1
    assert s2_obs.N == 1


def test_status_band_strong_when_high_signal(lib, isolated_store):
    """连续多次 K=N 应让 P5 升到 strong 区间。"""
    for i in range(20):
        cand = Candidate(
            text=f"规律 A",
            supporting_sample_ids=[f"S{i*3+1}", f"S{i*3+2}", f"S{i*3+3}"],
            K=3, N=3,
        )
        lib.upsert_candidate(
            cand,
            batch_sample_ids=[f"S{i*3+1}", f"S{i*3+2}", f"S{i*3+3}"],
            source="ai_induction",
        )

    loaded = isolated_store.load("F-001")
    # α ≈ 60.5, β ≈ 0.5 → P5 应 > 0.6
    from BreakoutStrategy.feature_library.feature_models import derive_status_band
    band = derive_status_band(loaded.observations[-1].signal_after, loaded.provenance)
    assert band == StatusBand.STRONG
