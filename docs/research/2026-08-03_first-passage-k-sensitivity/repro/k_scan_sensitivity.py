"""k 敏感性扫描临时实验脚本(临时,放 /tmp,不碰正式代码)。

目标:对 k = [1.0, 1.5, 2.0, 2.5, 3.0] 重评估 first_passage 指标,考查 k 的合理性。

方法(关键优化:每 ticker 跑一次 dag,缓存 matches + df,然后对 5 个 k 重算首穿):
  - 复用 outputs/path2_web/scans/20260802T221046.json 的扫描口径(dates / dataset_dir /
    label_horizon / filters / params_snapshot),保证可对比。
  - 每股:dag 只跑一遍 → 取 matches(按 date + price 过滤,与 serialize 同口径);然后对
    每个 k 调 path2.eval.match_first_passage(每 match)与 random_day_first_passage(每票一次)。
  - 聚合:跨 ticker 累加 per-(pattern,k) 与 per-(random,k) 的四态计数,算 ratio/none 占比。
  - 校验:k=2.0 必须复现 scan file 的 first_passage_stats(up/down/both/none + random),
    否则脚本 FAIL 不出报告。

只 import 复用 path2/ 与 path2_web/ 的函数,不修改任何正式代码。
"""
from __future__ import annotations

import dataclasses
import importlib
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

# --- repo root 上 path -------------------------------------------------------
REPO = Path("/home/yu/PycharmProjects/Trade_Strategy")
sys.path.insert(0, str(REPO))

from path2.dag.engine import analyze as dag_analyze          # noqa: E402
from path2.eval import (                                      # noqa: E402
    match_first_passage,
    random_day_first_passage,
)
from path2_web.data import slice_window                       # noqa: E402
from path2_web.gate_collector import attach_and_collect, detach  # noqa: E402
from path2_web.discovery import PatternRegistry               # noqa: E402

# --- scan 元数据 -------------------------------------------------------------
SCAN_FILE = REPO / "outputs/path2_web/scans/20260802T221046.json"
KS = [2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]   # 2.0=validation anchor;全面统计
TRADING_TO_CALENDAR_RATIO = 1.65   # 与 scan.py 同源
STATES = ("up", "down", "both", "none")


def load_scan_meta():
    d = json.loads(SCAN_FILE.read_text())
    scan = d["scan"]
    reg = PatternRegistry()
    reg.refresh()
    pattern_ids = d["pattern_ids"]
    module_paths = {pid: reg.module_path(pid) for pid in pattern_ids}
    end_nodes = {pid: d["per_pattern"][pid]["end_node"] for pid in pattern_ids}
    params_snaps = {pid: d["per_pattern"][pid]["params_snapshot"] for pid in pattern_ids}
    return {
        "pattern_ids": pattern_ids,
        "module_paths": module_paths,
        "end_nodes": end_nodes,
        "params_snaps": params_snaps,
        "start_date": scan["start_date"],
        "end_date": scan["end_date"],
        "dataset_dir": scan["dataset_dir"],
        "label_horizon": scan["label_horizon"],
        "filters": scan.get("filters", {}),
        "win_start": scan["win_start"],
        "win_end": scan["win_end"],
        "baseline_k2": {pid: d["per_pattern"][pid]["first_passage_stats"] for pid in pattern_ids},
        "n_results": len(d["results"]),
    }


# --- worker(模块级,pickle 安全)-------------------------------------------
def _scan_ticker(pkl_path, meta, ks):
    """单股:dag 跑一次,缓存 matches,对 ks 重算首穿。

    返回 (symbol, per_pattern_counts, random_counts, err)。
      per_pattern_counts: {pid: {k(str): {up,down,both,none}}}  跨 match 累加
      random_counts:      {k(str): {up,down,both,none}}          单票一次
    err 非 None → 该股异常。
    """
    from path2.debug import set_current_symbol
    symbol = Path(pkl_path).stem
    set_current_symbol(symbol)
    start_ts = pd.to_datetime(meta["start_date"])
    end_ts = pd.to_datetime(meta["end_date"])
    price_min = meta["filters"].get("price_min")
    price_max = meta["filters"].get("price_max")
    volume_min = meta["filters"].get("volume_min")
    try:
        df = pd.read_pickle(pkl_path)
        win = slice_window(df, meta["win_start"], meta["win_end"])
        if len(win) == 0:
            return symbol, None, None, None
        # 股票级成交量预筛(与 _scan_ticker_multi 同口径)
        if volume_min is not None:
            scan_win = win[(win["date"] >= start_ts) & (win["date"] <= end_ts)]
            if len(scan_win) == 0 or scan_win["volume"].mean() <= volume_min:
                return symbol, None, None, None

        # 1) dag 每模式跑一次,缓存过滤后 matches
        surviving: dict = {}
        any_match = False
        for pid in meta["pattern_ids"]:
            mod = importlib.import_module(meta["module_paths"][pid])
            params = mod.Params.from_dict(meta["params_snaps"][pid])
            spec = mod.build_pattern(params)
            collector = attach_and_collect(spec)
            try:
                res = dag_analyze(spec, win, params)
            finally:
                detach(spec)
            res = dataclasses.replace(res, gate_failures=collector.snapshot())
            end_node = meta["end_nodes"][pid]
            # date + price 过滤(与 serialize_per_pattern_result 同口径)
            keep = []
            for m in res.matches:
                ev = m.node_index[end_node]
                buy_date = win["date"].iat[ev.start_idx]
                if not (start_ts <= buy_date <= end_ts):
                    continue
                buy_close = win["close"].iat[ev.start_idx]
                if price_min is not None and buy_close < price_min:
                    continue
                if price_max is not None and buy_close > price_max:
                    continue
                keep.append(m)
            surviving[pid] = keep
            if keep:
                any_match = True

        if not any_match:
            return symbol, None, None, None

        # 2) 对每个 k,重算首穿(复用 path2.eval 公开函数;cheap)
        per_pattern_counts = {pid: {} for pid in meta["pattern_ids"]}
        for pid in meta["pattern_ids"]:
            end_node = meta["end_nodes"][pid]
            for k in ks:
                tot = {s: 0 for s in STATES}
                for m in surviving[pid]:
                    c = match_first_passage(m, end_node, win,
                                            meta["label_horizon"], k)
                    for s in STATES:
                        tot[s] += c[s]
                per_pattern_counts[pid][str(k)] = tot

        random_counts = {}
        for k in ks:
            r = random_day_first_passage(symbol, win, start_ts, end_ts,
                                         meta["label_horizon"], k)
            random_counts[str(k)] = r["counts"]
        return symbol, per_pattern_counts, random_counts, None
    except Exception as e:  # noqa: BLE001
        return symbol, None, None, f"{type(e).__name__}: {e}"
    finally:
        set_current_symbol(None)


def main():
    t0 = time.time()
    meta = load_scan_meta()
    print(f"[meta] pattern_ids={meta['pattern_ids']} horizon={meta['label_horizon']} "
          f"dates={meta['start_date']}..{meta['end_date']}")
    print(f"[meta] filters={meta['filters']} win={meta['win_start']}..{meta['win_end']}")
    print(f"[meta] baseline scan n_results(hits)={meta['n_results']}")

    pkls = sorted(Path(meta["dataset_dir"]).glob("*.pkl"))
    total = len(pkls)
    print(f"[scan] {total} tickers, workers=26, ks={KS}")

    # 取最大 head_buffer(两 pattern 都是 63,但保通用)
    agg_pp = {pid: {str(k): {s: 0 for s in STATES} for k in KS}
              for pid in meta["pattern_ids"]}
    agg_rand = {str(k): {s: 0 for s in STATES} for k in KS}
    scanned = hits = errors = 0
    last = t0

    with ProcessPoolExecutor(max_workers=26) as ex:
        futs = [ex.submit(_scan_ticker, str(p), meta, KS) for p in pkls]
        for fut in as_completed(futs):
            symbol, pp, rnd, err = fut.result()
            scanned += 1
            if err is not None:
                errors += 1
            elif pp is not None:
                hits += 1
                for pid in meta["pattern_ids"]:
                    for k in KS:
                        for s in STATES:
                            agg_pp[pid][str(k)][s] += pp[pid][str(k)][s]
                for k in KS:
                    for s in STATES:
                        agg_rand[str(k)][s] += rnd[str(k)][s]
            if scanned % 200 == 0 or scanned == total:
                now = time.time()
                rate = scanned / (now - t0)
                eta = (total - scanned) / rate if rate else 0
                print(f"[progress] {scanned}/{total} hits={hits} err={errors} "
                      f"rate={rate:.1f}/s eta={eta:.0f}s "
                      f"(+{now-last:.1f}s)", flush=True)
                last = now

    elapsed = time.time() - t0
    print(f"[done] scanned={scanned} hits={hits} errors={errors} "
          f"elapsed={elapsed:.1f}s")

    out = {
        "meta": {
            "scan_file": str(SCAN_FILE),
            "pattern_ids": meta["pattern_ids"],
            "label_horizon": meta["label_horizon"],
            "start_date": meta["start_date"],
            "end_date": meta["end_date"],
            "filters": meta["filters"],
            "ks": KS,
            "scanned": scanned, "hits": hits, "errors": errors,
            "elapsed_s": round(elapsed, 1),
        },
        "per_pattern": agg_pp,
        "random": agg_rand,
        "baseline_k2": meta["baseline_k2"],
    }
    Path("/tmp/k_scan_results_full.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print("[wrote] /tmp/k_scan_results_full.json")

    # 校验 k=2.0 vs scan baseline
    print("\n[validate] k=2.0 vs scan baseline:")
    ok = True
    for pid in meta["pattern_ids"]:
        mine = agg_pp[pid]["2.0"]
        base = meta["baseline_k2"][pid]
        for s in STATES:
            m_v, b_v = mine[s], base[s]
            match = (m_v == b_v)
            ok = ok and match
            print(f"  {pid}.{s}: mine={m_v} baseline={b_v} {'OK' if match else 'MISMATCH'}")
    # random baseline (scan 把 random 也存进每 pattern 的 first_passage_stats,值相同)
    rand_base = meta["baseline_k2"][meta["pattern_ids"][0]]  # bo_only
    for s in STATES:
        key = f"random_{s}"
        m_v, b_v = agg_rand["2.0"][s], rand_base[key]
        match = (m_v == b_v)
        ok = ok and match
        print(f"  random.{s}: mine={m_v} baseline={b_v} {'OK' if match else 'MISMATCH'}")
    print(f"[validate] {'PASS' if ok else 'FAIL'}")


if __name__ == "__main__":
    main()
