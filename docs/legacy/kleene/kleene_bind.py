"""Archived: Kleene 区间绑定算法(2026-06 归档)。

来源:原 path2/dag/_solve.py。
依赖:Event 基类(path2.core),求解期上下文(ctx, assign)。

算法核心:
  - 段首落外层窗口 [lo, hi]
  - 成员锚段首 span_from_first
  - 整段过 cardinality 下界 + node.where + aggregate_where(可跨 role 读 ctx.bound)
  - yield (seq_tuple, 段尾原始流下标)

本文件依赖 path2/dag/ 的多个内部符号(已删),无法独立运行,仅供算法参考。
"""
from __future__ import annotations
import math
from typing import Iterator, List, Tuple

from path2.core import Event   # 仅允许的 import


def _kleene_shape_ok(kl: KleeneSpec) -> None:
    """只支持「基数下界 + 贪心极大段」。其他形状抛 NotImplementedError(绝不静默给错)。"""
    if not kl.greedy:
        raise NotImplementedError("Kleene 非贪心子集枚举:未支持(需指数枚举/NFA)")
    if kl.max_count != math.inf:
        raise NotImplementedError(
            f"Kleene max_count={kl.max_count}(恰好/上界基数):未支持,只支持基数下界 min_count={kl.min_count}")


def kleene_bind(node: NodeSpec, stream, lo, hi, ctx, assign):
    """从 stream 枚举合法极大段。段首落外层窗口 [lo,hi];成员 e 锚段首 span_from_first;
    整段过基数下界 + node.where + aggregate_where。yield (seq_tuple, 段尾原始流下标)。

    成簇按 start 锚段首,与输入流顺序无关:run() 只保证 end_idx 升序、start_idx 可非单调,
    故先按 (start_idx,end_idx) 排序再单向扫,否则 end-sorted 流会在乱序处误断段、丢成员
    (KleeneSpec 语义本就是「成员对段首的绝对跨度」,与顺序无关)。返回的下标是段内成员的
    最大【原始流下标】:ptr 据此越过整段(保非重叠),且与 ONCE 路径同坐标系。"""
    kl = node.kleene
    _kleene_shape_ok(kl)
    s_lo, s_hi = kl.span_from_first or (0, math.inf)
    ordered = sorted(enumerate(stream), key=lambda it: (it[1].start_idx, it[1].end_idx))
    evs = [ev for _, ev in ordered]
    orig = [oi for oi, _ in ordered]
    n = len(evs)
    i = 0
    while i < n:
        if not (lo <= evs[i].start_idx <= hi):
            i += 1; continue
        first = evs[i]
        seg = [first]; j = i + 1
        while j < n and s_lo <= evs[j].start_idx - first.start_idx <= s_hi:
            seg.append(evs[j]); j += 1
        seg_t = tuple(seg)
        ctx_v = ctx if ctx is None else replace(ctx, bound=_TRIPWIRE)
        if (kl.min_count <= len(seg_t)
                and all(fn(seg_t, ctx_v) for _, fn in node.where)            # node.where 作用于整段(W.first 读串首,与 reify 同口径)
                and all(fn(seg_t, ctx_v) for _, fn in kl.aggregate_where)):
            yield (seg_t, max(orig[i:j]))
        i = j     # 极大段后不回头(贪心,skip_till_next 在 Kleene 上的特化)
