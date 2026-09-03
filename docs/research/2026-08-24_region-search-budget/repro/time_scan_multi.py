"""真跑 run_scan_multi(进程池)计时:与单进程分段和对照,量进程池固定开销。

用法:改 main() 起始参数,`uv run python docs/research/2026-08-24_region-search-budget/repro/time_scan_multi.py`
产物 scan JSON 落 repro/_scans/(不污染 outputs/)。
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import time

REPO = pathlib.Path(subprocess.check_output(
    ["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO))

from path2_web.scan import run_scan_multi  # noqa: E402
from path2_web.serialize import serialize_pattern  # noqa: E402
from path2_web.discovery import PatternRegistry  # noqa: E402
from path2_apps.bb_v1.dag_spec import build_pattern, eval_meta  # noqa: E402
from path2_apps.bb_v1.params import Params  # noqa: E402


def main(TICKER_REGEX="^A[A-C]", WORKERS=8) -> None:
    # ===== 参数 =====
    PATTERN_ID = "bb_v1"
    DATA_DIR = "/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls"
    START_DATE, END_DATE = "2024-01-01", "2026-01-01"
    LABEL_HORIZON, FP_K, HEAD_BUFFER = 40, 5.0, 250
    PRICE_MIN, PRICE_MAX, VOLUME_MIN = 0.5, 30.0, 10000.0
    REF_SCAN = REPO / "outputs/path2_web/scans/20260818T223413.json"
    WIDE_OVERRIDES = dict(burst=dict(first_drought_min=0, distinct_pk_min=1, vol_spike_min=0),
                          tb=dict(max_day_drop_pct=None))
    OUT_ROOT = str(pathlib.Path(__file__).parent / "_scans")
    # ==================
    snap = json.loads(REF_SCAN.read_text())["per_pattern"][PATTERN_ID]["params_snapshot"]
    for s2, kv in WIDE_OVERRIDES.items():
        snap[s2].update(kv)
    p = Params.from_dict(snap)
    meta = eval_meta(params=p)
    reg = PatternRegistry()
    t0 = time.perf_counter()
    result = run_scan_multi(
        data_dir=DATA_DIR,
        pattern_specs_json={PATTERN_ID: serialize_pattern(build_pattern(p))},
        module_paths={PATTERN_ID: reg.module_path(PATTERN_ID)},
        pattern_ids=[PATTERN_ID],
        end_nodes={PATTERN_ID: meta["end_node"]},
        head_buffer_trading_days=HEAD_BUFFER, label_horizon=LABEL_HORIZON,
        start_date=START_DATE, end_date=END_DATE,
        workers=WORKERS, ticker_regex=TICKER_REGEX,
        scan_ts=time.strftime("%Y%m%dT%H%M%S"),
        pattern_params_dicts={PATTERN_ID: p.to_dict()},
        name=f"timing-{TICKER_REGEX.strip('^')}-w{WORKERS}",
        price_min=PRICE_MIN, price_max=PRICE_MAX, volume_min=VOLUME_MIN,
        first_passage_enabled=True, first_passage_k=FP_K,
        outputs_root=OUT_ROOT,
    )
    wall = time.perf_counter() - t0
    s = result["scan"]
    pp = result["per_pattern"][PATTERN_ID]
    print(f"regex={TICKER_REGEX} workers={WORKERS} scanned={s['scanned']} hits={s['hits']} "
          f"errors={s['errors']} n_match={pp['stats']['count']} FP={pp['first_passage_stats'].get('ratio')} "
          f"wall={wall:.1f}s  per-stock-wall={wall/s['scanned']*1000:.0f}ms  "
          f"cpu-equiv={wall*WORKERS/s['scanned']*1000:.0f}ms/stock")


if __name__ == "__main__":
    main()
