"""同股同 span 多 tb 的双计规模:现 serialize 按 instance_id 去重(同 span 多实例 #idx 不同 → 各计一次),
若改为按物理 span 去重,FP 差多少。宽进底座、^A 768 股、窗内 + 价格过滤口径同 serialize_per_pattern_result。
用法:`uv run python docs/research/2026-08-24_region-search-budget/repro/span_dupe_fp.py`
"""
from __future__ import annotations
import json, pathlib, subprocess, sys
from collections import Counter, defaultdict
REPO = pathlib.Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(pathlib.Path(__file__).parent))
import pandas as pd
from path2 import config
from path2.dag.engine import analyze
from path2.eval import match_first_passage, _resolve_end_events
from path2.atoms import throwback_v1 as tbm
from path2_web.data import slice_window
from path2_web.scan import _list_pkls, TRADING_TO_CALENDAR_RATIO
from path2_apps.bb_v1.dag_spec import build_pattern
from path2_apps.bb_v1.params import Params
from microbench import atr_numpy


def main(TICKER_REGEX="^A"):
    DATA_DIR = "/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls"
    START_DATE, END_DATE = "2024-01-01", "2026-01-01"
    HEAD_BUFFER, H, FPK, PRICE_MIN, PRICE_MAX, VOLUME_MIN = 250, 40, 5.0, 0.5, 30.0, 10000.0
    config.set_runtime_checks(True)
    snap = json.loads((REPO / "outputs/path2_web/scans/20260818T223413.json").read_text())["per_pattern"]["bb_v1"]["params_snapshot"]
    snap["burst"].update(first_drought_min=0, distinct_pk_min=1, vol_spike_min=0); snap["tb"]["max_day_drop_pct"] = None
    p = Params.from_dict(snap); spec = build_pattern(p)
    start_ts, end_ts = pd.to_datetime(START_DATE), pd.to_datetime(END_DATE)
    buf_start = str((start_ts - pd.Timedelta(days=round(HEAD_BUFFER * TRADING_TO_CALENDAR_RATIO))).date())
    buf_end = str((end_ts + pd.Timedelta(days=round(H * TRADING_TO_CALENDAR_RATIO))).date())
    atr_cache = {}
    def _atr_at(df, idx, period):
        # 缓存持 df 引用防 id 复用(df 被回收后新 df 可能拿到同一 id → 读到过期 ATR)
        ent = atr_cache.get(period)
        if ent is None or ent[0] is not df:
            ent = atr_cache[period] = (df, atr_numpy(df["high"], df["low"], df["close"], period))
        v = float(ent[1][idx]); return v if v == v else 0.0
    tbm._atr_at = _atr_at
    fp_match = Counter(); fp_span = Counter(); n_match = n_span = n_dup_match = n_stock = 0
    dup_groups = Counter(); id_dupe = 0
    for pk in _list_pkls(DATA_DIR, TICKER_REGEX):
        w = slice_window(pd.read_pickle(pk), buf_start, buf_end)
        if len(w) == 0: continue
        sw = w[(w["date"] >= start_ts) & (w["date"] <= end_ts)]
        if len(sw) == 0 or sw["volume"].mean() <= VOLUME_MIN: continue
        n_stock += 1
        lo = int(w["date"].searchsorted(start_ts, "left")); hi = int(w["date"].searchsorted(end_ts, "right")) - 1
        res = analyze(spec, w, p)
        by_span = defaultdict(list); ids = set()
        for m in res.matches:
            evs = _resolve_end_events(m, "tb")
            if not any(start_ts <= w["date"].iat[e.start_idx] <= end_ts for e in evs): continue
            if not any(PRICE_MIN <= w["close"].iat[e.start_idx] <= PRICE_MAX for e in evs): continue
            tb = m.node_index["tb"]
            if tb.instance_id in ids: id_dupe += 1
            ids.add(tb.instance_id)
            fp = match_first_passage(m, "tb", w, H, FPK, sample_window=(lo, hi))
            by_span[(tb.start_idx, tb.end_idx)].append(fp)
        for span, fps in by_span.items():
            n_span += 1; n_match += len(fps)
            if len(fps) > 1: n_dup_match += len(fps); dup_groups[len(fps)] += 1
            for f in fps: fp_match.update(f)
            fp_span.update(fps[0])
    def ratio(c): d = c["up"] + c["down"] + c["both"]; return c["up"] / d if d else float("nan")
    print(f"stocks={n_stock} matches(窗内)={n_match} unique spans={n_span} 属于同 span 多 tb 组的 match={n_dup_match} ({n_dup_match/max(1,n_match):.1%}); "
          f"组大小分布={dict(dup_groups)}; instance_id 重复={id_dupe}")
    print(f"按 match 计(现状): {dict(fp_match)} FP={ratio(fp_match):.4f}")
    print(f"按物理 span 计:   {dict(fp_span)} FP={ratio(fp_span):.4f}   口径差 = {(ratio(fp_match)-ratio(fp_span))*100:+.2f} pt")


if __name__ == "__main__":
    main()
