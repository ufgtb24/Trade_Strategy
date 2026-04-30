"""Tests for shared dataclasses and status band derivation."""
from datetime import datetime

import pytest

from BreakoutStrategy.feature_library.feature_models import (
    Candidate, Event, Feature, ObservationLogEntry, StatusBand,
    derive_status_band,
)


def test_candidate_dataclass_basic():
    c = Candidate(
        text="盘整缩量后突破",
        supporting_sample_ids=["BO_AAPL_20210617", "BO_MSFT_20220301"],
        K=2, N=5,
    )
    assert c.K == 2
    assert c.N == 5
    assert c.raw_response_excerpt == ""  # default


def test_event_default_C_zero_and_epoch_null():
    e = Event(sample_id="BO_AAPL_20210617", K=1, N=1, source="ai_induction")
    assert e.C == 0
    assert e.epoch_tag is None


def test_observation_log_entry_phase1_fields():
    ent = ObservationLogEntry(
        id="obs-abc123",
        ts=datetime(2026, 4, 27, 14, 30),
        source="ai_induction",
        sample_id="BO_AAPL_20210617",
        K=1, N=1,
        alpha_after=1.5, beta_after=0.5, signal_after=0.07,
    )
    assert ent.epoch_tag is None         # Phase 1 未启用
    assert ent.superseded_by is None     # Phase 1 未启用
    assert ent.C == 0


def test_feature_dataclass_complete():
    f = Feature(
        id="F-001",
        text="盘整缩量后突破",
        embedding=[0.1, 0.2, 0.3],
        alpha=1.5, beta=0.5,
        last_update_ts=datetime(2026, 4, 27, 14, 30),
        provenance="ai_induction",
        observed_samples=["BO_AAPL_20210617"],
        total_K=1, total_N=1, total_C_weighted=0,
        observations=[],
    )
    assert f.research_status == "active"
    assert f.factor_overlap_declared is None


@pytest.mark.parametrize("signal,expected", [
    (0.01, StatusBand.FORGOTTEN),
    (0.04, StatusBand.FORGOTTEN),
    (0.05, StatusBand.CANDIDATE),
    (0.19, StatusBand.CANDIDATE),
    (0.20, StatusBand.SUPPORTED),
    (0.39, StatusBand.SUPPORTED),
    (0.40, StatusBand.CONSOLIDATED),
    (0.59, StatusBand.CONSOLIDATED),
    (0.60, StatusBand.STRONG),
    (0.99, StatusBand.STRONG),
])
def test_derive_status_band_thresholds(signal, expected):
    assert derive_status_band(signal, provenance="ai_induction") == expected


def test_provenance_lock_for_shuffle_origin():
    """provenance startswith 'shuffle-' 时即使 signal 高也锁 candidate（Phase 4+ 防误升级）。"""
    assert derive_status_band(0.80, provenance="shuffle-r1-b0") == StatusBand.CANDIDATE


def test_status_band_yaml_safe_dump():
    """StatusBand 实例应能被 yaml.safe_dump 序列化为干净字符串。"""
    import yaml
    out = yaml.safe_dump({"band": StatusBand.SUPPORTED})
    assert "supported" in out
    # 不应出现 python tag
    assert "!!python" not in out
