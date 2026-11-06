"""eval_meta 协议:end_node 手声明 + head_buffer 从 Params 推导(参数改动自动传导);默认 yaml 可读。"""
from dataclasses import fields, replace

import pytest
import yaml

from path2_apps.new_step import eval_meta
from path2_apps.new_step.params import DEFAULT_YAML_PATH, Params, PlateauParams


def test_default_meta():
    """默认参数:end_node = plateau.today(plateau 容器 today 槽的当天);
    head_buffer = max_days + max_step_bars + old_window + 1 = 40 + 5 + 15 + 1。"""
    assert eval_meta() == {"end_node": "plateau.today", "head_buffer_trading_days": 61}


@pytest.mark.parametrize("field, value, expect", [
    ("max_days", 10, 10 + 5 + 15 + 1),
    ("max_step_bars", 2, 40 + 2 + 15 + 1),
    ("old_window", 30, 40 + 5 + 30 + 1),
])
def test_head_buffer_tracks_params(field, value, expect):
    """改任一回看相关的构造参数 → head_buffer 跟着动(推导而非手写常量)。"""
    p = Params.default()
    p = replace(p, plateau=replace(p.plateau, **{field: value}))
    meta = eval_meta(p)
    assert meta["head_buffer_trading_days"] == expect
    assert meta["end_node"] == "plateau.today"


def test_default_yaml_loads():
    """默认 params.yaml 经 from_yaml 读入不报错,且 plateau section 写全了 13 个值。"""
    p = Params.from_yaml(DEFAULT_YAML_PATH)
    assert isinstance(p.plateau, PlateauParams)
    raw = yaml.safe_load(DEFAULT_YAML_PATH.read_text(encoding="utf-8"))
    assert set(raw) == {"plateau", "edges"}
    assert set(raw["plateau"]) == {f.name for f in fields(PlateauParams)}
    assert len(raw["plateau"]) == 13
    assert not raw["edges"]
