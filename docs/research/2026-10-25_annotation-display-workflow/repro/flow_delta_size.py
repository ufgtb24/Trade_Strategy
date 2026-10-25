"""一次改动在全池增减多少个买点：bb_v1 在训练段上，几道 where 门槛各松 / 紧一档，
按（股票, 买点日）对拍新增与去掉，并记全池扫一遍的耗时。
只读截到 2025-12-31 的副本；不落盘到 outputs/。用法：uv run python <本文件>"""
import sys, time, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from path2_web.eval_runner import _eval_core, _resolve_meta  # noqa: E402

MOD = "path2_apps.bb_v1"
START, END = "2021-10-08", "2025-12-31"
DATA = str(ROOT / "datasets" / "pkls_until_20251231")
VARIANTS = {
    "基线": None,
    "放量门槛 3→2.5（松）": {"burst": {"vol_spike_min": 2.5}},
    "放量门槛 3→4（紧）": {"burst": {"vol_spike_min": 4}},
    "沉寂天数 40→30（松）": {"burst": {"first_drought_min": 30}},
    "沉寂天数 40→50（紧）": {"burst": {"first_drought_min": 50}},
    "回踩单日跌幅 0.2→0.15（紧）": {"tb": {"max_day_drop_pct": 0.15}},
}

def keys(res):
    return {(r["symbol"], r["buy_date"]) for r in res["results"]}

end_node, hb = _resolve_meta(MOD, None, None)
out = {}
base = None
for name, ov in VARIANTS.items():
    t0 = time.perf_counter()
    res = _eval_core(module_path=MOD, start=START, end=END, horizons=(20,), end_node=end_node,
                     head_buffer_trading_days=hb, param_overrides=ov, data_dir=DATA, workers=26, ticker_regex=None)
    el = time.perf_counter() - t0
    k = keys(res)
    if base is None:
        base = k
        print(f"{name}: 买点 {len(k)} 个（股票+买点日去重），{len({s for s,_ in k})} 只股票，全池扫一遍 {el:.0f} 秒，errors={res['meta']['errors']}")
    else:
        add, rem = k - base, base - k
        print(f"{name}: 买点 {len(k)}，新增 {len(add)}（{len(add)/len(base):.0%}），去掉 {len(rem)}（{len(rem)/len(base):.0%}），扫 {el:.0f} 秒")
    out[name] = len(k)
