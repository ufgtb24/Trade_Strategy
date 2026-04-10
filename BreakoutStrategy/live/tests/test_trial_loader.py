"""Test TrialLoader loads filter.yaml and exposes Top-1 template."""
from pathlib import Path

import pytest

from BreakoutStrategy.live.pipeline.trial_loader import TrialBundle, TrialLoader


FIXTURE = Path(__file__).parent / "fixtures" / "mini_filter.yaml"


def test_trial_loader_loads_filter_yaml(tmp_path: Path):
    """TrialLoader.load() 返回完整的 TrialBundle。"""
    trial_dir = tmp_path / "trials" / "1"
    trial_dir.mkdir(parents=True)
    (trial_dir / "filter.yaml").write_text(FIXTURE.read_text())

    bundle = TrialLoader(trial_dir).load()
    assert isinstance(bundle, TrialBundle)


def test_trial_loader_selects_top_1_template(tmp_path: Path):
    """Top-1 模板应是 median 最高的那个（这里是 median=0.5 的 age+test+height+volume）。"""
    trial_dir = tmp_path / "trials" / "1"
    trial_dir.mkdir(parents=True)
    (trial_dir / "filter.yaml").write_text(FIXTURE.read_text())

    bundle = TrialLoader(trial_dir).load()
    assert bundle.template["name"] == "age+test+height+volume"
    assert bundle.template["median"] == 0.5
    assert bundle.template["factors"] == ["age", "test", "height", "volume"]


def test_trial_loader_extracts_thresholds_and_negative_factors(tmp_path: Path):
    trial_dir = tmp_path / "trials" / "1"
    trial_dir.mkdir(parents=True)
    (trial_dir / "filter.yaml").write_text(FIXTURE.read_text())

    bundle = TrialLoader(trial_dir).load()
    assert bundle.thresholds["age"] == 23.0
    assert bundle.thresholds["height"] == 0.46
    assert bundle.negative_factors == frozenset({"age", "test"})


def test_trial_loader_exposes_scan_params(tmp_path: Path):
    trial_dir = tmp_path / "trials" / "1"
    trial_dir.mkdir(parents=True)
    (trial_dir / "filter.yaml").write_text(FIXTURE.read_text())

    bundle = TrialLoader(trial_dir).load()
    assert "breakout_detector" in bundle.scan_params
    assert "general_feature" in bundle.scan_params
    assert "quality_scorer" in bundle.scan_params
    assert bundle.scan_params["breakout_detector"]["total_window"] == 20


def test_trial_loader_missing_filter_yaml_raises(tmp_path: Path):
    trial_dir = tmp_path / "trials" / "1"
    trial_dir.mkdir(parents=True)
    # 不创建 filter.yaml

    with pytest.raises(FileNotFoundError):
        TrialLoader(trial_dir).load()
