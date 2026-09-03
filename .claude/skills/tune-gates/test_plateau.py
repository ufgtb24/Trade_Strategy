# -*- coding: utf-8 -*-
"""plateau.py 单元测试(tune-gates skill 自带;需显式路径跑,不进默认 pytest 收集):
uv run pytest .claude/skills/tune-gates/test_plateau.py -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from plateau import intersect, judge_gate, load, plateau  # noqa: E402

REL, MINM = 0.05, 100


def g(**kw):
    """造一个闸数据 dict:x/fr/fp/match 必填,其余可选。"""
    base = {"x": [1, 2, 3, 4, 5, 6, 7, 8, 9],
            "fr": [0.5] * 9, "fp": [0.7] * 9, "match": [150] * 9}
    base.update(kw)
    return base


def test_wide_plateau_pick_center():
    """宽平台:两侧掉、中间平 → 推荐落在平台中心,无警告。"""
    d = g(fr=[0.4, 0.8, 0.82, 0.81, 0.8, 0.79, 0.8, 0.4, 0.3])
    v = judge_gate(d, REL, MINM)
    assert v["fr_plateau"] == (2, 7)
    assert v["recommend_x"] in (4, 5)
    assert not v["warnings"]


def test_single_spike_narrow_warning():
    """单尖峰:只有一格高 → 交集过窄警告。"""
    d = g(fr=[0.3, 0.3, 0.3, 0.95, 0.3, 0.3, 0.3, 0.3, 0.3])
    v = judge_gate(d, REL, MINM)
    assert any("疑似尖峰" in w for w in v["warnings"])


def test_no_intersection_warning():
    """fr 与 FP 平台不相交 → 无交集警告。"""
    d = g(fr=[0.9, 0.88, 0.86, 0.6, 0.3, 0.2, 0.2, 0.2, 0.2],
          fp=[0.6, 0.62, 0.64, 0.66, 0.68, 0.9, 0.89, 0.88, 0.87])
    v = judge_gate(d, REL, MINM)
    assert v["intersection"] is None
    assert any("无交集" in w for w in v["warnings"])


def test_narrow_intersection_is_spike_warning():
    """fr 平台仅 1 格(0.95 容差线只过一点)→ 交集过窄,「疑似尖峰」警告。"""
    d = g(fr=[0.3, 0.95, 0.8, 0.81, 0.8, 0.79, 0.8, 0.4, 0.3])
    v = judge_gate(d, REL, MINM)
    # fr 峰 0.95(容差线 0.9025)只有 x=2 过线 → fr 平台=(2,2);与 FP 平台 [1,9]
    # 交集=(2,2) 仅 1 档,「疑似尖峰」必触发;贴边警告针对交集外峰紧邻边界
    assert any("尖峰" in w for w in v["warnings"])


def test_year_disagreement_warning():
    """分年反号:两年 fr 平台分居两端 → 稳健交集空 + 分年警告。"""
    d = g(fr=[0.9, 0.88, 0.86, 0.6, 0.4, 0.38, 0.36, 0.3, 0.2],
          fr_y1=[0.9, 0.88, 0.86, 0.6, 0.4, 0.38, 0.36, 0.3, 0.2],
          fr_y2=[0.2, 0.3, 0.36, 0.38, 0.4, 0.6, 0.86, 0.88, 0.9])
    v = judge_gate(d, REL, MINM)
    assert v["robust_intersection"] is None
    assert any("分年" in w for w in v["warnings"])


def test_match_below_floor_warning():
    """平台内 match 跌破功效线 → 警告。"""
    d = g(match=[150, 150, 150, 150, 150, 40, 40, 150, 150])
    v = judge_gate(d, REL, MINM)
    assert any("功效线" in w for w in v["warnings"])


def test_intersect_and_load_roundtrip(tmp_path):
    """区间求交 + CSV 读写排序。"""
    assert intersect((1, 4), (3, 6)) == (3, 4)
    assert intersect((1, 2), (3, 6)) is None
    p = tmp_path / "s.csv"
    p.write_text("gate,x,fr,fp,match\nA,3,0.5,0.7,100\nA,1,0.4,0.6,120\n")
    d = load(str(p))
    assert d["A"]["x"] == [1, 3]


def test_plot_smoke(tmp_path):
    """绘图冒烟:合成一闸跑通出 png。"""
    import plateau
    d = g(fr=[0.4, 0.8, 0.82, 0.81, 0.8, 0.79, 0.8, 0.4, 0.3])
    v = judge_gate(d, REL, MINM)
    out = tmp_path / "A.png"
    plateau.plot_gate("A", d, v, out, MINM)
    assert out.exists() and out.stat().st_size > 5000
