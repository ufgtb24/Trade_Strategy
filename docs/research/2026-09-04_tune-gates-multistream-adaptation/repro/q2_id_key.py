# -*- coding: utf-8 -*-
"""Q2:草案 4.1 把 id(detector) 放进「跨 combo 的 stream_cache 键」是否成立。

三问:
  A. 每个 combo 的 build_pattern 是否造新 detector 实例(id 变)?
  B. 草案伪代码(siblings 由 spec0 算、gkey 由 per-combo node 算)会怎样?
  C. 若按 per-combo 重算 siblings 修好 A,跨 combo 的 stream_cache 键还安全吗
     (旧 spec 被丢弃后地址回收 → 不同 node 的 detector 撞同一 id)?
"""
import sys, gc
from pathlib import Path
REPO = Path("/home/yu/PycharmProjects/Trade_Strategy")
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / ".claude/skills/tune-gates"))
import study_io as S
from multivar_core import classify, influence_dims, apply_overrides, detection_combos

study = S.load_study(S.APPS_DIR / "bb_v1" / "study.py")
mod = S.import_app(study)
base = S.base_snapshot(mod, study)
cls = classify(mod, base, study.SCAN_GRID, study.WHERE_LEVELS)
spec0 = mod.build_pattern(mod.Params.from_dict(base, strict=True))
infl = influence_dims(spec0, cls, study.SCAN_GRID)

siblings = {}
for n in spec0.nodes:
    if n.detector is not None:
        siblings.setdefault((id(n.detector), n.consumes_stream), []).append(n)
infl_group = {k: tuple(sorted(set().union(*(set(infl[s.node_id]) for s in g))))
              for k, g in siblings.items()}
print("A. spec0 组键:", [(hex(k[0]), k[1]) for k in siblings])

combos = detection_combos(study.SCAN_GRID, cls)
print("   combo 数:", len(combos))

# --- B. 草案伪代码逐字复刻(只跑分组/取键,不真 detect) ---
err = None
for i, combo in enumerate(combos[:2]):
    p = mod.Params.from_dict(apply_overrides(base, {}, combo), strict=True)
    spec = mod.build_pattern(p)
    by_id = {n.node_id: n for n in spec.nodes}
    print(f"   combo{i} 组键:", [(hex(id(n.detector)), n.consumes_stream) for n in spec.nodes if n.detector is not None])
    try:
        node = by_id["bo"]
        gkey = (id(node.detector), node.consumes_stream)
        ckey = (gkey, tuple(combo[d] for d in infl_group[gkey]))
    except KeyError as e:
        err = e
        print(f"   ★ combo{i} 取 infl_group[gkey] → KeyError {e}")
        break
print("B. 草案伪代码结果:", "KeyError(每个 combo 必炸)" if err else "未复现")

# --- C. 地址回收:跨 combo 保留 id 键,看是否出现「不同 node 的 detector 撞同一 id」 ---
seen = {}     # (id, consumes) -> set of node_id
collide = []
for i, combo in enumerate(combos):
    p = mod.Params.from_dict(apply_overrides(base, {}, combo), strict=True)
    spec = mod.build_pattern(p)
    for n in spec.nodes:
        if n.detector is None:
            continue
        k = (id(n.detector), n.consumes_stream)
        prev = seen.setdefault(k, set())
        if prev and n.node_id not in prev:
            collide.append((i, k, sorted(prev), n.node_id))
        prev.add(n.node_id)
    del spec, p       # 丢弃本 combo 的 spec(与 scan_one_stock 循环内重新绑定等价)
print("C. 跨 combo 同 (id,consumes) 键被不同 node 复用的次数:", len(collide))
for c in collide[:6]:
    print("    ", c[0], hex(c[1][0]), c[1][1], c[2], "→", c[3])
print("   不同 combo 之间键复用情况(键 → 出现它的 node 集):",
      {(hex(k[0]), k[1]): sorted(v) for k, v in list(seen.items())[:8]})
