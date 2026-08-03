"""W.* —— 节点 where 谓词便利层(一元约束)。小而封闭(奥卡姆,只覆盖业务用到的)。

方向性/区间算子被【类型化边】吸收(结构);容器/标量/存在算子被【节点 where】吸收(一元约束)。
作者写声明时根本看不到旧的 Before/After/Overlaps/Pattern.all。
每个 W.* 返回 WherePredicate: (event_or_seq) -> bool;组合子 all/any/not_ 可任意嵌套。
"""
from __future__ import annotations

import builtins
import operator as _op

from path2.dag.nodes import WherePredicate
from path2.dag.result import ClauseWitness

_OPS = {">=": _op.ge, ">": _op.gt, "<=": _op.le, "<": _op.lt, "==": _op.eq, "!=": _op.ne}


def _cmp(op: str):
    if op not in _OPS:
        raise ValueError(f"未知 op: {op!r}(合法 {sorted(_OPS)})")
    f = _OPS[op]

    def safe(a, b):
        # 属性/聚合值为 None(Optional 字段未赋值,如 BOEvent.drought/vol_ratio)= 不满足该比较。
        # 与旧 app `x is not None and x op thr` 短路语义一致,避免 None op thr 抛 TypeError。
        return False if a is None else f(a, b)

    return safe


class _Pred:
    """where 谓词:callable (x)->bool,额外带 .meta(阈值规则)/.measure(x)(实测值)/
    .children(组合子的子谓词)/.witness(x)(递归 ClauseWitness)。
    __call__ 保持短路(求解热路径每候选都调);witness 全量求值不短路(诊断要看
    每个分支的实测值,哪怕 or 首支已真)。"""
    __slots__ = ("_fn", "meta", "_measure", "children")

    def __init__(self, fn, meta, measure, children=()):
        self._fn = fn
        self.meta = meta
        self._measure = measure
        self.children = tuple(children)

    def __call__(self, x):
        return self._fn(x)

    def measure(self, x):
        return self._measure(x)

    def witness(self, x) -> ClauseWitness:
        kids = tuple(c.witness(x) for c in self.children)   # 先递归:全量求值
        m = self.meta or {}
        return ClauseWitness(
            satisfied=bool(self._fn(x)),
            measured=self._measure(x),
            op=m.get("op"), threshold=m.get("threshold"),
            label=m.get("field") or m.get("kind"),
            children=kids,
        )


def attr(name: str, op: str, thr) -> WherePredicate:
    """= At:单实例 e.name op thr。"""
    cmp = _cmp(op)
    return _Pred(lambda e: cmp(getattr(e, name), thr),
                 {"kind": "attr", "field": name, "op": op, "threshold": thr},
                 lambda e: getattr(e, name))


def _lift(f) -> "_Pred":
    """裸 callable → 不透明叶子 _Pred(satisfied-only,无阈值细节)。已是 _Pred 原样返回。"""
    if isinstance(f, _Pred):
        return f
    return _Pred(lambda x: bool(f(x)), {"kind": "opaque"}, lambda x: None)


def all(*fns: WherePredicate) -> WherePredicate:  # noqa: A001
    """= Pattern.all:AND 合取。meta 递归携带子结构(kind='and')。"""
    kids = tuple(_lift(f) for f in fns)
    return _Pred(lambda x: builtins.all(f(x) for f in kids),
                 {"kind": "and", "children": tuple(k.meta for k in kids)},
                 lambda x: None,
                 children=kids)


def any(*fns: WherePredicate) -> WherePredicate:  # noqa: A001
    """= OR 析取(内置 any 的谓词版,与 W.all 对称)。__call__ 短路;
    witness 全量求值(每个分支实测值都算,供调参对照)。"""
    kids = tuple(_lift(f) for f in fns)
    return _Pred(lambda x: builtins.any(f(x) for f in kids),
                 {"kind": "or", "children": tuple(k.meta for k in kids)},
                 lambda x: None,
                 children=kids)


def not_(fn: WherePredicate) -> WherePredicate:
    """逻辑取反。注意 None 语义随内层:attr 对 None 判 False,取反后变 True。"""
    k = _lift(fn)
    return _Pred(lambda x: not k(x),
                 {"kind": "not", "children": (k.meta,)},
                 lambda x: None,
                 children=(k,))


def witness_of(fn, target) -> ClauseWitness:
    """任意 where clause fn → ClauseWitness。_Pred 走递归 witness();
    裸 callable 降级 satisfied-only(无 measured/children)。"""
    if hasattr(fn, "witness"):
        return fn.witness(target)
    return ClauseWitness(satisfied=bool(fn(target)))


def child(key: str, inner: WherePredicate) -> WherePredicate:
    """单 child 委托:inner（任意现有一元谓词,如 W.attr）作用于 event.child(key)。
    outer event 类型：composite Event（实现了 child(name)）。"""
    return _Pred(
        lambda e: inner(e.child(key)),
        {"kind": "child", "key": key, "inner": getattr(inner, "meta", None)},
        lambda e: inner.measure(e.child(key)) if hasattr(inner, "measure") else None,
    )


def children(key: str, agg: WherePredicate) -> WherePredicate:
    """child 组委托:agg(seq 谓词,如自定义 lambda)作用于 event.children(key)。
    outer event 类型:composite Event(实现了 children(name))。

    注:原有 W.distinct/W.any/W.count 已归档(2026-06,docs/legacy/kleene/),
    如需 children 聚合判据请用自定义 lambda 或在 detector 阶段实现。"""
    return _Pred(
        lambda e: agg(e.children(key)),
        {"kind": "children", "key": key, "inner": getattr(agg, "meta", None)},
        lambda e: agg.measure(e.children(key)) if hasattr(agg, "measure") else None,
    )
