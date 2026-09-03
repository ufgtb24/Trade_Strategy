"""scan-wide · 宽进重扫做调参底座(tune-gates 第 2 步)。

对指定 pattern 用「筛子层(事后可切参数)放机制下限、生成侧(必须真扫参数)保持」的
宽进参数,在给定训练窗上全宇宙扫描,产出带全量 match + label 的 scan 文件,作为
逐闸事后切档的宽底座(后续用 feature-study/extract_skeleton 从本 scan 提取 dataset.csv)。

宽进 override 的语义见 tune-gates SKILL.md 第 2 步:
  - 事后可切参数(纯 where 字段 / 只影响「产不产事件」不改几何)放机制下限,
    让完整取值空间进池——事后切档零成本、与真扫等价;
  - 必须真扫参数(参与切串/物化或改变几何)保持参照快照机制值——审计走逐档真扫。

参数全部在 main() 起始声明(无 argparse,承 CLAUDE.md 入口规范)。

用法:
    uv run python scripts/path2/scan-wide.py
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
    DATA_DIR = "/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls"   # 主目录 pkl(worktree 内为空)
    START_DATE, END_DATE = "2024-01-01", "2026-01-01"                     # 训练窗(跨 regime 两年)
    LABEL_HORIZON = 40                                                    # 与参照 scan 一致
    PRICE_MIN, PRICE_MAX, VOLUME_MIN = 0.5, 30.0, 10000.0                 # 与参照 scan 一致
    WORKERS = 8
    FIRST_PASSAGE_ENABLED = True
    FIRST_PASSAGE_K = 5.0
    NOTE = "宽进底座 head_buffer=250 完整检测(守 skill 红线:训练与外推同口径);窗 2024-01..2026-01"
    OUT_NAME = "scan-wide-bb_v1-202401-202601-buf250"
    # 参照 scan:读其 params_snapshot 作当前值基底,只 override 下列事后可切参数
    REF_SCAN = REPO / "outputs/path2_web/scans/20260818T223413.json"
    # 宽进 override(事后可切 → 机制下限;必须真扫保持参照快照机制值):
    #   burst.first_drought_min 40→0 / distinct_pk_min 3→1 / vol_spike_min 10→0
    #   tb.max_day_drop_pct 0.2→None
    OVERRIDES = dict(burst=dict(first_drought_min=0, distinct_pk_min=1, vol_spike_min=0),
                     tb=dict(max_day_drop_pct=None))
    # head_buffer override:250 完整检测(外推同口径;eval_meta=63 欠检,drought/peak 积累受限)
    HEAD_BUFFER = 250
    # 小样本验证用(全量时置 None):正则限定 pkl 文件名,如 r"^(AAA|AACB)\.pkl$"
    TICKER_REGEX = None
    # =====================================

    blob = json.loads(REF_SCAN.read_text())
    snap = blob["per_pattern"][PATTERN_ID]["params_snapshot"]
    for sec, kv in OVERRIDES.items():
        snap[sec].update(kv)
    p = Params.from_dict(snap)

    registry = PatternRegistry()
    module_path = registry.module_path(PATTERN_ID)
    if module_path is None:
        raise SystemExit(f"registry 找不到 {PATTERN_ID}")

    meta = eval_meta(params=p)
    end_node = meta["end_node"]
    head_buffer = HEAD_BUFFER   # 250 完整检测(override eval_meta=63)
    spec_json = serialize_pattern(build_pattern(p))

    scan_ts = time.strftime("%Y%m%dT%H%M%S")
    result = run_scan_multi(
        data_dir=DATA_DIR,
        pattern_specs_json={PATTERN_ID: spec_json},
        module_paths={PATTERN_ID: module_path},
        pattern_ids=[PATTERN_ID],
        end_nodes={PATTERN_ID: end_node},
        head_buffer_trading_days=head_buffer,
        label_horizon=LABEL_HORIZON,
        start_date=START_DATE, end_date=END_DATE,
        workers=WORKERS, ticker_regex=TICKER_REGEX, scan_ts=scan_ts,
        pattern_params_dicts={PATTERN_ID: p.to_dict()},
        params_provenance={PATTERN_ID: "wide-base"},
        note=NOTE, name=OUT_NAME,
        price_min=PRICE_MIN, price_max=PRICE_MAX, volume_min=VOLUME_MIN,
        first_passage_enabled=FIRST_PASSAGE_ENABLED, first_passage_k=FIRST_PASSAGE_K,
    )
    s = result["scan"]
    print(f"scanned={s['scanned']} hits={s['hits']} errors={s['errors']}")
    print(f"落盘: {REPO / 'outputs' / 'path2_web' / 'scans' / f'{OUT_NAME}.json'}")


if __name__ == "__main__":
    main()
