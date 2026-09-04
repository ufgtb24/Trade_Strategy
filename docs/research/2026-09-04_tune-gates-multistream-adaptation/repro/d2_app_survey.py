# -*- coding: utf-8 -*-
"""D2:全部现役 app 的多流兄弟组普查——兄弟流是否 bound(进 compile_plan 求解集)/是否被别的 node consumes。"""
import sys, importlib
from pathlib import Path
REPO = Path("/home/yu/PycharmProjects/Trade_Strategy")
sys.path.insert(0, str(REPO))
from path2.dag._solve import compile_plan
from path2.core import stream_schema

APPS = ["bottom_burst", "bb_v1", "bb_v3", "bb_v0", "bo_only", "bb_pk", "try_conplex_where"]
for app in APPS:
    try:
        mod = importlib.import_module(f"path2_apps.{app}.dag_spec")
        spec = mod.build_pattern(mod.Params.default())
    except Exception as ex:
        print(f"== {app}: 构建失败 {type(ex).__name__}: {ex}")
        continue
    groups = {}
    for n in spec.nodes:
        if n.detector is not None:
            groups.setdefault((id(n.detector), n.consumes_stream), []).append(n)
    bound = {nid for w in compile_plan(spec).wcc_plans for nid in w.comp}
    consumed = {n.consumes_stream for n in spec.nodes if n.consumes_stream is not None}
    children_targets = {c for n in spec.nodes for c in n.children.values()}
    multi = {k: v for k, v in groups.items() if len(v) > 1}
    print(f"== {app}: nodes={[n.node_id for n in spec.nodes]}")
    print(f"   bound(求解集)={sorted(bound)} · 被 consumes 的流={sorted(consumed)} · children 指向={sorted(children_targets)}")
    if not multi:
        print("   多流/别名兄弟组: 无")
    for k, v in multi.items():
        for n in v:
            print(f"   兄弟组 {[x.node_id for x in v]} | node={n.node_id} produces={n.produces_stream!r} "
                  f"solve={n.solve} bound={n.node_id in bound} 被consumes={n.node_id in consumed} "
                  f"被children引用={n.node_id in children_targets} "
                  f"detector声明流={sorted(stream_schema(n.detector), key=lambda s:(s is None,s))}")
