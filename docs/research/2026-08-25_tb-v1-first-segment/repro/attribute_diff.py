"""regress DIFF 归因:抽样 removed/added 各 5 股,局部重算新机器首段 + gate,解释每条差异来路。

只读脚本,不改生产代码。跑法:
  PYTHONPATH=<repo> python docs/research/2026-08-25_tb-v1-first-segment/repro/attribute_diff.py

注意:打印的是 detected 档 burst(未过 where)——`analyze()` 内部 `res.events` 是各 node 流平铺
去重后的结果(`path2/dag/result.py:70`、`path2/dag/engine.py:159`),在 where 筛选之前;不要把
输出里任意一行直接当成 match,需另与 baseline 的 `leaf_event_id`/`upstream_key` 对齐后才能下结论。
"""
from __future__ import annotations

import json
import pickle
import subprocess
import sys
from pathlib import Path

REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO))

import pandas as pd

from path2_web.data import slice_window
from path2_web.scan import TRADING_TO_CALENDAR_RATIO
from path2_apps.bb_v1.dag_spec import analyze, load_params
from path2.atoms.throwback_v1 import run_first_segment, _revert_max_day_drop
from path2.calc.atr import calculate_tr_median
from path2.calc.measure import measure_at, measure_series


def main() -> None:
    REGRESS = REPO / "outputs/path2_eval/bb_v1_regress_task6.json"
    DATA = Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls")
    N = 5
    r = json.loads(REGRESS.read_text())
    meta = r["meta"]
    print("meta keys:", sorted(meta.keys()))
    # ⚠ leaf_event_id/start_idx/end_idx 在 eval_runner._eval_ticker 里是相对「双端缓冲窗」
    # (buf_start=start-head_buffer, buf_end=end+max(horizons))算的下标,不是 [start,end]
    # 窗内下标——必须复刻同一套缓冲切窗,否则索引对不上(brief 骨架的 slice_window(start,end)
    # 是简化写法,实测证伪,这里按实际口径改)。
    start_ts, end_ts = pd.to_datetime(meta["start"]), pd.to_datetime(meta["end"])
    head_buffer = meta["head_buffer_trading_days"]
    horizons = meta["horizons"]
    buf_start = start_ts - pd.Timedelta(days=round(head_buffer * TRADING_TO_CALENDAR_RATIO))
    buf_end = end_ts + pd.Timedelta(days=round(max(horizons) * TRADING_TO_CALENDAR_RATIO))
    p = load_params()
    tbp = p.tb
    for kind in ("removed", "added"):
        seen: list[str] = []
        for row in r[kind]:
            if row["symbol"] in seen:
                continue
            seen.append(row["symbol"])
            if len(seen) > N:
                break
            df = slice_window(pickle.load(open(DATA / f"{row['symbol']}.pkl", "rb")), buf_start, buf_end)
            res = analyze(df, p)
            bursts = [e for e in res.events if e.node_id == "burst"]
            vol = calculate_tr_median(df['high'], df['low'], df['close'], tbp.vol_window).values
            print(f"== {kind} {row['symbol']} buy_date={row['buy_date']} "
                  f"leaf_event_id={row['leaf_event_id']} upstream_key={row['upstream_key']} ==")
            for b in bursts:
                gates: list = []
                bo = b.end_idx
                gbot = min(measure_at(df, i, tbp.measure) for i in range(b.start_idx, b.end_idx + 1))
                seg = run_first_segment(measure_series(df, tbp.measure).values, df['open'].values, bo, gbot, vol,
                                        max_rise_k=tbp.max_rise_k, stop_confirm_bars=tbp.stop_confirm_bars,
                                        max_span=tbp.max_span, on_gate=gates.append, vol_window=tbp.vol_window,
                                        real_closes=df['close'].values)
                dd = _revert_max_day_drop(df, bo, seg.enter) if seg else None
                print(f"  burst[{b.start_idx},{b.end_idx}] bo={bo} date={df['date'].iat[bo].date()} "
                      f"gbot={gbot:.4f} → {seg} gate={[g.gate_name for g in gates]} max_day_drop={dd}")


if __name__ == "__main__":
    main()
