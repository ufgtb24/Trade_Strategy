# -*- coding: utf-8 -*-
"""组内标注顺序是否可观测:把别名组的声明序倒过来(bo2 在前),看引擎给事件的 node_id。
若可观测,则工具遍历兄弟组必须用「声明序」,用拓扑序/字典序都会静默偏离引擎。"""
import sys
from pathlib import Path
REPO = Path("/home/yu/PycharmProjects/Trade_Strategy")
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / ".claude/skills/tune-gates"))
import pandas as pd, study_io as S
from path2 import config
from path2.atoms.breakout import BODetector
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec
from path2.dag.engine import run_streams
from path2_web.data import slice_window
from path2_web.scan import _list_pkls
config.set_runtime_checks(True)
study = S.load_study(S.APPS_DIR / "bb_v1" / "study.py"); mod = S.import_app(study)
p = mod.Params.from_dict(S.base_snapshot(mod, study), strict=True)
win = slice_window(pd.read_pickle(next(iter(_list_pkls(str(REPO / "datasets/pkls"), r"^AAPL")))), "2023-01-01", "2026-03-01")
for order_desc, first, second in (("声明序 bo 在前", "bo", "bo2"), ("声明序 bo2 在前", "bo2", "bo")):
    det = BODetector(**p.bo_kwargs())
    nodes = (NodeSpec(first, det, produces_stream="bo", solve=False),
             NodeSpec(second, det, produces_stream="bo", solve=False),
             NodeSpec("pk", det, produces_stream="pk", solve=False))
    st = run_streams(PatternSpec(pattern_id="ord", nodes=nodes, edges=()), win)
    e0 = st["bo"][0]
    print(f"  {order_desc}: 事件 node_id={e0.node_id!r} instance_id={e0.instance_id!r}")
