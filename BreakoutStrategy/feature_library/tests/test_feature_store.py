"""Tests for FeatureStore (features/<id>.yaml CRUD)."""
from datetime import datetime

import pytest

from BreakoutStrategy.feature_library.feature_models import (
    Feature, ObservationLogEntry,
)
from BreakoutStrategy.feature_library.feature_store import (
    FeatureStore, slugify,
)


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    from BreakoutStrategy.feature_library import paths
    monkeypatch.setattr(paths, "FEATURE_LIBRARY_ROOT", tmp_path / "feature_library")
    monkeypatch.setattr(paths, "SAMPLES_DIR", paths.FEATURE_LIBRARY_ROOT / "samples")
    monkeypatch.setattr(paths, "FEATURES_DIR", paths.FEATURE_LIBRARY_ROOT / "features")
    return FeatureStore()


@pytest.fixture
def sample_feature() -> Feature:
    return Feature(
        id="F-001",
        text="盘整缩量后突破",
        embedding=[0.1, 0.2, 0.3],
        alpha=1.5,
        beta=0.5,
        last_update_ts=datetime(2026, 4, 27, 14, 30),
        provenance="ai_induction",
        observed_samples=["BO_AAPL_20210617"],
        total_K=1,
        total_N=1,
        total_C_weighted=0,
        observations=[
            ObservationLogEntry(
                id="obs-aaa",
                ts=datetime(2026, 4, 27, 14, 30),
                source="ai_induction",
                sample_id="BO_AAPL_20210617",
                K=1, N=1,
                alpha_after=1.5, beta_after=0.5, signal_after=0.07,
            )
        ],
    )


def test_save_and_load_roundtrip(isolated_store, sample_feature):
    isolated_store.save(sample_feature)
    loaded = isolated_store.load(sample_feature.id)
    assert loaded.id == sample_feature.id
    assert loaded.text == sample_feature.text
    assert loaded.alpha == sample_feature.alpha
    assert loaded.observations[0].sample_id == "BO_AAPL_20210617"
    assert loaded.observations[0].epoch_tag is None
    assert loaded.observations[0].superseded_by is None
    assert loaded.research_status == "active"
    assert loaded.factor_overlap_declared is None


def test_save_creates_yaml_file(isolated_store, sample_feature):
    """save 后能 glob 到 F-001*.yaml。"""
    from BreakoutStrategy.feature_library import paths
    isolated_store.save(sample_feature)
    found = list(paths.FEATURES_DIR.glob("F-001*.yaml"))
    assert len(found) == 1, f"expected 1 file matching F-001*.yaml, got {found}"


def test_exists(isolated_store, sample_feature):
    assert not isolated_store.exists("F-001")
    isolated_store.save(sample_feature)
    assert isolated_store.exists("F-001")


def test_next_id_starts_at_001(isolated_store):
    assert isolated_store.next_id() == "F-001"


def test_next_id_increments(isolated_store, sample_feature):
    isolated_store.save(sample_feature)
    assert isolated_store.next_id() == "F-002"


def test_list_all_returns_all_features(isolated_store, sample_feature):
    isolated_store.save(sample_feature)
    f2 = Feature(
        id="F-002", text="另一个",
        embedding=[0.4, 0.5, 0.6],
        alpha=2.0, beta=1.0,
        last_update_ts=datetime(2026, 4, 27, 14, 30),
        provenance="ai_induction",
        observed_samples=["BO_TEST_20240101"],
        total_K=2, total_N=3, total_C_weighted=0,
    )
    isolated_store.save(f2)
    all_features = isolated_store.list_all()
    assert {f.id for f in all_features} == {"F-001", "F-002"}


def test_slugify_chinese_returns_empty():
    assert slugify("盘整缩量后突破") == ""


def test_slugify_english_keeps_kebab():
    assert slugify("Tight Rectangle Basing") == "tight-rectangle-basing"


def test_slugify_truncated_to_30():
    long = "this is a very long text that should be truncated for filename safety"
    assert len(slugify(long)) <= 30


def test_slugify_strips_dangerous_chars():
    assert "/" not in slugify("a/b/c")
    assert "\\" not in slugify(r"a\b\c")
