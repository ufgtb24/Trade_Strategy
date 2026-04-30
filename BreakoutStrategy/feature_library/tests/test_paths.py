"""Tests for feature_library path constants."""
from pathlib import Path

from BreakoutStrategy.feature_library import paths


def test_feature_library_root_is_repo_relative():
    """FEATURE_LIBRARY_ROOT 应位于 repo 根目录下的 feature_library/。"""
    assert paths.FEATURE_LIBRARY_ROOT.name == "feature_library"
    assert paths.FEATURE_LIBRARY_ROOT.is_absolute()


def test_samples_dir_under_root():
    assert paths.SAMPLES_DIR == paths.FEATURE_LIBRARY_ROOT / "samples"


def test_sample_dir_resolution():
    sample_id = "BO_AAPL_20230115"
    expected = paths.SAMPLES_DIR / sample_id
    assert paths.sample_dir(sample_id) == expected


def test_sample_artifact_paths():
    sample_id = "BO_AAPL_20230115"
    base = paths.sample_dir(sample_id)
    assert paths.chart_png_path(sample_id) == base / "chart.png"
    assert paths.meta_yaml_path(sample_id) == base / "meta.yaml"
    assert paths.nl_description_path(sample_id) == base / "nl_description.md"


def test_ensure_sample_dir_creates(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "FEATURE_LIBRARY_ROOT", tmp_path / "feature_library")
    monkeypatch.setattr(paths, "SAMPLES_DIR", paths.FEATURE_LIBRARY_ROOT / "samples")
    sample_id = "BO_TEST_20260101"
    created = paths.ensure_sample_dir(sample_id)
    assert created.is_dir()
    assert created == paths.SAMPLES_DIR / sample_id
