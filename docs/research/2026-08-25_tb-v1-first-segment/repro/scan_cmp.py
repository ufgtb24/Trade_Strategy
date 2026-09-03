"""tb_v1 首段状态机重构 · 对比扫描(改前基线 / 改后各 max_span 档 / bo_only 参照)。

一次运行 = CONFIGS 里每个 (pattern, overrides, window) 组合各做一次全宇宙 scan,落盘
outputs/path2_web/scans/<out_name>.json(per_pattern.stats = match 数/fr 分布,
per_pattern.first_passage_stats = 首穿四态计数 + 随机日基线,供 summarize.py 汇总)。
口径固定:head_buffer=250(完整检测,训练/外推同口径)· label 40 · first_passage k=5 ·
price 0.5-30 / vol≥10000(与既往 scan 一致)。窗按 CONFIGS 指定(训练窗 / 外推窗分开扫)。

用法:改 main() 顶部 CONFIGS 后
  PYTHONPATH=<repo> python docs/research/2026-08-25_tb-v1-first-segment/repro/scan_cmp.py
"""
from __future__ import annotations

import importlib
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO))

from path2_web.scan import run_scan_multi            # noqa: E402
from path2_web.serialize import serialize_pattern    # noqa: E402
from path2_web.discovery import PatternRegistry      # noqa: E402

TRAIN = ("2024-01-01", "2026-01-01")
OOS = ("2026-01-01", "2026-08-25")


def main() -> None:
    # ===== 参数(在此处直接改,无 argparse) =====
    # 每项:pattern_id / out_name / overrides(空=params.yaml 现值)/ window
    CONFIGS = [
        dict(pattern_id="bb_v1", out_name="cmp-new-v1-span12-train", overrides={"tb": {"max_span": 12}}, window=TRAIN),
        dict(pattern_id="bb_v1", out_name="cmp-new-v1-span12-oos",   overrides={"tb": {"max_span": 12}}, window=OOS),
        dict(pattern_id="bb_v1", out_name="cmp-new-v1-span20-train", overrides={"tb": {"max_span": 20}}, window=TRAIN),
        dict(pattern_id="bb_v1", out_name="cmp-new-v1-span20-oos",   overrides={"tb": {"max_span": 20}}, window=OOS),
        dict(pattern_id="bb_v1", out_name="cmp-new-v1-span60-train", overrides={"tb": {"max_span": 60}}, window=TRAIN),
        dict(pattern_id="bb_v1", out_name="cmp-new-v1-span60-oos",   overrides={"tb": {"max_span": 60}}, window=OOS),
    ]
    DATA_DIR = "/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls"
    HEAD_BUFFER = 250
    LABEL_HORIZON = 40
    PRICE_MIN, PRICE_MAX, VOLUME_MIN = 0.5, 30.0, 10000.0
    WORKERS = 24
    FIRST_PASSAGE_K = 5.0
    TICKER_REGEX = None                        # 小样本验证用,如 r"^(AAA|AACB)\.pkl$"
    NOTE = "tb_v1 首段状态机重构对比扫描(2026-08-25)"
    # =====================================

    registry = PatternRegistry()
    for cfg in CONFIGS:
        pid = cfg["pattern_id"]
        module_path = registry.module_path(pid)
        if module_path is None:
            raise SystemExit(f"registry 找不到 {pid}")
        mod = importlib.import_module(module_path)
        p = mod.load_params()
        if cfg["overrides"]:
            d = p.to_dict()
            for sec, kv in cfg["overrides"].items():
                d[sec].update(kv)
            p = type(p).from_dict(d)
        end_node = mod.eval_meta(params=p)["end_node"]
        spec_json = serialize_pattern(mod.build_pattern(p))
        start, end = cfg["window"]

        t0 = time.time()
        result = run_scan_multi(
            data_dir=DATA_DIR,
            pattern_specs_json={pid: spec_json},
            module_paths={pid: module_path},
            pattern_ids=[pid],
            end_nodes={pid: end_node},
            head_buffer_trading_days=HEAD_BUFFER,
            label_horizon=LABEL_HORIZON,
            start_date=start, end_date=end,
            workers=WORKERS, ticker_regex=TICKER_REGEX, scan_ts=time.strftime("%Y%m%dT%H%M%S"),
            pattern_params_dicts={pid: p.to_dict()},
            params_provenance={pid: "scan_cmp"},
            note=NOTE, name=cfg["out_name"],
            price_min=PRICE_MIN, price_max=PRICE_MAX, volume_min=VOLUME_MIN,
            first_passage_enabled=True, first_passage_k=FIRST_PASSAGE_K,
        )
        s = result["scan"]
        print(f"{cfg['out_name']}: window={start}..{end} scanned={s['scanned']} hits={s['hits']} "
              f"errors={s['errors']} in {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
