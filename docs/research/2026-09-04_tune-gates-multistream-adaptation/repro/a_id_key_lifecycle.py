"""草案 4.1 的 `gkey = (id(node.detector), node.consumes_stream)` 在跨 combo 的轴上是否成立。
siblings/infl_group 建自 spec0,而循环里的 node 来自每个 combo 新建的 spec。只读实验。"""
import gc
from path2_apps.bb_v1 import dag_spec as APP

base = APP.Params.default().to_dict()
spec0 = APP.build_pattern(APP.Params.from_dict(base, strict=True))

siblings = {}
for n in spec0.nodes:
    if n.detector is not None:
        siblings.setdefault((id(n.detector), n.consumes_stream), []).append(n.node_id)
print("spec0 分组键:", {k: v for k, v in siblings.items()})

print("\n模拟 detection_combos 逐轮 build_pattern:")
for lvl in (0.1, 0.2, 0.3):
    d = {**base, "bo": {**base["bo"], "min_relative_height": lvl}}
    spec = APP.build_pattern(APP.Params.from_dict(d, strict=True))
    node = {n.node_id: n for n in spec.nodes}["bo"]
    gkey = (id(node.detector), node.consumes_stream)
    print(f"  combo bo.min_relative_height={lvl}: gkey={gkey} 命中 spec0 分组? {gkey in siblings}"
          f"  -> 草案里的 infl_group[gkey] 会 {'正常' if gkey in siblings else 'KeyError'}")

print("\nid 回收演示(为什么就算绕过 KeyError 也危险):")
seen = set()
collided = 0
for lvl in [0.1 + 0.001 * i for i in range(200)]:
    d = {**base, "bo": {**base["bo"], "min_relative_height": lvl}}
    spec = APP.build_pattern(APP.Params.from_dict(d, strict=True))
    i = id({n.node_id: n for n in spec.nodes}["bo"].detector)
    if i in seen:
        collided += 1
    seen.add(i)
    del spec
    gc.collect()
print(f"  200 轮里 id(detector) 与此前某轮重复的次数: {collided}"
      f"  (每轮 spec 被回收后 id 可复用;缓存键含 id 时这就是脏读入口)")
