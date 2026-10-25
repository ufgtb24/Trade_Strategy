"""PROTOTYPE 取数：给「结构化标注」原型导出几只股票的 K 线 + 事件。

只读截到 2025-12-31 的副本；挑 bb_v1 在 2023~2025 有 match 的股票，
每只取 match 前后一段窗口，导出 bb_v1 的事件 / match / pattern 声明，
外加 平台段、走势区段 两种 atom 的事件（演示「按种类分轨」）。
输出 prototypes/01-annotation/data.js（window.PROTO_DATA = {...}），双击 HTML 即可读。
"""
import json
import random
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from chart_workflow.loader import load_bars  # noqa: E402
from path2_web.data import slice_window  # noqa: E402
from path2_web.serialize import serialize_analysis, serialize_pattern, _event_to_dict  # noqa: E402
from path2_apps.bb_v1 import dag_spec as bb  # noqa: E402
from path2.atoms.platform import PlatformDetector  # noqa: E402
from path2.atoms.trend import TrendSegmentDetector  # noqa: E402

SNAP = ROOT / "datasets/pkls_until_20251231"
OUT = ROOT / ".scratch/annotation-path2/prototypes/01-annotation/data.js"
N_PICK = 4
WIN_BEFORE, WIN_AFTER = 160, 60


def main():
    random.seed(7)
    syms = sorted(p.stem for p in SNAP.glob("*.pkl"))
    random.shuffle(syms)
    params = bb.load_params()
    spec = serialize_pattern(bb.build_pattern(params))
    picked = []
    for sym in syms:
        if len(picked) >= N_PICK:
            break
        try:
            df = load_bars(SNAP, sym, "2025-12-31")
        except Exception:
            continue
        if len(df) < 400 or df["close"].iloc[-1] > 60 or df["close"].iloc[-1] < 1:
            continue
        full = slice_window(df, "2021-10-08", "2025-12-31")
        res = bb.analyze(full, params)
        ms = [m for m in res.matches if full["date"].iloc[m.end_idx] >= pd.Timestamp("2023-06-01")]
        if not ms:
            continue
        m = ms[0]
        lo = max(0, m.start_idx - WIN_BEFORE)
        hi = min(len(full) - 1, m.end_idx + WIN_AFTER)
        win = full.iloc[lo:hi + 1].reset_index(drop=True)
        res_w = bb.analyze(win, params)
        ana = serialize_analysis(res_w)
        extra = []
        for kind, det in (("platform", PlatformDetector()), ("trend", TrendSegmentDetector())):
            for e in det.detect(win):
                d = _event_to_dict(e)
                d["kind"] = kind
                d["instance_id"] = f"{kind}_{d['start_idx']}"
                extra.append(d)
        bars = [{"date": str(r.date.date()), "o": r.open, "h": r.high, "l": r.low,
                 "c": r.close, "v": r.volume} for r in win.itertuples()]
        picked.append({"symbol": sym, "bars": bars, "analysis": ana, "atoms": extra})
        print(sym, len(bars), "matches", len(ana["matches"]), "events", len(ana["events"]), "atoms", len(extra))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {"pattern_spec": spec, "stocks": picked,
               "snapshot": json.loads((SNAP / "SNAPSHOT.json").read_text())["created_at"]}
    OUT.write_text("window.PROTO_DATA = " + json.dumps(payload, default=str) + ";\n")
    print("wrote", OUT, OUT.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
