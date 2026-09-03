# -*- coding: utf-8 -*-
"""网格提案与 study.py 确定性渲染的测试。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import grid_propose  # noqa: E402
import study_io as S  # noqa: E402

GRID = {("bo", "min_relative_height"): [0.1, 0.15, 0.2, 0.3],
        ("burst", "gap_max"): [4, 8, 12, 20]}
WHERE = {("burst", "first_drought_min"): [0, 20, 40]}
REF = {"bo.min_relative_height": 0.2, "burst.gap_max": 8}


def _render():
    return grid_propose.render_study(
        app_module="path2_apps.demo.dag_spec", base_yaml="params.yaml",
        wide_overrides={"burst": {"first_drought_min": 0}},
        scan_grid=GRID, where_levels=WHERE, ref_point=REF,
        tight_wheres={"FINAL": {("burst", "first_drought_min"): 40}})


def test_render_is_byte_identical_across_calls():
    """★ 红线:同一份 grid 渲染两次必须逐字相同——study.py 的哈希是长表准入校验,
    渲染不稳定会让已有扫描结果无声作废、必须重扫数小时。"""
    assert _render() == _render()


def test_render_is_order_invariant_across_key_permutations():
    """★ 红线补强(修复轮 2,I-1):上面那条同进程调两次的断言测不出「_fmt 忘了排序」这类
    真实威胁——同进程里 dict 迭代序就是插入序,两次调用天然同序,哪怕 `_fmt` 完全不排序
    也会通过(已实测复现:把 `_fmt` 的 `sorted(...)` 换成 `list(v.items())`,那条测试照样
    绿)。真正的红线威胁是"同一份网格,第二次按另一个键序写出来"——这里显式构造顶层网格维 /
    内层 WIDE_OVERRIDES 字段 / REF_POINT / TIGHT_WHERES 均反序、但内容相等的等价输入,
    断言渲染结果逐字相同。"""
    grid_a = {("bo", "min_relative_height"): [0.1, 0.15, 0.2, 0.3], ("burst", "gap_max"): [4, 8, 12, 20]}
    grid_b = {("burst", "gap_max"): [4, 8, 12, 20], ("bo", "min_relative_height"): [0.1, 0.15, 0.2, 0.3]}
    wide_a = {"burst": {"first_drought_min": 0, "distinct_pk_min": 1}}
    wide_b = {"burst": {"distinct_pk_min": 1, "first_drought_min": 0}}
    ref_a = {"bo.min_relative_height": 0.2, "burst.gap_max": 8}
    ref_b = {"burst.gap_max": 8, "bo.min_relative_height": 0.2}
    tight_a = {"FINAL": {("burst", "first_drought_min"): 40}, "B": {("burst", "gap_max"): 8}}
    tight_b = {"B": {("burst", "gap_max"): 8}, "FINAL": {("burst", "first_drought_min"): 40}}
    assert grid_a == grid_b and wide_a == wide_b and ref_a == ref_b and tight_a == tight_b  # 内容确实相等、只是写序不同

    a = grid_propose.render_study(app_module="path2_apps.demo.dag_spec", base_yaml="params.yaml",
                                   wide_overrides=wide_a, scan_grid=grid_a, where_levels=WHERE,
                                   ref_point=ref_a, tight_wheres=tight_a)
    b = grid_propose.render_study(app_module="path2_apps.demo.dag_spec", base_yaml="params.yaml",
                                   wide_overrides=wide_b, scan_grid=grid_b, where_levels=WHERE,
                                   ref_point=ref_b, tight_wheres=tight_b)
    assert a == b


def test_rendered_study_loads_with_all_eight_declarations(tmp_path):
    """渲染出来的必须是 load_study 能吃的合法声明(8 项齐全)。"""
    p = tmp_path / "study.py"
    p.write_text(_render(), encoding="utf-8")
    st = S.load_study(p)
    for name in S.STUDY_NAMES:
        assert hasattr(st, name), f"缺少声明 {name}"
    assert st.SCAN_GRID == GRID
    assert st.WHERE_LEVELS == WHERE
    assert st.REF_POINT == REF


def test_render_does_not_embed_timestamp():
    """不得含时间戳——它会让每次渲染的哈希都不同。"""
    import re
    text = _render()
    assert not re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", text)


def test_propose_levels_always_include_current_default():
    """推荐档位必须含参数当前默认值:参照格才落得进网格,build_classification 的
    REF_POINT 守卫才过得去。"""
    for default in (0.2, 8, 1.5, 40):
        levels = grid_propose.levels_for(default)
        assert default in levels
        assert len(levels) >= 3
        assert levels == sorted(set(levels))


def test_propose_levels_rejects_non_numeric():
    """非数值型不猜档位,返回 None 让人来定。"""
    assert grid_propose.levels_for("close") is None
    assert grid_propose.levels_for(None) is None


def test_levels_for_never_crosses_zero_when_default_positive():
    """★ I-3(修复轮 2):0.5x 乘子对小整数默认值取整会下溢到 0——0 对"根数/个数"这类参数
    几乎必然非法(真实实测命中:burst.min_bos、tb.stop_confirm_bars 默认值均为 1,旧版
    levels_for(1) 含 0,两个字段因此被 classify() 拒、判成"探不出来")。默认值为正时,
    产出的候选档位里不得出现 ≤0 的值。"""
    for default in (1, 2, 3, 5, 0.2, 1.5, 8, 40):
        levels = grid_propose.levels_for(default)
        assert all(v > 0 for v in levels), f"levels_for({default}) 含非正档: {levels}"


def test_levels_for_of_one_is_pinned():
    """剔掉非法档(0)后只剩 {1, 2},不足 3 档,按需向上延长乘子阶梯补足——钉住具体产出。"""
    assert grid_propose.levels_for(1) == [1, 2, 4]


def test_ref_point_is_derived_from_production_values():
    """★ 参照格自动推导:取生产参数在网格上的落点,只含 D 维。

    手写 REF_POINT 曾导致真实事故——生产值已从 2 改成 1,手写的还停在 2,
    被误当成「需要用户拍板的语义决定」。自动推导后这类问题不会再出现。
    """
    base = {"bo": {"min_relative_height": 0.2}, "burst": {"gap_max": 8, "min_bos": 1}}
    kinds = {("bo", "min_relative_height"): "D", ("burst", "gap_max"): "D",
             ("burst", "min_bos"): "F"}
    grid = {("bo", "min_relative_height"): [0.1, 0.2, 0.3],
            ("burst", "gap_max"): [4, 8, 12],
            ("burst", "min_bos"): [1, 2, 3]}
    ref = grid_propose.ref_point_from_base(base, grid, kinds)
    assert ref == {"bo.min_relative_height": 0.2, "burst.gap_max": 8}   # F 维不进
    for dotted, v in ref.items():
        sec, field = dotted.split(".")
        assert v in grid[(sec, field)], "参照格必须精确落在网格档位上"


def test_ref_point_rejects_production_value_off_grid():
    """生产值不在档位里 → 响亮失败,不静默取最近档(那会让参照格偷偷变成别的格)。"""
    import pytest
    base = {"bo": {"x": 0.25}}
    with pytest.raises(SystemExit):
        grid_propose.ref_point_from_base(base, {("bo", "x"): [0.1, 0.2, 0.3]}, {("bo", "x"): "D"})


def test_propose_on_real_app_does_not_crash_and_finds_both_d_and_w_dims():
    """★ 真实 app 冒烟(修复轮补):上面 7 个测试全在假树上跑,漏掉了两处会让 propose()
    在真实 app 上整体崩溃的问题——①机械铺档可能撞上 detector 自身的构造不变式(如
    bo.total_window 探到 0.5x 候选时与 bo.min_side_bars 默认值冲突,build_pattern 直接
    抛异常);②批量单次 classify 只要 base 里有任何 where 阈值型字段就会被 classify 末尾
    的 W 守卫拒绝整批(bb_v1 恰好有好几个)。propose() 改逐维探测后,这两类失败只让**那
    一维**的 kind=None 带 reason,不炸全局;这里断言两条探测路径都真的走通了(至少各出
    一个 D 与一个 W),而不是全军覆没成 None。"""
    import importlib
    mod = importlib.import_module("path2_apps.bb_v1.dag_spec")
    base = mod.Params.from_yaml(S.app_dir(mod) / "params.yaml").to_dict()
    result = grid_propose.propose(mod, base)
    kinds = {(p["section"], p["field"]): p["kind"] for p in result["params"]}
    assert "D" in kinds.values(), "逐维探测应至少探出一个 D 维(如 bo.min_relative_height)"
    assert "W" in kinds.values(), "逐维探测应至少探出一个 W 维(如 burst.first_drought_min)"
    # ★ I-3 回归钉子:tb.stop_confirm_bars 是参照格事故里的那个参数、也是历史调参的主改动项,
    # 旧版 levels_for(1) 含非法档 0 会让它退化成"探不出来"——这里必须探得出、不能是 None。
    assert kinds[("tb", "stop_confirm_bars")] is not None, \
        "tb.stop_confirm_bars 不应退化为探不出来(I-3 回归)"
    for p in result["params"]:
        if p["kind"] is None:
            assert p["reason"], f"{p['section']}.{p['field']} kind=None 但 reason 为空"
