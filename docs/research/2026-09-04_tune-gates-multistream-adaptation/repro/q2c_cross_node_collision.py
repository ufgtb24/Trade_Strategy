# -*- coding: utf-8 -*-
"""Q2-C':合成拓扑上把「跨 combo 的 id 键撞到别的 node」真跑出来。
合成 app:两个 BurstDetector 实例(bA/bB)都 consumes_stream='bo' —— 同 consumes、
同 size class,正是 (id(det), consumes) 这个键唯一能区分它们的场景。"""
import sys
from pathlib import Path
REPO = Path("/home/yu/PycharmProjects/Trade_Strategy")
sys.path.insert(0, str(REPO))
from path2.atoms.breakout import BurstDetector

class FakeSpecNodes(list):
    pass

def build(gap):
    """模拟 build_pattern:每次造全新的一组 detector(与真 app 逐字同构)。"""
    a = BurstDetector(min_bos=1, gap_max=gap)
    b = BurstDetector(min_bos=1, gap_max=gap + 1)
    return [("bA", a, "bo"), ("bB", b, "bo")]

seen = {}          # (id, consumes) -> (combo_i, node_id)
collisions = []
for i in range(200):
    nodes = build(4 + (i % 3))
    for nid, det, cons in nodes:
        k = (id(det), cons)
        if k in seen and seen[k][1] != nid:
            collisions.append((seen[k], (i, nid), hex(k[0])))
        seen[k] = (i, nid)
    del nodes      # 与 scan_one_stock 每 combo 丢弃上一份 spec 等价
print("跨 combo 的 (id(det), consumes) 键撞到不同 node 的次数:", len(collisions))
for c in collisions[:8]:
    print("   combo", c[0][0], c[0][1], "→ combo", c[1][0], c[1][1], "同址", c[2])
