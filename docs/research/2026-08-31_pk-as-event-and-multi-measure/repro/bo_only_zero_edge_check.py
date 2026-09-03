"""skeptic 复核 arch §2.3「地雷」:零边 pattern(bo_only)加第二个孤立 node 后,
match 里会不会出现 node_index 缺 end_node('bo') 的条目 → serialize 崩。
"""
import sys, os, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..')))
import pandas as pd
from path2.atoms.breakout import BODetector
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec
from path2.dag import engine as dag_engine
from path2_web.data import slice_window

KW = dict(total_window=20, min_side_bars=6, min_relative_height=0.2,
          exceed_threshold=0.003, peak_supersede_threshold=0.01,
          vol_baseline_period=63, peak_measure="high")

df = pd.read_pickle("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls/TRON.pkl")
win = slice_window(df, "2024-09-19", "2026-03-08").reset_index(drop=True)

base = PatternSpec(pattern_id="bo_only_like",
                   nodes=(NodeSpec("bo", BODetector(breakout_measure="high", **KW),
                                   render_grid="price"),),
                   edges=())
r0 = dag_engine.analyze(base, win, None)
print(f"[基线 · 单 node 零边] matches={len(r0.matches)} "
      f"node_index keys 样例={sorted(r0.matches[0].node_index) if r0.matches else '—'}")

two = PatternSpec(pattern_id="bo_only_plus_pk",
                  nodes=(NodeSpec("bo", BODetector(breakout_measure="high", **KW),
                                  render_grid="price"),
                         # 第二个孤立 node(模拟 pk):不同 detector 实例 → 不同流
                         NodeSpec("pk_stub", BODetector(breakout_measure="close", **KW))),
                  edges=())
r1 = dag_engine.analyze(two, win, None)
print(f"[加一个孤立 node] matches={len(r1.matches)}")
from collections import Counter
c = Counter(tuple(sorted(m.node_index)) for m in r1.matches)
for k, v in c.items():
    print(f"    node_index={k}: {v} 条")
missing = [m for m in r1.matches if "bo" not in m.node_index]
print(f"    缺 end_node('bo') 的 match: {len(missing)} 条 "
      f"→ serialize 里 m.node_index['bo'] 会 {'KeyError' if missing else '正常'}")
