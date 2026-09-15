# -*- coding: utf-8 -*-
"""budget 预算计算器单测(显式路径跑):uv run pytest .claude/skills/tune-gates/test_budget.py -q"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from budget import (R_BAR_DETECT_PRIOR, delta_needed_for_joint, floor_upper, joint_feasible,  # noqa: E402
                    n_pl, se_flip, x_screen, x_single)


def test_bb_v1_calibration_numbers():
    """bb_v1 标定值(只作计算器的数值核对):定案前生产格 SE_level 3.01 点、检测参数 r̄ 0.85、
    筛选族大小 36、q 0.10、设计效应 5、定向占比 0.62、δ 2 点。"""
    assert R_BAR_DETECT_PRIOR == 0.85
    sf = se_flip(3.01, 0.85)
    assert round(sf, 2) == 1.26
    assert round(x_screen(sf, m=36, q=0.10), 1) == 4.8
    assert round(x_single(sf), 1) == 3.5
    assert round(n_pl(0.02, deff=5, s_dec=0.62)) == 8233
    assert n_pl(0.02, deff=5, s_dec=0.62) == pytest.approx(3.29 / 0.02 ** 2, rel=2e-3)


def test_no_calibration_defaults():
    """deff、s_dec 必须显式传入(关键字),不接受缺省或位置传参。"""
    with pytest.raises(TypeError):
        n_pl(0.02)
    with pytest.raises(TypeError):
        n_pl(0.02, 5.0, 0.62)
    with pytest.raises(TypeError):
        floor_upper(1000.0, deff=5.0)


@pytest.mark.parametrize("deff,s_dec,p", [(2.0, 0.4, 0.5), (6.5, 0.9, 0.3), (1.0, 1.0, 0.5)])
def test_floor_equals_delta_on_power_line(deff, s_dec, p):
    """功效线与噪声地板互为反函数:恰在功效线上 floor = δ,bar 更多 floor 更低。"""
    for delta in (0.01, 0.02, 0.05):
        line = n_pl(delta, deff=deff, s_dec=s_dec, p=p)
        assert floor_upper(line, deff=deff, s_dec=s_dec, p=p) == pytest.approx(delta)
        assert floor_upper(2 * line, deff=deff, s_dec=s_dec, p=p) < delta


def test_joint_feasibility():
    sf = se_flip(3.01, 0.85)          # bb_v1 标定例 ≈1.2645 点;单改需 ≈3.54 点,两参数同改需 ≈6.02 点
    assert delta_needed_for_joint(sf, 1) == pytest.approx(x_single(sf))
    assert delta_needed_for_joint(sf, 2) == pytest.approx(1.7 * x_single(sf))
    assert delta_needed_for_joint(sf, 3) == delta_needed_for_joint(sf, 2)
    assert joint_feasible(sf, 4.0, 1) is True
    assert joint_feasible(sf, 4.0, 2) is False
    assert joint_feasible(sf, 6.1, 2) is True
