"""硬伤 C 兜底 · 跨节点 clause 未 bound 时不静默 fallback,抛显式错。

与 stdlib fn.meta.refs_other_node 双落:
- refs_other_node(编译期标注): UI 提前诚实降级(小图标)
- _TRIPWIRE(运行期兜底): 防未来 spec 静默产错值

与 `_solve.py` 内已有的同名私有 `_TripWire`(候选预过滤阶段用)同源同构,
本模块是它的可共享、可导出版本(Task 8 后端要捕获 `CrossNodePendingError`)。
diagnose 层(`diagnose.py`)复用本模块;`_solve.py` 的私有版本不动 —— 求解核心
之外的模块随意改。
"""

class CrossNodePendingError(Exception):
    """跨节点 clause 访问未 bound 的 sibling node · 应走 caveats 通道诚实降级。"""
    pass


class _TripWire:
    """sentinel · 任何操作都抛 CrossNodePendingError。"""
    __slots__ = ()

    def __repr__(self):
        return "<_TRIPWIRE>"

    def _raise(self, *_args, **_kwargs):
        raise CrossNodePendingError(
            "跨节点 clause 访问 sibling node 但 sibling 尚未 bind · "
            "spec 应显式声明 refs_other_node · 或将该 clause 延后到 pair 复核阶段"
        )

    # 所有运算都指向 _raise
    __add__ = __sub__ = __mul__ = __truediv__ = _raise
    __lt__ = __le__ = __gt__ = __ge__ = __eq__ = _raise
    __getattr__ = _raise
    __getitem__ = _raise
    __call__ = _raise
    __bool__ = _raise


_TRIPWIRE = _TripWire()
