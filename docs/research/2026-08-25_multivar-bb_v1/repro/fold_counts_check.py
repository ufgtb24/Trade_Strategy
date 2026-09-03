"""参照格 × FINAL / B where 的年折 count:长表谓词聚合 vs 当前代码 run_scan_multi 新扫(同 HEAD_BUFFER=250)。"""
import json, subprocess, sys, time
from pathlib import Path
import pandas as pd
REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO))
from path2_web.scan import run_scan_multi
from path2_web.serialize import serialize_pattern
from path2_web.discovery import PatternRegistry


def main():
    BASE = json.loads((REPO / "docs/research/2026-08-25_multivar-bb_v1/ref_params.json").read_text())
    WHERES = {"FINAL": dict(first_drought_min=20, distinct_pk_min=4, vol_spike_min=15, peak_age_min=0),
              "B": dict(first_drought_min=20, distinct_pk_min=3, vol_spike_min=10, peak_age_min=0)}
    LT = REPO / "docs/research/2026-08-25_multivar-bb_v1/longtable"
    df = pd.concat([pd.read_parquet(p) for p in sorted(LT.glob("part-*.parquet"))], ignore_index=True)
    ref = (df["bo.min_relative_height"] == 0.2) & (df["bo.exceed_threshold"] == 0.003) & (df["burst.gap_max"] == 8) \
        & (df["tb.stop_confirm_bars"] == 2) & (df["tb.big_rise_k"] == 5.0) & (df["burst.count"] >= 1) & (df["tb.day_drop"] < 0.2)
    reg = PatternRegistry(); mod = reg.get("bb_v1")
    for name, w in WHERES.items():
        m = ref & (df["burst.first_drought"] >= w["first_drought_min"]) & (df["burst.distinct_pk"] >= w["distinct_pk_min"]) \
            & (df["burst.max_bar_vol_ratio"] >= w["vol_spike_min"]) & (df["burst.peak_age_max"] >= w["peak_age_min"])
        lt_counts = df[m].groupby("fold_Y").size().to_dict()
        snap = json.loads(json.dumps(BASE)); snap["burst"].update(w); snap["tb"]["max_day_drop_pct"] = 0.2
        p = mod.Params.from_dict(snap, strict=True)
        out = run_scan_multi(data_dir=str(REPO / "datasets/pkls"), pattern_specs_json={"bb_v1": serialize_pattern(mod.build_pattern(p))},
                             module_paths={"bb_v1": reg.module_path("bb_v1")}, pattern_ids=["bb_v1"], end_nodes={"bb_v1": "tb"},
                             head_buffer_trading_days=250, label_horizon=40, start_date="2024-01-01", end_date="2026-01-01",
                             workers=8, ticker_regex=None, scan_ts=time.strftime("%Y%m%dT%H%M%S"), pattern_params_dicts={"bb_v1": p.to_dict()},
                             name=f"foldcheck-{name}", price_min=0.5, price_max=30.0, volume_min=10000.0,
                             first_passage_enabled=True, first_passage_k=5.0, outputs_root=str(REPO / "outputs/path2_web"))
        sc = {}
        for r in out["results"]:
            pr = (r.get("per_pattern") or {}).get("bb_v1")
            for mm in (pr["analysis"]["matches"] if pr else []):
                sc[mm["buy_date"][:4]] = sc.get(mm["buy_date"][:4], 0) + 1
        print(name, "长表", lt_counts, "新扫", sc, "研究§5.3 参考", {"FINAL": "73/92", "B": "164/172"}[name])
        assert lt_counts == sc, f"{name} fold 计数不一致"


main()
