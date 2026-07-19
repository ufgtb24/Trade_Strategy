"""W.* —— 节点 where 谓词便利层(一元约束)。小而封闭(奥卡姆,只覆盖业务用到的)。

方向性/区间算子被【类型化边】吸收(结构);容器/标量/存在算子被【节点 where】吸收(一元约束)。
作者写声明时根本看不到旧的 Before/After/Overlaps/Pattern.all。
每个 W.* 返回 WherePredicate: (event_or_seq, ctx) -> bool。
"""
from __future__ import annotations

import builtins
import operator as _op
from typing import Callable

from path2.dag.nodes import WherePredicate

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
    """where 谓词:callable (x, ctx)->bool,额外带 .meta(阈值规则) 与 .measure(x,ctx)(实测值)。
    保持与裸 lambda 完全相同的调用接口,_solve/_reify 零感知。"""
    __slots__ = ("_fn", "meta", "_measure")

    def __init__(self, fn, meta, measure):
        self._fn = fn
        self.meta = meta
        self._measure = measure

    def __call__(self, x, ctx):
        return self._fn(x, ctx)

    def measure(self, x, ctx):
        return self._measure(x, ctx)


def attr(name: str, op: str, thr) -> WherePredicate:
    """= At:单实例 e.name op thr。"""
    cmp = _cmp(op)
    return _Pred(lambda e, ctx: cmp(getattr(e, name), thr),
                 {"kind": "attr", "field": name, "op": op, "threshold": thr},
                 lambda e, ctx: getattr(e, name))


def all(*fns: WherePredicate) -> WherePredicate:  # noqa: A001
    """= Pattern.all:AND 合取。组合子无单一阈值,meta=None,measure 返 None。"""
    return _Pred(lambda x, ctx: builtins.all(f(x, ctx) for f in fns),
                 None, lambda x, ctx: None)


def child(key: str, inner: WherePredicate) -> WherePredicate:
    """单 child 委托:inner（任意现有一元谓词,如 W.attr）作用于 event.child(key)。
    outer event 类型：composite Event（实现了 child(name)）。"""
    return _Pred(
        lambda e, ctx: inner(e.child(key), ctx),
        {"kind": "child", "key": key, "inner": getattr(inner, "meta", None)},
        lambda e, ctx: inner.measure(e.child(key), ctx)
                       if hasattr(inner, "measure") else None,
    )


def mark_refs_other_node(pred: WherePredicate) -> WherePredicate:
    """标注一条 where clause「引用其他 node」(硬伤 C 双落 · 编译期端)。

    不改变判定/measure 语义(纯包一层),只在 .meta 里追加 refs_other_node=True,
    供 UI(PendingIcon)与 diagnose 层(cross_node_pending caveat)静态检测消费,
    使前端能在跨节点 clause 尚未真正 bound 前就诚实降级,而不是等运行期 _TRIPWIRE
    (path2.dag._tripwire)兜底抛错才知道。当前 app 未用(无跨节点 clause),为未来
    spec 预留声明入口。"""
    meta = getattr(pred, "meta", None)
    new_meta = {**(meta or {}), "refs_other_node": True}
    measure = pred.measure if hasattr(pred, "measure") else (lambda x, ctx: None)
    return _Pred(lambda x, ctx: pred(x, ctx), new_meta, measure)


def children(key: str, agg: WherePredicate) -> WherePredicate:
    """child 组委托:agg(seq 谓词,如自定义 lambda)作用于 event.children(key)。
    outer event 类型:composite Event(实现了 children(name))。

    注:原有 W.distinct/W.any/W.count 已归档(2026-06,docs/legacy/kleene/),
    如需 children 聚合判据请用自定义 lambda 或在 detector 阶段实现。"""
    return _Pred(
        lambda e, ctx: agg(e.children(key), ctx),
        {"kind": "children", "key": key, "inner": getattr(agg, "meta", None)},
        lambda e, ctx: agg.measure(e.children(key), ctx)
                       if hasattr(agg, "measure") else None,
    )
