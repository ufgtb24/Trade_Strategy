"""方案 D 可行性验证:把 bo/pk 拆成两个独立 BODetector 实例,PatternSpec 还能不能构造。
只读实验,不改仓库代码。"""
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec
from path2.atoms.breakout import BODetector

det1, det2 = BODetector(), BODetector()

print("--- 形态 1:两实例、各只认领一条流(最朴素的拆法) ---")
try:
    PatternSpec(pattern_id="d1", nodes=(
        NodeSpec("bo", det1, produces_stream="bo", render_grid="price"),
        NodeSpec("pk", det2, produces_stream="pk", solve=False, render_grid="price"),
    ), edges=())
    print("构造成功")
except Exception as e:
    print(f"{type(e).__name__}: {e}")

print("\n--- 形态 2:两实例、各认领两条流(4 node,补齐 C3) ---")
try:
    s = PatternSpec(pattern_id="d2", nodes=(
        NodeSpec("bo", det1, produces_stream="bo", render_grid="price"),
        NodeSpec("pk1", det1, produces_stream="pk", solve=False, render_grid="price"),
        NodeSpec("bo2", det2, produces_stream="bo", solve=False, render_grid="price"),
        NodeSpec("pk", det2, produces_stream="pk", solve=False, render_grid="price"),
    ), edges=())
    print("构造成功;node 数 =", len(s.nodes))
except Exception as e:
    print(f"{type(e).__name__}: {e}")
