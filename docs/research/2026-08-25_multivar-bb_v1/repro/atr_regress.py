"""ATR 修复回归脚本:子集 scan 修复前后 match 集 + forward_return 逐项相同。
用法:改 main() 顶部 MODE 后 `uv run python docs/research/2026-08-25_multivar-bb_v1/repro/atr_regress.py`
  before  → 修复前跑,落 outputs/path2_web/scans/atr-regress-before.json
  after   → 修复后跑,落 outputs/path2_web/scans/atr-regress-after.json
  compare → 比对两文件
"""
import json, subprocess, sys, time
from pathlib import Path

REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO))


def _scan(name: str, *, pid: str, start_date: str, end_date: str, ticker_regex: str,
         workers: int, head_buffer_trading_days: int, label_horizon: int,
         first_passage_enabled: bool, first_passage_k: float,
         price_min: float, price_max: float, volume_min: float, note: str) -> None:
    from path2_web.scan import run_scan_multi
    from path2_web.serialize import serialize_pattern
    from path2_web.discovery import PatternRegistry
    reg = PatternRegistry()
    mod = reg.get(pid)
    snap = json.loads((REPO / "docs/research/2026-08-25_multivar-bb_v1/ref_params.json").read_text())
    p = mod.Params.from_dict(snap, strict=True)          # 宽进底座(where 已在机制下限)
    t0 = time.time()
    run_scan_multi(
        data_dir=str(REPO / "datasets/pkls"),
        pattern_specs_json={pid: serialize_pattern(mod.build_pattern(p))},
        module_paths={pid: reg.module_path(pid)}, pattern_ids=[pid],
        end_nodes={pid: mod.eval_meta(params=p)["end_node"]},
        head_buffer_trading_days=head_buffer_trading_days, label_horizon=label_horizon,
        start_date=start_date, end_date=end_date,
        workers=workers, ticker_regex=ticker_regex, scan_ts=time.strftime("%Y%m%dT%H%M%S"),
        pattern_params_dicts={pid: p.to_dict()}, params_provenance={pid: "atr-regress"},
        note=note, name=name,
        price_min=price_min, price_max=price_max, volume_min=volume_min,
        first_passage_enabled=first_passage_enabled, first_passage_k=first_passage_k,
        outputs_root=str(REPO / "outputs/path2_web"),
    )
    print(f"{name}: {time.time() - t0:.1f}s")


def _key_set(path: Path) -> dict:
    d = json.loads(path.read_text())
    out = {}
    for r in d["results"]:
        pr = (r.get("per_pattern") or {}).get("bb_v1")
        if not pr:
            continue
        for m in pr["analysis"]["matches"]:
            out[(r["symbol"], m["match_id"])] = m["forward_return"]
    return out


def main() -> None:
    MODE = "before"                       # before | after | compare
    PID = "bb_v1"
    START_DATE = "2024-01-01"
    END_DATE = "2026-01-01"
    TICKER_REGEX = r"^A[A-F]"
    WORKERS = 8
    HEAD_BUFFER_TRADING_DAYS = 250
    LABEL_HORIZON = 40
    FIRST_PASSAGE_ENABLED = True
    FIRST_PASSAGE_K = 5.0
    PRICE_MIN = 0.5
    PRICE_MAX = 30.0
    VOLUME_MIN = 10000.0
    NOTE = "ATR 修复回归"

    scans = REPO / "outputs/path2_web/scans"
    if MODE in ("before", "after"):
        _scan(f"atr-regress-{MODE}", pid=PID, start_date=START_DATE, end_date=END_DATE,
             ticker_regex=TICKER_REGEX, workers=WORKERS,
             head_buffer_trading_days=HEAD_BUFFER_TRADING_DAYS, label_horizon=LABEL_HORIZON,
             first_passage_enabled=FIRST_PASSAGE_ENABLED, first_passage_k=FIRST_PASSAGE_K,
             price_min=PRICE_MIN, price_max=PRICE_MAX, volume_min=VOLUME_MIN, note=NOTE)
        return
    a, b = _key_set(scans / "atr-regress-before.json"), _key_set(scans / "atr-regress-after.json")
    assert a, "before 集为空:先跑 MODE=before/after 采集数据再 compare"
    assert set(a) == set(b), f"match 集不同: 仅前 {len(set(a) - set(b))} / 仅后 {len(set(b) - set(a))}"
    bad = [k for k in a if not ((a[k] is None and b[k] is None) or
                                (a[k] is not None and b[k] is not None and abs(a[k] - b[k]) < 1e-12))]
    assert not bad, f"forward_return 不等: {bad[:5]}"
    print(f"OK: {len(a)} match 逐项相同")


main()
