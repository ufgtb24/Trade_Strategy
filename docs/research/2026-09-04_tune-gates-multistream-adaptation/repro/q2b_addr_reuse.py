# -*- coding: utf-8 -*-
"""Q2-C:地址回收实测——build_pattern 的 detector 地址是否跨 spec 复用。
跨 combo 的 stream_cache 若把 id(detector) 写进键,复用即"不同 node 的 detector 撞同一键"。"""
import sys
from pathlib import Path
REPO = Path("/home/yu/PycharmProjects/Trade_Strategy")
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / ".claude/skills/tune-gates"))
import study_io as S
study = S.load_study(S.APPS_DIR / "bb_v1" / "study.py")
mod = S.import_app(study)
base = S.base_snapshot(mod, study)
P = lambda: mod.Params.from_dict(base, strict=True)

def ids_of(spec):
    return {n.node_id: id(n.detector) for n in spec.nodes if n.detector is not None}

snaps = []
for i in range(6):
    spec = mod.build_pattern(P())
    snaps.append(ids_of(spec))
    del spec                       # 与 scan_one_stock 每 combo 重新绑定 spec 等价
for i, s in enumerate(snaps):
    print(i, {k: hex(v) for k, v in s.items()})
# 跨 spec 的地址是否复用,以及复用时挂在哪个 node 上
addr_to_nodes = {}
for i, s in enumerate(snaps):
    for nid, a in s.items():
        addr_to_nodes.setdefault(a, []).append((i, nid))
reused = {hex(a): v for a, v in addr_to_nodes.items() if len({n for _, n in v}) > 1}
print("\n跨 spec 复用同一地址、且挂到不同 node 的:", reused if reused else "本次运行未出现")
print("跨 spec 复用同一地址(含同 node)的条目数:",
      sum(1 for v in addr_to_nodes.values() if len({i for i, _ in v}) > 1), "/", len(addr_to_nodes))
