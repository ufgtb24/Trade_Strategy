# tests/path2/dag/test_shared_stream_fuzz.py
"""1c 别名安全 fuzz:差分「共享流 ≡ 分离等价流」。

原理:Task 7 令两个 NodeSpec 共享同一 detector 时 run_streams 只实例化一次 stream
list 并让两个 node_id 同时指向它(streams[X] is streams[Y])。本 fuzz 验证 _solve 在
此别名场景下与「各持等价独立副本」(is not)产生完全相同的输出 keyset。

两种 solver 模式全覆盖:
  - solve(pruned)  — collapse=False(默认), memo_mode="charitable"(默认,生产默认)
  - solve(noprune) — collapse=False, memo_mode="off"   (差分无剪枝)

ONCE 节点 × 4 边类型(Temporal/Containment/Overlap/Equals)
"""
import random

from tests.path2.dag._oracle import E, keyset
from path2.dag.edges import TemporalEdge, ContainmentEdge, OverlapEdge, EqualsEdge
from path2.dag._solve import compile_plan, solve
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec


def _rand_segs(n, smax, rng):
    """生成 n 个随机线段 [(start, end), ...],已排序。"""
    out = []
    for _ in range(n):
        s = rng.randint(0, smax)
        out.append((s, rng.randint(s, smax)))
    return sorted(out)


def _ks_all(spec, streams):
    """两种 solver 模式的 keyset 元组(剪枝/不剪枝)。"""
    plan = compile_plan(spec)
    return (
        keyset(solve(plan, streams)),                              # pruned(生产默认)
        keyset(solve(plan, streams, collapse=False, memo_mode="off")),  # noprune
    )


def _assert_alias_safe(spec, segs, z_segs, label):
    """核心差分断言:共享流(X is Y)与分离等价流(X is not Y)的 solver 输出须完全一致。"""
    shared = E("S", segs)
    # 共享:X 与 Y 绑同一 list 对象(模拟 Task 7 的 dedup 共享)
    st_shared = {"X": shared, "Y": shared, "Z": E("Z", z_segs)}
    # 分离:X 与 Y 各持等价独立副本(内容相同但 is not)
    st_sep = {"X": E("S", segs), "Y": E("S", segs), "Z": E("Z", z_segs)}

    # 设置守护:确保真的在测共享 vs 分离,而非两者相同对象
    assert st_shared["X"] is st_shared["Y"], "setup guard: shared streams must be same object"
    assert st_sep["X"] is not st_sep["Y"], "setup guard: separated streams must be distinct objects"

    ks_shared = _ks_all(spec, st_shared)
    ks_sep = _ks_all(spec, st_sep)
    assert ks_shared == ks_sep, (
        f"{label} 别名不安全:共享流与分离等价流 solver 输出不一致\n"
        f"  segs={segs}  z_segs={z_segs}\n"
        f"  shared={ks_shared}\n"
        f"  sep={ks_sep}"
    )


def test_alias_safe_once_nodes():
    """X, Y(ONCE)共享同一源流,各连边到公共 dst Z;共享 vs 分离须一致。
    4 边类型 × 2000 随机种子。"""
    rng = random.Random(13)
    for _ in range(2000):
        segs = _rand_segs(rng.randint(1, 3), 8, rng)
        z_segs = _rand_segs(rng.randint(1, 3), 8, rng)
        kind = rng.choice([TemporalEdge, ContainmentEdge, OverlapEdge, EqualsEdge])

        if kind is TemporalEdge:
            edges = [
                TemporalEdge("X", "Z", min_gap=rng.choice([0, 1]), max_gap=rng.choice([5, 100])),
                TemporalEdge("Y", "Z", min_gap=0, max_gap=100),
            ]
        else:
            edges = [kind("X", "Z"), kind("Y", "Z")]

        nodes = tuple(NodeSpec(node_id=n, detector=None) for n in ["X", "Y", "Z"])
        spec = PatternSpec(
            pattern_id="t",
            nodes=nodes, edges=tuple(edges),
        )
        _assert_alias_safe(spec, segs, z_segs, kind.__name__)
