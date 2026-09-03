# -*- coding: utf-8 -*-
"""研究底座:解析 scan 20260818T110622 → 重放 bb_v1 → 对齐自检 → 存样本上下文。

产出 repro/samples.pkl:每个 match 一条记录,含
  - 标签: forward_return(r40) / match_fp_counts / json 侧对照值
  - 事件上下文: bo_idx / burst span / confirm(start) / end / outcome / trough / revert
  - win K 线全列(date,o,h,l,c,v),行号即事件 idx(与 scan 同一切窗)
对齐自检:重放侧 match_forward_returns/match_first_passage 与 json 值精确一致。
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import pandas as pd

from path2.dag.engine import analyze as dag_analyze
from path2.eval import match_first_passage, match_forward_returns
from path2_apps.bb_v1.dag_spec import build_pattern
from path2_apps.bb_v1.params import Params
from path2_web.data import slice_window

REPO = Path(__file__).resolve().parents[4]
SCAN_PATH = REPO / "outputs/path2_web/scans/20260818T110622.json"
PKL_DIR = Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls")
OUT_PATH = Path(__file__).resolve().parent / "samples.pkl"
HORIZON = 40
FP_K = 5.0
TRADING_TO_CALENDAR_RATIO = 1.65
HEAD_BUFFER_TRADING_DAYS = 63   # bb_v1.eval_meta: max(63,63,14,20)


def main() -> None:
    scan = json.loads(SCAN_PATH.read_text())
    meta = scan["scan"]
    start_ts = pd.to_datetime(meta["start_date"])
    end_ts = pd.to_datetime(meta["end_date"])
    buf_start = start_ts - pd.Timedelta(
        days=round(HEAD_BUFFER_TRADING_DAYS * TRADING_TO_CALENDAR_RATIO))
    buf_end = end_ts + pd.Timedelta(days=round(HORIZON * TRADING_TO_CALENDAR_RATIO))
    assert str(buf_start.date()) == meta["win_start"], (buf_start, meta["win_start"])
    assert str(buf_end.date()) == meta["win_end"], (buf_end, meta["win_end"])
    params = Params.from_dict(scan["per_pattern"]["bb_v1"]["params_snapshot"])

    rows, n_fr_ok, n_bad = [], 0, 0
    for r in scan["results"]:
        sym = r["symbol"]
        json_matches = {m["match_id"]: m for m in
                        r["per_pattern"]["bb_v1"]["analysis"]["matches"]}
        json_fp = r["per_pattern"]["bb_v1"]["match_fp_counts"]
        df = pd.read_pickle(PKL_DIR / f"{sym}.pkl")
        win = slice_window(df, buf_start, buf_end)
        spec = build_pattern(params)
        res = dag_analyze(spec, win, params)
        lo = int(win["date"].searchsorted(start_ts, "left"))
        hi = int(win["date"].searchsorted(end_ts, "right")) - 1
        sym_fp = {"up": 0, "down": 0, "both": 0, "none": 0}
        for m in res.matches:
            tb = m.node_index["tb"]
            burst = m.node_index["burst"]
            bo_idx = burst.members[-1].end_idx
            confirm = tb.start_idx
            trough = min(range(bo_idx + 1, confirm + 1),
                         key=lambda i: float(win["close"].iat[i]))
            fr = match_forward_returns(m, "tb", win, [HORIZON],
                                       sample_window=(lo, hi))[HORIZON]
            fp = match_first_passage(m, "tb", win, HORIZON, k=FP_K,
                                     sample_window=(lo, hi))
            for k in sym_fp:
                sym_fp[k] += fp[k]
            jm = json_matches[m.match_id]
            fr_ok = fr is not None and abs(fr - jm["forward_return"]) < 1e-12
            n_fr_ok += fr_ok
            n_bad += not fr_ok
            rows.append(dict(
                symbol=sym, match_id=m.match_id,
                bo_idx=bo_idx, burst_start=burst.start_idx, burst_end=burst.end_idx,
                confirm=confirm, end_idx=tb.end_idx, outcome=tb.outcome,
                trough=trough, anchor_bo_id=tb.anchor_bo_id,
                fr=fr, fr_json=jm["forward_return"], fp=fp,
                fr_ok=fr_ok,
                win=win[["date", "open", "high", "low", "close", "volume"]],
            ))
        if sym_fp != json_fp:
            print(f"  FP MISMATCH {sym}: replay={sym_fp} json={json_fp}")
    OUT_PATH.write_bytes(pickle.dumps(rows))
    print(f"symbols={len(scan['results'])} matches={len(rows)} "
          f"fr_aligned={n_fr_ok} bad={n_bad}")
    frs = sorted(r["fr"] for r in rows if r["fr"] is not None)
    print(f"fr median={pd.Series(frs).median():.4f} "
          f"(json stats median={scan['per_pattern']['bb_v1']['stats']['median']:.4f})")


if __name__ == "__main__":
    main()
