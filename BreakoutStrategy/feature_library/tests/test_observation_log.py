"""Tests for observation_log."""
from datetime import datetime

import pytest

from BreakoutStrategy.feature_library.feature_models import (
    Feature, ObservationLogEntry,
)
from BreakoutStrategy.feature_library.feature_store import FeatureStore
from BreakoutStrategy.feature_library.observation_log import (
    append_entry, get_active_entries, new_entry_id,
)


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    from BreakoutStrategy.feature_library import paths
    monkeypatch.setattr(paths, "FEATURE_LIBRARY_ROOT", tmp_path / "feature_library")
    monkeypatch.setattr(paths, "SAMPLES_DIR", paths.FEATURE_LIBRARY_ROOT / "samples")
    monkeypatch.setattr(paths, "FEATURES_DIR", paths.FEATURE_LIBRARY_ROOT / "features")
    return FeatureStore()


@pytest.fixture
def empty_feature(isolated_store) -> Feature:
    f = Feature(
        id="F-001", text="test",
        embedding=[0.1], alpha=0.5, beta=0.5,
        last_update_ts=datetime(2026, 4, 27),
        provenance="ai_induction",
        observed_samples=[], total_K=0, total_N=0, total_C_weighted=0,
    )
    isolated_store.save(f)
    return f


def test_new_entry_id_format():
    eid = new_entry_id()
    assert eid.startswith("obs-")
    assert len(eid) >= 8  # obs- + 至少 4 字符


def test_new_entry_id_unique():
    ids = {new_entry_id() for _ in range(100)}
    assert len(ids) == 100  # 全部唯一


def test_append_entry_persists(isolated_store, empty_feature):
    entry = ObservationLogEntry(
        id=new_entry_id(),
        ts=datetime(2026, 4, 27, 14, 30),
        source="ai_induction",
        sample_id="BO_AAPL_20210617",
        K=1, N=1,
        alpha_after=1.5, beta_after=0.5, signal_after=0.07,
    )
    append_entry(isolated_store, "F-001", entry)

    loaded = isolated_store.load("F-001")
    assert len(loaded.observations) == 1
    assert loaded.observations[0].sample_id == "BO_AAPL_20210617"
    assert loaded.observations[0].id == entry.id


def test_get_active_entries_excludes_superseded(isolated_store, empty_feature):
    e1 = ObservationLogEntry(
        id="obs-001",
        ts=datetime(2026, 4, 27),
        source="ai_induction",
        sample_id="BO_X", K=1, N=1,
        alpha_after=1.5, beta_after=0.5, signal_after=0.07,
        superseded_by="obs-002",  # 被 obs-002 覆盖
    )
    e2 = ObservationLogEntry(
        id="obs-002",
        ts=datetime(2026, 4, 27),
        source="ai_induction",
        sample_id="BO_X", K=0, N=1,
        alpha_after=0.5, beta_after=1.5, signal_after=0.01,
    )
    append_entry(isolated_store, "F-001", e1)
    append_entry(isolated_store, "F-001", e2)

    active = get_active_entries(isolated_store, "F-001")
    assert len(active) == 1
    assert active[0].id == "obs-002"


def test_get_active_entries_all_active_when_no_supersede(isolated_store, empty_feature):
    e1 = ObservationLogEntry(
        id="obs-a", ts=datetime(2026, 4, 27),
        source="ai_induction", sample_id="S1", K=1, N=1,
        alpha_after=1.5, beta_after=0.5, signal_after=0.07,
    )
    e2 = ObservationLogEntry(
        id="obs-b", ts=datetime(2026, 4, 27),
        source="ai_induction", sample_id="S2", K=0, N=1,
        alpha_after=1.5, beta_after=1.5, signal_after=0.05,
    )
    append_entry(isolated_store, "F-001", e1)
    append_entry(isolated_store, "F-001", e2)

    active = get_active_entries(isolated_store, "F-001")
    assert len(active) == 2
