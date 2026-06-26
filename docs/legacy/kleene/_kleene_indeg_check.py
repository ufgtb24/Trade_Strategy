"""Archived: Kleene 入边 satisfies 校验(2026-06 归档)。

来源:原 path2/dag/_solve.py。
依赖 endpoint(),归档代码不可独立运行,仅供算法参考。
"""
from path2.core import Event   # 仅允许的 import
# from path2.dag._solve import endpoint  # 已删,引用保留供算法参考


def _kleene_indeg_ok(ps, assign, seq):
    """Kleene 节点作 dst:入边 satisfies 对段首 seq[0](窗口已筛段首)。"""
    return all(edge.satisfies(endpoint(assign[u], edge), seq[0]) for u, edge in ps)
