"""票 02 验收：读 scan 的 skill 脚本在新 scan 上能读出 hits（只读；输出只有计数与身份校验，不含收益数字）。
用法（worktree 根目录）：.venv/bin/python <本文件> <scan 文件> <临时目录>
  feature-study：build_dataset 跑两道自检门（hit 集对齐、label 对齐），门不过会 raise。
  tune-gates：compare_longtable 的 _engine_keys 读 serialize 输出的 analysis.hits 与 hit_fp_counts，并与 scan 文件的 hit_id 对照。
  diagnose-event：diagnose_env 对这份 scan 做环境探测。
行情只经 scan 记录的 dataset_dir（训练段副本）或 path2_web.data.read_bars 读。"""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
SCAN, TMP = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
blob = json.loads(SCAN.read_text())
meta = blob["scan"]
PID = "bb_v1"
assert meta["dataset_dir"].endswith("datasets/pkls_until_20251231"), meta["dataset_dir"]
n_scan = sum(len(r["per_pattern"][PID]["analysis"]["hits"]) for r in blob["results"])
print("scan 文件 hit 数", n_scan, "有 hit 的股票数", meta["hit_stocks"])


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---- feature-study
sys.path.insert(0, str(ROOT / ".claude/skills/feature-study"))
ex = load("fs_extract", ROOT / ".claude/skills/feature-study/extract.py")
adapter = ex.load_adapter(PID)
df = ex.build_dataset(adapter, scan=SCAN, out_csv=TMP / "t02_dataset.csv",
                      compute_features=lambda win, row: {})
print("feature-study build_dataset：两道自检门通过；去重后行数", len(df))

# ---- tune-gates
import pandas as pd  # noqa: E402
from path2.dag.engine import analyze  # noqa: E402
from path2_web.data import read_bars, slice_window  # noqa: E402
from path2_web.serialize import serialize_per_pattern_result  # noqa: E402
from path2_apps.bb_v1 import dag_spec as app  # noqa: E402
cl = load("tg_cl", ROOT / ".claude/skills/tune-gates/compare_longtable.py")
p = app.Params.from_dict(blob["per_pattern"][PID]["params_snapshot"])
spec = app.build_pattern(p)
s, e = pd.to_datetime(meta["start_date"]), pd.to_datetime(meta["end_date"])
total = 0
for r in blob["results"]:
    win = slice_window(read_bars(meta["dataset_dir"], r["symbol"]), meta["win_start"], meta["win_end"])
    lo = int(win["date"].searchsorted(s, "left")); hi = int(win["date"].searchsorted(e, "right")) - 1
    res = analyze(spec, win, p)
    f = meta["filters"]
    out = serialize_per_pattern_result(res, end_node=blob["per_pattern"][PID]["end_node"], label_horizon=meta["label_horizon"],
                                       win=win, start_ts=s, end_ts=e, price_min=f["price_min"], price_max=f["price_max"],
                                       first_passage_k=meta["first_passage_k"], sample_window=(lo, hi))
    keys = cl._engine_keys(res.hits, out["analysis"]["hits"], ("burst", "tb"))
    in_scan = {h["hit_id"] for h in r["per_pattern"][PID]["analysis"]["hits"]}
    assert {h["hit_id"] for h in out["analysis"]["hits"]} == in_scan, r["symbol"]
    assert out["hit_fp_counts"] == r["per_pattern"][PID]["hit_fp_counts"], r["symbol"]
    assert len(keys) == len(in_scan), r["symbol"]
    total += len(keys)
print("tune-gates _engine_keys：读出", total, "条 hit，hit_id 集合与 hit_fp_counts 都和 scan 文件一致")

# ---- diagnose-event
sys.path.insert(0, str(ROOT / ".claude/skills/diagnose-event"))
env = load("de_env", ROOT / ".claude/skills/diagnose-event/path2_diag_env.py")
first = blob["results"][0]["per_pattern"][PID]["analysis"]["hits"][0]
inst = first["leaf"]
d = env.diagnose_env(blob["results"][0]["symbol"], inst, scan_path=str(SCAN))
print("diagnose-event diagnose_env：探测到 pattern", d["pattern"], "；返回字段", sorted(d)[:12])
