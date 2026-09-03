"""scan-oos-bo · bo_only(单纯突破)外推窗扫描,对照 bb_v1 完整链条。

目的:区分「突破信号本身在 2026 外推区失效」还是「bb_v1 的 burst/tb 下游毁了 edge」——
bo_only 是单 BODetector(买点=突破日),若它外推 FP>0.5 而 bb_v1<0.5,说明突破有 edge、
是下游回踩环节失效;若两者都 <0.5,则突破信号本身失效。

head_buffer=250 完整检测(与 bb_v1 外推同口径;bo_only 的 eval_meta 也是 63,同样欠检)。
"""
from __future__ import annotations

import pathlib
import subprocess
import sys
import time

REPO = pathlib.Path(subprocess.check_output(
    ["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO))

from path2_web.scan import run_scan_multi   # noqa: E402   (自行落盘)
from path2_web.serialize import serialize_pattern                    # noqa: E402
from path2_web.discovery import PatternRegistry                      # noqa: E402
from path2_apps.bo_only.dag_spec import build_pattern, eval_meta     # noqa: E402
from path2_apps.bo_only.params import Params                         # noqa: E402


def main() -> None:
    # ===== 参数 =====
    PATTERN_ID = "bo_only"
    DATA_DIR = "/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls"
    OOS_START, OOS_END = "2026-01-01", "2026-08-17"
    LABEL_HORIZON = 40
    PRICE_MIN, PRICE_MAX, VOLUME_MIN = 0.5, 30.0, 10000.0
    WORKERS = 8
    FIRST_PASSAGE_K = 5.0
    HEAD_BUFFER = 250        # 完整检测(bo_only eval_meta=63 欠检,与 bb_v1 外推同口径)
    NOTE = "bo_only 单纯突破外推,head_buffer=250 完整检测;对照 bb_v1"
    OUT_NAME = "oos-bo_only-202601-202608-buf250"
    # ==================

    p = Params.default()
    registry = PatternRegistry()
    module_path = registry.module_path(PATTERN_ID)
    if module_path is None:
        raise SystemExit(f"registry 找不到 {PATTERN_ID}")
    meta = eval_meta(params=p)
    spec_json = serialize_pattern(build_pattern(p))

    scan_ts = time.strftime("%Y%m%dT%H%M%S")
    result = run_scan_multi(
        data_dir=DATA_DIR,
        pattern_specs_json={PATTERN_ID: spec_json},
        module_paths={PATTERN_ID: module_path},
        pattern_ids=[PATTERN_ID],
        end_nodes={PATTERN_ID: meta["end_node"]},
        head_buffer_trading_days=HEAD_BUFFER,
        label_horizon=LABEL_HORIZON,
        start_date=OOS_START, end_date=OOS_END,
        workers=WORKERS, ticker_regex=None, scan_ts=scan_ts,
        pattern_params_dicts={PATTERN_ID: p.to_dict()},
        params_provenance={PATTERN_ID: "oos-bo_only"},
        note=NOTE, name=OUT_NAME,
        price_min=PRICE_MIN, price_max=PRICE_MAX, volume_min=VOLUME_MIN,
        first_passage_enabled=True, first_passage_k=FIRST_PASSAGE_K,
    )
    s = result["scan"]
    print(f"scanned={s['scanned']} hits={s['hits']} errors={s['errors']} -> {OUT_NAME}")


if __name__ == "__main__":
    main()
