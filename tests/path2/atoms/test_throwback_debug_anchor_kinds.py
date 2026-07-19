"""v3 anchor_kind-gated debug 契约锚测试(throwback.py)。

用 ast 静态解析,不运行 detector,不依赖 fixture。

契约:
- throwback.py 里必有且只有 5 处 debug_break call(总数守恒)
- 每处必须传 anchor_kind kwarg,且必须是 str literal(不允许变量 / f-string / 表达式)
- 5 处 anchor_kind 字面量分布 Counter == {'gate':1, 'trough':1, 'end':2, 'entry':1}

不依赖精确 lineno · 抗 throwback.py 上下加行漂移。
"""
import ast
import pathlib
from collections import Counter


THROWBACK_PATH = pathlib.Path(__file__).resolve().parents[3] / "path2" / "atoms" / "throwback.py"
EXPECTED_ANCHOR_KIND_COUNTER = Counter({"gate": 1, "trough": 1, "end": 2, "entry": 1})


def _collect_debug_break_calls():
    src = THROWBACK_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(THROWBACK_PATH))
    return [n for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and getattr(n.func, "id", None) == "debug_break"]


def test_throwback_has_exactly_five_debug_break_calls():
    calls = _collect_debug_break_calls()
    assert len(calls) == 5, (
        f"expected 5 debug_break calls in throwback.py · got {len(calls)}"
        f" at lines {[c.lineno for c in calls]}"
    )


def test_every_debug_break_has_anchor_kind_kwarg_as_str_literal():
    calls = _collect_debug_break_calls()
    for c in calls:
        anchor_kind_kw = next((k for k in c.keywords if k.arg == "anchor_kind"), None)
        assert anchor_kind_kw is not None, (
            f"L{c.lineno} debug_break missing required anchor_kind kwarg"
        )
        assert isinstance(anchor_kind_kw.value, ast.Constant) and isinstance(anchor_kind_kw.value.value, str), (
            f"L{c.lineno} anchor_kind must be str literal (for grep-ability) · got "
            f"{ast.dump(anchor_kind_kw.value)}"
        )


def test_throwback_anchor_kind_distribution_matches_baseline():
    """anchor_kind 分布 Counter 严格等于 baseline · 抗 lineno 漂移。"""
    calls = _collect_debug_break_calls()
    anchor_kinds = [
        next(k.value.value for k in c.keywords if k.arg == "anchor_kind")
        for c in calls
    ]
    actual = Counter(anchor_kinds)
    assert actual == EXPECTED_ANCHOR_KIND_COUNTER, (
        f"anchor_kind distribution mismatch:\n"
        f"  expected {dict(EXPECTED_ANCHOR_KIND_COUNTER)}\n"
        f"  actual   {dict(actual)}\n"
        f"lines: {[c.lineno for c in calls]}\n"
        f"anchor_kinds: {anchor_kinds}"
    )


EXPECTED_CLASS_ID_COUNTER = Counter({"tb": 5})   # 5 处 tb 埋点 · 全部 class_id='tb'
EXPECTED_JOINT_COUNTER = Counter({
    ("gate",   "tb"): 1,
    ("trough", "tb"): 1,
    ("end",    "tb"): 2,
    ("entry",  "tb"): 1,
})


def test_every_debug_break_has_class_id_kwarg_as_str_literal():
    """契约 · 每处 debug_break 必带 class_id kwarg 且是 str literal(grep-ability)。"""
    calls = _collect_debug_break_calls()
    for c in calls:
        class_kw = next((k for k in c.keywords if k.arg == "class_id"), None)
        assert class_kw is not None, (
            f"L{c.lineno} debug_break missing required class_id kwarg"
        )
        assert isinstance(class_kw.value, ast.Constant) and isinstance(class_kw.value.value, str), (
            f"L{c.lineno} class_id must be str literal (for grep-ability) · got "
            f"{ast.dump(class_kw.value)}"
        )


def test_throwback_class_id_distribution_matches_baseline():
    """class_id 分布 Counter 严格等于 baseline · throwback 全 tb。"""
    calls = _collect_debug_break_calls()
    class_ids = [
        next(k.value.value for k in c.keywords if k.arg == "class_id")
        for c in calls
    ]
    actual = Counter(class_ids)
    assert actual == EXPECTED_CLASS_ID_COUNTER, (
        f"class_id distribution mismatch:\n"
        f"  expected {dict(EXPECTED_CLASS_ID_COUNTER)}\n"
        f"  actual   {dict(actual)}\n"
        f"lines: {[c.lineno for c in calls]}\n"
        f"class_ids: {class_ids}"
    )


def test_throwback_joint_distribution_matches_baseline():
    """(anchor_kind, class_id) 二维联合 Counter 严格等于 baseline。"""
    calls = _collect_debug_break_calls()
    joint = [
        (
            next(k.value.value for k in c.keywords if k.arg == "anchor_kind"),
            next(k.value.value for k in c.keywords if k.arg == "class_id"),
        )
        for c in calls
    ]
    actual = Counter(joint)
    assert actual == EXPECTED_JOINT_COUNTER, (
        f"(anchor_kind, class_id) joint distribution mismatch:\n"
        f"  expected {dict(EXPECTED_JOINT_COUNTER)}\n"
        f"  actual   {dict(actual)}\n"
        f"lines: {[c.lineno for c in calls]}\n"
        f"pairs: {joint}"
    )
