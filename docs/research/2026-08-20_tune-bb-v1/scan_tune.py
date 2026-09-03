"""scan-tune · 必须真扫参数 OAT 真扫(tune-gates 第 4 步「必须真扫参数」)。

对指定必须真扫参数围绕当前值定档位,每档一次全宇宙 scan
(训练窗 [2024-01,2026-01],head_buffer=250 完整检测),汇总每档 (match, fr_median, FP)
供判定。真扫档位间是「换池」(match 非子集关系),判定靠 match 条带 + 分年一致性
(见 tune-gates SKILL.md 第 4 步)。

基线:事后可切参数放宽(250 完整检测下全池 FP 最高,收紧降 FP),只动目标参数
(其他生成侧保持参照快照)。目标参数当前值档 = 宽进底座 scan-wide-buf250 已扫过,可复用。

用法:改 main() 起始参数(无 argparse):
    uv run python docs/research/2026-08-20_tune-bb-v1/scan_tune.py
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

from path2_web.scan import run_scan_multi   # noqa: E402
from path2_web.serialize import serialize_pattern                    # noqa: E402
from path2_web.discovery import PatternRegistry                      # noqa: E402
from path2_apps.bb_v1.dag_spec import build_pattern, eval_meta       # noqa: E402
from path2_apps.bb_v1.params import Params                           # noqa: E402


def main() -> None:
    # ===== 参数 =====
    PATTERN_ID = "bb_v1"
    DATA_DIR = "/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls"
    START_DATE, END_DATE = "2024-01-01", "2026-01-01"    # 训练窗
    LABEL_HORIZON = 40
    PRICE_MIN, PRICE_MAX, VOLUME_MIN = 0.5, 30.0, 10000.0
    WORKERS = 8
    FIRST_PASSAGE_K = 5.0
    HEAD_BUFFER = 250                                    # 完整检测
    REF_SCAN = REPO / "outputs/path2_web/scans/20260818T223413.json"
    # 事后可切放宽基线(250 完整检测下全池最优)
    WIDE_OVERRIDES = dict(burst=dict(first_drought_min=0, distinct_pk_min=1, vol_spike_min=0),
                          tb=dict(max_day_drop_pct=None))
    # 目标必须真扫参数:[(section, field, 档位)],每档一次全宇宙 scan
    # 档位含当前值(该档 = 宽进底座已扫过,可复用不重扫)
    TARGETS = [
        ("tb", "stop_confirm_bars", [0, 1, 2, 3]),
        ("bo", "min_relative_height", [0.1, 0.15, 0.2, 0.3]),
        ("bo", "exceed_threshold", [0.001, 0.003, 0.01, 0.03]),
        ("burst", "gap_max", [4, 8, 12, 20]),
        ("burst", "min_bos", [1, 2, 3, 4]),
        ("tb", "big_rise_k", [3, 5, 8, 12]),
    ]
    TICKER_REGEX = None   # 全量;小样本验证时填子集正则(对 p.stem 匹配,不带 .pkl)
    # ==================

    blob = json.loads(REF_SCAN.read_text())
    registry = PatternRegistry()
    module_path = registry.module_path(PATTERN_ID)
    if module_path is None:
        raise SystemExit(f"registry 找不到 {PATTERN_ID}")

    for sec, field, levels in TARGETS:
        for lv in levels:
            snap = json.loads(json.dumps(blob["per_pattern"][PATTERN_ID]["params_snapshot"]))
            for s2, kv in WIDE_OVERRIDES.items():
                snap[s2].update(kv)
            snap[sec][field] = lv    # override 目标参数
            p = Params.from_dict(snap)
            meta = eval_meta(params=p)
            spec_json = serialize_pattern(build_pattern(p))
            tag = f"{sec}.{field}={lv}"
            out_name = f"tune-{sec}-{field}-{lv}-buf250"
            scan_ts = time.strftime("%Y%m%dT%H%M%S")
            result = run_scan_multi(
                data_dir=DATA_DIR,
                pattern_specs_json={PATTERN_ID: spec_json},
                module_paths={PATTERN_ID: module_path},
                pattern_ids=[PATTERN_ID],
                end_nodes={PATTERN_ID: meta["end_node"]},
                head_buffer_trading_days=HEAD_BUFFER,
                label_horizon=LABEL_HORIZON,
                start_date=START_DATE, end_date=END_DATE,
                workers=WORKERS, ticker_regex=TICKER_REGEX, scan_ts=scan_ts,
                pattern_params_dicts={PATTERN_ID: p.to_dict()},
                params_provenance={PATTERN_ID: f"tune-{tag}"},
                note=f"OAT 真扫 {tag}", name=out_name,
                price_min=PRICE_MIN, price_max=PRICE_MAX, volume_min=VOLUME_MIN,
                first_passage_enabled=True, first_passage_k=FIRST_PASSAGE_K,
            )
            s = result["scan"]
            pp = result["per_pattern"][PATTERN_ID]
            fps = pp["first_passage_stats"]
            fp = fps["ratio"]
            fr = pp["stats"]["median"]
            n = pp["stats"]["count"]
            fr_s = f"{fr:.4f}" if fr is not None else "  --  "
            fp_s = f"{fp:.4f}" if fp is not None else "  --  "
            print(f"[{tag}] scanned={s['scanned']} hits={s['hits']} errors={s['errors']}"
                  f"  n={n} fr_med={fr_s} FP={fp_s} -> {out_name}")


if __name__ == "__main__":
    main()
