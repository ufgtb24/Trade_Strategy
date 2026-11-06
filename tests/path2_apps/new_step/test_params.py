"""new_step 参数 schema:dataclass 默认值、frozen、detector 构造参数切片、yaml 局部覆盖与未知键校验。

只钉 dataclass 默认值(yaml 缺字段时的兜底 / 测试与脚本默认),不钉 params.yaml 里的取值。
"""
import inspect

import pytest

from path2_apps.new_step.params import EdgesParams, Params, PlateauParams
from path2_apps.new_step.plateau import PlateauDetector


def test_default_returns_nested_instances():
    p = Params.default()
    assert isinstance(p.plateau, PlateauParams)
    assert isinstance(p.edges, EdgesParams)


def test_default_plateau_defaults():
    pl = Params.default().plateau
    # 识别器构造参数
    assert pl.old_window == 15
    assert pl.strong_k == 3.0
    assert pl.max_step_bars == 5
    assert pl.max_days == 40
    # where 阈值
    assert pl.old_flat_max == 1.2
    assert pl.step_rise_min == 0.4
    assert pl.vs_left_min == 4.0
    assert pl.vs_right_min == 2.5
    assert pl.step_vol_min == 3.0
    assert pl.keep_min == 0.3
    assert pl.calm_max == 0.6
    assert pl.vs_high_max == 1.0
    assert pl.body_min == 0.0


def test_params_frozen_top_and_nested():
    p = Params.default()
    with pytest.raises(Exception):
        p.plateau = PlateauParams()
    with pytest.raises(Exception):
        p.plateau.old_window = 99


def test_plateau_kwargs_match_detector_signature():
    """plateau_kwargs 与 PlateauDetector.__init__ 一一对应;阈值走 where,不进 detector。"""
    kw = Params.default().plateau_kwargs()
    sig = set(inspect.signature(PlateauDetector.__init__).parameters) - {"self"}
    assert set(kw) == sig == {"old_window", "strong_k", "max_step_bars", "max_days"}
    PlateauDetector(**kw)


def test_from_yaml_partial_override(tmp_path):
    """section 内局部字段 → 缺失字段用子 dataclass default 兜底。"""
    path = tmp_path / "p.yaml"
    path.write_text("plateau:\n  max_days: 10\n  keep_min: 0.5\n", encoding="utf-8")
    p = Params.from_yaml(path)
    assert p.plateau.max_days == 10
    assert p.plateau.keep_min == 0.5
    assert p.plateau.old_window == 15        # yaml 未提及,用 default
    assert p.edges == EdgesParams()          # 整 section 缺失,用 default


@pytest.mark.parametrize("text, bad", [
    ("plateau: {max_days: 10}\nburst: {gap_max: 8}\n", "burst"),        # 第一版的 section 已删
    ("plateau:\n  max_dayz: 10\n", "max_dayz"),
])
def test_from_yaml_rejects_unknown_keys(tmp_path, text, bad):
    path = tmp_path / "p.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match=bad):
        Params.from_yaml(path)
