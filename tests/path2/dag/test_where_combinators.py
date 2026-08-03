"""W.any / W.not_ / W.all 升级:递归 meta + witness 全量求值(不短路)。"""
from dataclasses import dataclass

from path2.dag import where as W


@dataclass(frozen=True)
class _E:
    distinct_pk: int = 0
    max_bar_vol_ratio: float = 0.0
    first_drought: int = 0


def _pk_or_vol():
    return W.any(W.attr("distinct_pk", ">=", 4),
                    W.attr("max_bar_vol_ratio", ">=", 8.0))


def test_any_truth_table():
    f = _pk_or_vol()
    assert f(_E(distinct_pk=5)) is True
    assert f(_E(max_bar_vol_ratio=9.0)) is True
    assert f(_E()) is False


def test_nested_or_inside_and():
    """(A or B) and C —— 用户诉求的原型表达式。"""
    f = W.all(_pk_or_vol(), W.attr("first_drought", ">=", 20))
    assert f(_E(distinct_pk=5, first_drought=25)) is True
    assert f(_E(distinct_pk=5, first_drought=3)) is False
    assert f(_E(first_drought=25)) is False


def test_not_flips():
    f = W.not_(W.attr("distinct_pk", ">=", 4))
    assert f(_E(distinct_pk=3)) is True
    assert f(_E(distinct_pk=5)) is False


def test_not_none_semantics_follows_inner():
    """attr 对 None 判 False(不满足),取反后为 True——纯逻辑取反,None 语义随内层。"""
    f = W.not_(W.attr("distinct_pk", ">=", 4))
    assert f(_E(distinct_pk=None)) is True


def test_combinator_meta_recursive():
    f = _pk_or_vol()
    assert f.meta["kind"] == "or"
    assert [m["field"] for m in f.meta["children"]] == ["distinct_pk", "max_bar_vol_ratio"]
    g = W.all(W.attr("first_drought", ">=", 20))
    assert g.meta["kind"] == "and"
    n = W.not_(W.attr("distinct_pk", ">=", 4))
    assert n.meta["kind"] == "not" and n.meta["children"][0]["field"] == "distinct_pk"


def test_witness_evaluates_all_branches_no_short_circuit():
    """or 首支已真,witness 仍算出第二支的实测值(调参对照的核心诉求)。"""
    w = _pk_or_vol().witness(_E(distinct_pk=9, max_bar_vol_ratio=5.5))
    assert w.satisfied is True
    assert w.label == "or"
    assert [c.measured for c in w.children] == [9, 5.5]
    assert [c.satisfied for c in w.children] == [True, False]
    assert [c.label for c in w.children] == ["distinct_pk", "max_bar_vol_ratio"]


def test_attr_witness_is_leaf():
    w = W.attr("distinct_pk", ">=", 4).witness(_E(distinct_pk=3))
    assert w.satisfied is False and w.measured == 3 and w.children == ()
    assert w.label == "distinct_pk"


def test_witness_bool_backcompat():
    """__bool__ == satisfied 保持(旧代码 if witness: 行为不变)。"""
    assert bool(W.attr("distinct_pk", ">=", 4).witness(_E(distinct_pk=9))) is True
    assert bool(_pk_or_vol().witness(_E())) is False


def test_witness_of_bare_callable_degrades():
    from path2.dag.where import witness_of
    w = witness_of(lambda e: e.distinct_pk > 0, _E(distinct_pk=1))
    assert w.satisfied is True and w.measured is None and w.children == ()


def test_lifted_bare_callable_inside_combinator():
    """裸 lambda 进组合子被 _lift 包成不透明叶子:判定正确,witness 不炸。"""
    f = W.any(lambda e: e.distinct_pk >= 4)
    assert f(_E(distinct_pk=5)) is True
    w = f.witness(_E(distinct_pk=5))
    assert len(w.children) == 1 and w.children[0].satisfied is True
