"""独立复核「随便挪个位置也会被判认出」的底(cost 自写,不读 chance_recognition.py),只看 bb_v1。

判定规则(照 mind.md 第 4.1、4.2 节的文字):用户框对应 bb_v1 的某个 node;
  位置对上 = 该 node 的事件与框有一根以上交叠(点事件 = 种类声明了 is_point 的 bo、pk:落在框内或前后 2 个交易日内;
  只有一个 bo 的 burst 虽然只占一根,仍按区段算、不放宽);
  三档:detected(有该 node 的事件)/ qualified(该事件过了这个 node 的全部 where)/
       matched(该事件进了某次 match;bo 是孤立 node,算作「是某个进了 match 的 burst 的成员」)。
底 = 随机位置、同样宽度的框被判成「认出」的比例(每只股票每种框宽撒 N_BOX 个,只撒在预热期之后)。
另算一个变体 B:点事件的位置改用它声明的最早一根 bar 到末根(pk 的峰 bar 在登记 bar 之前 ≥6 根,
见 path2/atoms/breakout.py PeakEvent;网页护栏的「事件锚点」也是这样取的,path2_web/serialize.py event_anchor)。
只读截到 2025-12-31 的副本;窗口 = 训练段 2021-10-08..2025-12-31。
"""
from __future__ import annotations

import dataclasses
import json
import random
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from chart_workflow.loader import load_bars  # noqa: E402
from path2.dag import diagnose as dag_diagnose  # noqa: E402
from path2.dag.engine import analyze as engine_analyze  # noqa: E402
from path2_apps.bb_v1 import dag_spec as bb  # noqa: E402
from path2_web.data import slice_window  # noqa: E402

SNAP = ROOT / "datasets/pkls_until_20251231"
WIDTHS = (1, 5, 10, 20, 40)
N_BOX = 400
N_STOCKS = 200
WARMUP = 63
TOL = 2


def extent(e, variant):
    """事件在图上的位置区间(含两端)。A:起止根;B:从它声明的最早一根 bar 起。"""
    s, t = e.start_idx, e.end_idx
    if variant == "B":
        for f in dataclasses.fields(e):
            v = getattr(e, f.name)
            if f.name.endswith("_idx") and f.name != "instance_idx" and isinstance(v, int) \
                    and not isinstance(v, bool):
                s = min(s, v)
    if type(e).is_point:          # 点事件(按种类声明 is_point,不按单个实例只占一根)放宽前后 TOL 根
        return s - TOL, t + TOL
    return s, t


def main():
    random.seed(11)
    rng = np.random.default_rng(11)
    syms = sorted(p.stem for p in SNAP.glob("*.pkl"))
    random.shuffle(syms)
    p = bb.load_params()
    spec = bb.build_pattern(p)
    acc: dict = {}
    n = 0
    for sym in syms:
        if n >= N_STOCKS:
            break
        df = load_bars(SNAP, sym, "2025-12-31")
        if len(df) < 1000:
            continue
        n += 1
        win = slice_window(df, "2021-10-08", "2025-12-31")
        nb = len(win)
        res = engine_analyze(spec, win, p)
        diag = dag_diagnose(spec, win, None)
        qualified = set()
        for nid, nd in diag.nodes.items():
            for row in nd.attr:
                if all(bool(w) for w in row.clauses.values()):
                    qualified.add(row.event.instance_id)
        matched = set()
        for m in res.matches:
            for e in m.node_index.values():
                matched.add(e.instance_id)
            for b in getattr(m.node_index.get("burst"), "members", ()):
                matched.add(b.instance_id)
        by_node: dict = {}
        for e in res.events:
            by_node.setdefault(e.node_id, []).append(e)
        for nid in ("bo", "pk", "burst", "tb"):
            for variant in ("A", "B"):
                for level in ("detected", "qualified", "matched"):
                    cov = np.zeros(nb + 1, np.int32)
                    for e in by_node.get(nid, []):
                        if level == "qualified" and e.instance_id not in qualified:
                            continue
                        if level == "matched" and e.instance_id not in matched:
                            continue
                        s, t = extent(e, variant)
                        s, t = max(0, s), min(nb - 1, t)
                        if s <= t:
                            cov[s] += 1
                            cov[t + 1] -= 1
                    covered = np.cumsum(cov[:nb]) > 0
                    pre = np.concatenate([[0], np.cumsum(covered)])
                    for w in WIDTHS:
                        b0 = rng.integers(WARMUP, nb - w + 1, N_BOX)
                        hit = (pre[b0 + w] - pre[b0]) > 0
                        acc.setdefault((nid, variant, level, w), []).append(hit.mean())
    out = {}
    print(f"bb_v1 随便挪位置被判「认出」的比例(每只股票的比例取均值,{n} 只,每只每种框宽 {N_BOX} 个随机框)")
    for nid in ("bo", "pk", "burst", "tb"):
        for variant in ("A", "B"):
            for level in ("detected", "qualified", "matched"):
                xs = [statistics.mean(acc[(nid, variant, level, w)]) for w in WIDTHS]
                out[f"{nid}|{variant}|{level}"] = dict(zip(map(str, WIDTHS), xs))
                print(f"  {nid:5s} {variant} {level:9s} " +
                      "  ".join(f"宽{w:2d} {x:5.1%}" for w, x in zip(WIDTHS, xs)))
    (HERE / "out_chance_base_bb_v1.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
