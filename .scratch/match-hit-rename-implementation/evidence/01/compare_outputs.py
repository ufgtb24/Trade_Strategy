"""票 01「只改名、没改行为」的对照：改名前后各跑一遍，把每个 app 在几只股票上的 hit 逐个落成 JSON。

用法（在 worktree 根目录，用 worktree 的 .venv）：
    python <本文件> dump <输出.json>            # 跑一遍，写 JSON
    python <本文件> diff <改名前.json> <改名后.json>   # 逐项比较，全同退出码 0
    python <本文件> discover <app>              # 找有 hit 的股票（选股用，只跑一次）

读数：经 path2_web.data.read_bars 读训练段副本 datasets/pkls_until_20251231（截到训练段末日），
再用 slice_window 切 WINDOW，与扫描 worker 同一条读数路径。不读 datasets/pkls。

每个 hit 记：hit_id、起止确认下标、node 绑定（node_id → 事件类型、instance_id、起止确认下标）、
买点日（eval_meta 的 end_node 解析出的买点日日期）、前瞻涨幅 / 前瞻回撤（HORIZONS 各一项）、
首次穿越四态（FP_HORIZON）。

改名前后接口名字不同（matches/hits、match_id/hit_id、match_forward_*/hit_forward_*），
本脚本两边都认，只为在同一份脚本里跑两次；产品代码里不留旧名。
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys

import path2.eval as ev
from path2_web.data import read_bars, slice_window

DATA_DIR = "datasets/pkls_until_20251231"
WINDOW = ("2021-01-01", "2025-12-31")
HORIZONS = (5, 10, 20, 40)
FP_HORIZON = 40

# 每个 app 挑的股票：discover 在训练段副本上找出的、有 hit 的股票（固定下来，两次跑同一批）
# try_conplex_where 在改名前就跑不起来（throwback_v1 取 BOEvent.members 报 AttributeError），
# 记下报错本身，两次报错相同即算行为没变。
APPS: dict[str, list[str]] = {
    "bb_v1": ["PLTR", "SOFI", "AMC"],
    "bo_only": ["AAPL", "NVDA", "PLTR"],
    "bottom_burst": ["GME", "DRIO", "APRE"],
    "new_step": ["PLTR", "AMC", "GME"],
    "try_conplex_where": ["PLTR", "GME"],
}

DISCOVER_POOL = ["AAPL", "NVDA", "AMD", "TSLA", "PLTR", "SOFI", "MARA", "RIOT", "AMC", "GME",
                 "NIO", "LCID", "F", "SNAP", "UBER", "HOOD", "RIVN", "COIN", "SMCI", "ARM",
                 "INTC", "BB", "NOK", "CCL", "AAL", "PLUG", "FCEL", "SNDL", "TLRY", "CLSK"]


def _pick(obj, new: str, old: str):
    """改名后取新名，改名前取旧名。"""
    return getattr(obj, new) if hasattr(obj, new) else getattr(obj, old)


def _load(app: str):
    mod = importlib.import_module(f"path2_apps.{app}")
    params = mod.load_params()
    end_node = mod.eval_meta(params)["end_node"]
    return mod, params, end_node


def _ev_dict(e) -> list:
    return [type(e).__name__, e.instance_id, int(e.start_idx), int(e.end_idx),
            None if e.confirm_idx is None else int(e.confirm_idx)]


def _round(x):
    return None if x is None else round(float(x), 12)


def run_one(app: str, symbol: str) -> list[dict]:
    mod, params, end_node = _load(app)
    df = slice_window(read_bars(DATA_DIR, symbol), *WINDOW)
    res = mod.analyze(df, params)
    hits = _pick(res, "hits", "matches")
    fwd_ret = _pick(ev, "hit_forward_returns", "match_forward_returns")
    fwd_dd = _pick(ev, "hit_forward_drawdowns", "match_forward_drawdowns")
    fp = _pick(ev, "hit_first_passage", "match_first_passage")
    dates = df["date"].dt.strftime("%Y-%m-%d").tolist()
    out = []
    for h in hits:
        buy = [dates[t] for e in ev._resolve_end_events(h, end_node) for t in e.sample_bar_indices()]
        out.append({
            "hit_id": _pick(h, "hit_id", "match_id"),
            "span": [int(h.start_idx), int(h.end_idx), int(h.confirm_idx)],
            "nodes": {nid: _ev_dict(e) for nid, e in sorted(h.node_index.items())},
            "buy_dates": buy,
            "forward_returns": {str(k): _round(v) for k, v in fwd_ret(h, end_node, df, HORIZONS).items()},
            "forward_drawdowns": {str(k): _round(v) for k, v in fwd_dd(h, end_node, df, HORIZONS).items()},
            "first_passage": fp(h, end_node, df, FP_HORIZON),
        })
    return out


def _run_or_error(app: str, symbol: str):
    try:
        return run_one(app, symbol)
    except Exception as e:  # noqa: BLE001 — 报错本身也是要比较的产出
        return [{"error": f"{type(e).__name__}: {e}"}]


def dump(path: str) -> None:
    result = {app: {sym: _run_or_error(app, sym) for sym in syms} for app, syms in APPS.items()}
    with open(path, "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=1, sort_keys=True)
    for app, per in result.items():
        print(app, {s: len(v) for s, v in per.items()})


def diff(a_path: str, b_path: str) -> int:
    a, b = json.load(open(a_path)), json.load(open(b_path))
    bad = 0
    n = 0
    for app in sorted(set(a) | set(b)):
        for sym in sorted(set(a.get(app, {})) | set(b.get(app, {}))):
            ha, hb = a.get(app, {}).get(sym), b.get(app, {}).get(sym)
            if ha is None or hb is None or len(ha) != len(hb):
                print(f"不同：{app} {sym} hit 个数 {None if ha is None else len(ha)} vs {None if hb is None else len(hb)}")
                bad += 1
                continue
            for i, (x, y) in enumerate(zip(ha, hb)):
                n += 1
                for key in sorted(set(x) | set(y)):
                    if x.get(key) != y.get(key):
                        print(f"不同：{app} {sym} 第 {i} 个 hit 的 {key}")
                        bad += 1
    print(f"比较了 {n} 个 hit，{bad} 处不同")
    return 1 if bad else 0


def discover(app: str) -> None:
    for sym in DISCOVER_POOL:
        try:
            n = len(run_one(app, sym))
        except FileNotFoundError:
            continue
        print(app, sym, n, flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("dump").add_argument("out")
    d = sub.add_parser("diff")
    d.add_argument("a")
    d.add_argument("b")
    sub.add_parser("discover").add_argument("app")
    args = ap.parse_args()
    if args.cmd == "dump":
        dump(args.out)
        return 0
    if args.cmd == "diff":
        return diff(args.a, args.b)
    discover(args.app)
    return 0


if __name__ == "__main__":
    sys.exit(main())
