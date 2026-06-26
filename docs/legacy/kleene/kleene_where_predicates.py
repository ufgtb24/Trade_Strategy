"""Archived: Kleene seq 谓词工厂(2026-06 归档)。

这 6 个工厂(W.first / W.last / W.count / W.any / W.distinct / W.reduce)只对 Kleene 整段
(tuple[Event, ...])有意义。归档后 dag/ 内所有 where 谓词只作用于单 Event。

来源:原 path2/dag/where.py。
依赖 _Pred / _cmp(已删除已归档的属于 where.py 内部辅助,本归档代码引用保留为字面)。
归档代码不可独立运行,仅供算法参考。
"""
from __future__ import annotations
import builtins
import operator as _op
from typing import Callable, Any

from path2.core import Event   # 仅允许的 import


def first(name: str, op: str, thr) -> object:
    """Kleene 串首属性(③ drought)。"""
    cmp = _cmp(op)
    return _Pred(lambda seq, ctx: cmp(getattr(seq[0], name), thr),
                 {"kind": "first", "field": name, "op": op, "threshold": thr},
                 lambda seq, ctx: getattr(seq[0], name))


def last(name: str, op: str, thr) -> object:
    """Kleene 串尾属性。"""
    cmp = _cmp(op)
    return _Pred(lambda seq, ctx: cmp(getattr(seq[-1], name), thr),
                 {"kind": "last", "field": name, "op": op, "threshold": thr},
                 lambda seq, ctx: getattr(seq[-1], name))


def count(op: str, thr) -> object:
    """② Kleene 基数:len(seq) op thr。"""
    cmp = _cmp(op)
    return _Pred(lambda seq, ctx: cmp(len(seq), thr),
                 {"kind": "count", "field": None, "op": op, "threshold": thr},
                 lambda seq, ctx: len(seq))


def any(name: str, op: str, thr) -> object:  # noqa: A001
    """⑥ 存在量化:∃ e∈seq, e.name op thr。measure 取满足者中最贴合的代表值
    (op 为 >=/>: 满足者的 max;<=/<: 满足者的 min;==/!=: 第一个满足者;无满足者: None)。"""
    cmp = _cmp(op)

    def fn(seq, ctx):
        return builtins.any(cmp(getattr(e, name), thr) for e in seq)

    def measure(seq, ctx):
        ok = [getattr(e, name) for e in seq if cmp(getattr(e, name), thr)]
        if not ok:
            return None
        if op in (">=", ">"):
            return max(ok)
        if op in ("<=", "<"):
            return min(ok)
        return ok[0]

    return _Pred(fn, {"kind": "any", "field": name, "op": op, "threshold": thr}, measure)


def distinct(name: str, op: str, thr) -> object:
    """⑤ 跨序列 distinct 计数(name 为 tuple 字段时 flatten,如 broken_peak_ids)。"""
    cmp = _cmp(op)

    def _acc(seq):
        acc = set()
        for e in seq:
            v = getattr(e, name)
            if isinstance(v, (tuple, list, set)):
                acc.update(v)
            else:
                acc.add(v)
        return acc

    return _Pred(lambda seq, ctx: cmp(len(_acc(seq)), thr),
                 {"kind": "distinct", "field": name, "op": op, "threshold": thr},
                 lambda seq, ctx: len(_acc(seq)))


def reduce(name: str, fn: Callable, op: str, thr) -> object:
    """= Over:fn([e.name for e in seq]) op thr。"""
    cmp = _cmp(op)
    return _Pred(lambda seq, ctx: cmp(fn([getattr(e, name) for e in seq]), thr),
                 {"kind": "reduce", "field": name, "op": op, "threshold": thr},
                 lambda seq, ctx: fn([getattr(e, name) for e in seq]))
