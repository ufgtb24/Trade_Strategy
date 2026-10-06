"""未触线比例随期限 H 的变化（v3 收盘口径，k=5）；fold2 搜索段 256 只股票，数据裁到 2025-06-30（已登记开发范围）。"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / ".claude/skills/tune-gates-v3/scripts"))
from daily import _daily_close_labels  # noqa
DATA = ROOT / "docs/research/2026-10-02_v3-bb-training-calibration"
PKL = Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls")
pool = pd.read_parquet(DATA / "fold2_search_baseline.parquet")
base = pd.read_parquet(DATA / "fold2_search_candidates.parquet").query("candidate_id=='base'")
out = {}
frames = {}
for sym in sorted(pool.symbol.unique()):
    raw = pd.read_pickle(PKL / f"{sym}.pkl")
    d = pd.DatetimeIndex(pd.to_datetime(raw["date"] if "date" in raw else raw.index)).normalize()
    keep = (d >= "2024-01-01") & (d <= "2025-06-30")
    f = raw.loc[keep].copy().reset_index(drop=True); f["date"] = d[keep]
    frames[sym] = f
for H in (10, 20, 40):
    labs = pd.concat([_daily_close_labels(f, s, pd.Timestamp("2024-07-01"), pd.Timestamp("2025-03-31"), H, 5.0)
                      for s, f in frames.items()], ignore_index=True)
    labs["dir"] = labs.up - labs.down
    b = labs.merge(base[["symbol", "date"]], on=["symbol", "date"])
    resolved = labs.up + labs.down
    out[H] = {"pool_rows": len(labs), "pool_none": float(labs.none.mean()), "pool_dir": float(labs.dir.mean()),
              "pool_q_resolved": float(labs.up.sum() / resolved.sum()),
              "base_rows": len(b), "base_none": float(b.none.mean()), "base_dir": float(b.dir.mean()),
              "base_q_resolved": float(b.up.sum() / max(1, (b.up + b.down).sum()))}
Path(__file__).with_name("horizon_none_results.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
