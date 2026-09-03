"""scan-oos · 外推窗多配置对比扫描(第 5 步 holdout 外推验证)。

对同一外推窗 [OOS_START, OOS_END] 扫 A/B/FINAL 三个配置,落盘三个 scan,
供外推对比(tune-gates 回放校验的跨窗版;判据预注册见「结论与台账.md」)。

⚠ label 现实约束:label_horizon=40 交易日后向缓冲,数据只到 OOS_END(2026-08-17),
故外推窗末尾 ~40 交易日的 match 无 label(forward_return=None)——有效评估区间约
[OOS_START, OOS_END - 40 交易日]。对比时只统计 label 非 None 的 match。

参数在 main() 起始声明(无 argparse,承 CLAUDE.md 入口规范):
    uv run python docs/research/2026-08-20_tune-bb-v1/scan_oos.py
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

from path2_web.scan import run_scan_multi   # noqa: E402   (自行落盘 outputs/path2_web/scans/)
from path2_web.serialize import serialize_pattern                    # noqa: E402
from path2_web.discovery import PatternRegistry                      # noqa: E402
from path2_apps.bb_v1.dag_spec import build_pattern, eval_meta       # noqa: E402
from path2_apps.bb_v1.params import Params                           # noqa: E402


def main() -> None:
    # ===== 参数(在此处直接改,无 argparse) =====
    PATTERN_ID = "bb_v1"
    DATA_DIR = "/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls"   # 主目录 pkl
    OOS_START, OOS_END = "2026-01-01", "2026-08-17"                     # 外推窗(全窗外)
    LABEL_HORIZON = 40
    PRICE_MIN, PRICE_MAX, VOLUME_MIN = 0.5, 30.0, 10000.0
    WORKERS = 8
    FIRST_PASSAGE_K = 5.0
    REF_SCAN = REPO / "outputs/path2_web/scans/20260818T223413.json"   # 参照快照(A 配置基底)
    # 前缓冲验证:正常 = eval_meta(63 交易日,覆盖所有 lookback);加大 = 250 交易日,
    # 检验「2026-01 无事件是否因前缓冲不足」(理论:BODetector lookback=max(vol_baseline63, peak滑窗20)=63,
    # 63 已够——若加大仍无 01 事件则坐实市场原因)
    HEAD_BUFFER = 250
    # 外推对比三配置(override 相对参照快照 fd40+毒药0.2+dpk3+vsp10+pa0):
    #   A      = 参照原值(旧当前配置)
    #   B      = fd 40→20(主配置,纯减法)
    #   FINAL  = fd20 + dpk4 + vsp15(外推对照)
    CONFIGS = {
        "A":     dict(burst=dict(),                                 tb=dict()),
        "B":     dict(burst=dict(first_drought_min=20),             tb=dict()),
        "FINAL": dict(burst=dict(first_drought_min=20, distinct_pk_min=4, vol_spike_min=15),
                      tb=dict()),
    }   # 完整检测外推:三个配置都 HEAD_BUFFER=250 重跑,对比完整外推区表现
    # =====================================

    blob = json.loads(REF_SCAN.read_text())
    registry = PatternRegistry()
    module_path = registry.module_path(PATTERN_ID)
    if module_path is None:
        raise SystemExit(f"registry 找不到 {PATTERN_ID}")

    for name, overrides in CONFIGS.items():
        snap = json.loads(json.dumps(blob["per_pattern"][PATTERN_ID]["params_snapshot"]))
        for sec, kv in overrides.items():
            snap[sec].update(kv)
        p = Params.from_dict(snap)
        meta = eval_meta(params=p)
        spec_json = serialize_pattern(build_pattern(p))
        out_name = f"oos-{name}-bb_v1-202601-202608-buf{HEAD_BUFFER}"
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
            params_provenance={PATTERN_ID: f"oos-{name}"},
            note=f"外推窗 {OOS_START}..{OOS_END} 配置 {name}", name=out_name,
            price_min=PRICE_MIN, price_max=PRICE_MAX, volume_min=VOLUME_MIN,
            first_passage_enabled=True, first_passage_k=FIRST_PASSAGE_K,
        )
        s = result["scan"]
        print(f"[{name}] scanned={s['scanned']} hits={s['hits']} errors={s['errors']} -> {out_name}")


if __name__ == "__main__":
    main()
