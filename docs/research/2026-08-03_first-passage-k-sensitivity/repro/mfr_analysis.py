"""bb vs bo_only 的 mfr(最大上行潜力)增量验证 —— 临时实验脚本(放 /tmp,不碰正式代码)。

目标:
  forward_return 字段本身就是 mfr(high 版,见 eval.py:8 / serialize.py:335),
  但既有研究结论说"bb 相对 bo_only 无方向优势"。用户怀疑该结论或被"终点值"误解,
  要用明确的 mfr 口径 + 控制波动率,重测 bb 是否在最大上行潜力上有增量。

数据源(零重跑 dag):
  scan file outputs/path2_web/scans/20260802T221046.json 已存 per-match:
    - forward_return  = mfr_high(= match_forward_returns,h horizon=40)
    - start_idx/end_idx(end_node event 的买点窗,与 eval 同锚点)
  本脚本只补两件需 df 的事:
    - mfr_close = max(close[t+1..t+N])/close[t]-1(窗内均值,与 high 版同口径,影线 vs 实体对照)
    - M_t       = rolling_atr_pct_nanmedian(20) 在买点窗 [start_idx,end_idx] 上的 nanmedian

对比:
  A. 整体:所有 bo match vs 所有 bb match
  B. 同池:bb 命中的 134 个 symbol 内,这些 symbol 的 bo vs bb(控制标的池)
  控制波动率:
    方法1 M 分层:按 M_t 的 q33/q66 切低/中/高三档,同档内比 bb vs bo 中位数
    方法2 归一化:mfr / M_t,比"单位波动的最大上行"

只 import 复用 path2/ 与 path2_web/,不改任何正式代码。
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path("/home/yu/PycharmProjects/Trade_Strategy")
sys.path.insert(0, str(REPO))

from path2.calc.atr import rolling_atr_pct_nanmedian  # noqa: E402
from path2_web.data import slice_window               # noqa: E402

SCAN_FILE = REPO / "outputs/path2_web/scans/20260802T221046.json"
N_HORIZON = 40  # label_horizon(scan file)


# ---------------------------------------------------------------------------
# Phase 1:从 scan file 提取 per-match 锚点 + mfr_high
# ---------------------------------------------------------------------------
def extract_matches():
    d = json.loads(SCAN_FILE.read_text())
    scan = d["scan"]
    # symbol → [(pattern, event_id, start_idx, end_idx, mfr_high), ...]
    by_sym: dict[str, list[tuple]] = {}
    for r in d["results"]:
        sym = r["symbol"]
        for pid in ("bo_only", "bottom_burst"):
            for m in r["per_pattern"][pid]["analysis"]["matches"]:
                by_sym.setdefault(sym, []).append((
                    pid, m["event_id"],
                    int(m["start_idx"]), int(m["end_idx"]),
                    m.get("forward_return"),  # mfr_high(scan 已算;None=越界)
                ))
    return by_sym, scan["win_start"], scan["win_end"], scan["dataset_dir"]


# ---------------------------------------------------------------------------
# Phase 2 worker:每 symbol 读一次 pkl,补 mfr_close + M_t(逐 match)
# ---------------------------------------------------------------------------
def _work(symbol, items, win_start, win_end, dataset_dir):
    pkl = Path(dataset_dir) / f"{symbol}.pkl"
    if not pkl.exists():
        return symbol, None, f"pkl missing: {pkl}"
    try:
        df = pd.read_pickle(pkl)
        win = slice_window(df, win_start, win_end)
        if len(win) == 0:
            return symbol, None, "empty win"
        high = win["high"]; low = win["low"]; close = win["close"]
        n_bars = len(win)
        # 标的级 M(整个 win 的 ATR% nanmedian;用于分层兜底)
        M_series = rolling_atr_pct_nanmedian(high, low, close, 20).values
        M_sym = float(np.nanmedian(M_series)) if np.isfinite(M_series).any() else None
        out = []
        for pid, eid, s_idx, e_idx, mfr_high in items:
            # mfr_close:买点窗 [s,e] 内逐 t 窗内均值(与 high 版同口径)
            rets_c = []
            for t in range(s_idx, e_idx + 1):
                if t + N_HORIZON < n_bars:
                    rets_c.append(float(close.iloc[t + 1: t + N_HORIZON + 1].max())
                                  / float(close.iat[t]) - 1.0)
            mfr_close = sum(rets_c) / len(rets_c) if rets_c else None
            # M_t:买点窗 [s,e] 内 ATR% 的 nanmedian(代表该买点的波动率尺度)
            seg = M_series[s_idx: e_idx + 1]
            seg = seg[np.isfinite(seg)]
            M_t = float(np.nanmedian(seg)) if len(seg) else None
            buy_close = float(close.iat[s_idx])
            out.append({
                "symbol": symbol, "pattern": pid, "event_id": eid,
                "start_idx": s_idx, "end_idx": e_idx,
                "mfr_high": mfr_high, "mfr_close": mfr_close,
                "M_t": M_t, "M_sym": M_sym, "buy_close": buy_close,
            })
        return symbol, out, None
    except Exception as e:  # noqa: BLE001
        return symbol, None, f"{type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# 统计辅助
# ---------------------------------------------------------------------------
def _stats(vals):
    vals = [v for v in vals if v is not None and np.isfinite(v)]
    if not vals:
        return {"n": 0}
    arr = np.array(vals)
    return {
        "n": len(arr),
        "median": float(np.median(arr)),
        "mean": float(np.mean(arr)),
        "q25": float(np.quantile(arr, 0.25)),
        "q75": float(np.quantile(arr, 0.75)),
        "q90": float(np.quantile(arr, 0.90)),
    }


def _group(rows, pattern, key="mfr_high"):
    return [r[key] for r in rows if r["pattern"] == pattern]


def _buckets(rows):
    """按 M_t 的 q33/q66 切三档;返回 {tier: [rows]}。"""
    ms = [r["M_t"] for r in rows if r["M_t"] is not None and np.isfinite(r["M_t"])]
    if not ms:
        return {"all": rows}
    q33, q66 = np.quantile(ms, [1/3, 2/3])
    out = {"low": [], "mid": [], "high": []}
    for r in rows:
        m = r["M_t"]
        if m is None or not np.isfinite(m):
            continue
        if m <= q33: out["low"].append(r)
        elif m <= q66: out["mid"].append(r)
        else: out["high"].append(r)
    out["_cuts"] = {"q33": float(q33), "q66": float(q66)}
    return out


def main():
    t0 = time.time()
    by_sym, ws, we, ds = extract_matches()
    total = len(by_sym)
    print(f"[extract] {total} symbols with any match")
    print(f"[extract] win={ws}..{we} horizon={N_HORIZON}")

    rows = []
    errors = 0
    with ProcessPoolExecutor(max_workers=26) as ex:
        futs = [ex.submit(_work, s, it, ws, we, ds) for s, it in by_sym.items()]
        done = 0
        for f in as_completed(futs):
            sym, out, err = f.result()
            done += 1
            if err:
                errors += 1
            elif out:
                rows.extend(out)
            if done % 500 == 0 or done == total:
                rate = done / (time.time() - t0)
                print(f"[progress] {done}/{total} rows={len(rows)} err={errors} "
                      f"rate={rate:.1f}/s", flush=True)

    elapsed = time.time() - t0
    bb = [r for r in rows if r["pattern"] == "bottom_burst"]
    bo = [r for r in rows if r["pattern"] == "bo_only"]
    bb_syms = {r["symbol"] for r in bb}
    bo_in_bbpool = [r for r in bo if r["symbol"] in bb_syms]  # 同池 bo
    print(f"[done] rows={len(rows)} (bo={len(bo)} bb={len(bb)}) "
          f"bb_syms={len(bb_syms)} bo_in_pool={len(bo_in_bbpool)} "
          f"err={errors} elapsed={elapsed:.1f}s")

    # ---- A. 整体对比 --------------------------------------------------------
    res = {"meta": {
        "scan_file": str(SCAN_FILE), "horizon": N_HORIZON,
        "n_bo": len(bo), "n_bb": len(bb), "n_bb_syms": len(bb_syms),
        "n_bo_in_pool": len(bo_in_bbpool), "errors": errors,
        "elapsed_s": round(elapsed, 1),
    }}

    res["A_overall"] = {}
    for key in ("mfr_high", "mfr_close"):
        res["A_overall"][key] = {
            "bo_only": _stats(_group(bo, "bo_only", key)),
            "bb": _stats(_group(bb, "bottom_burst", key)),
        }
    # 同池
    res["B_samepool"] = {}
    for key in ("mfr_high", "mfr_close"):
        res["B_samepool"][key] = {
            "bo_only": _stats(_group(bo_in_bbpool, "bo_only", key)),
            "bb": _stats(_group(bb, "bottom_burst", key)),
        }

    # ---- 方法1 · M 分层(同池,控制标的 + 波动率双重) -------------------------
    pool = bb + bo_in_bbpool  # 同池样本(bo 含 bb 全部 symbol)
    bk = _buckets(pool)
    res["M_stratified_samepool"] = {
        "cuts": bk.get("_cuts"),
        "tiers": {},
    }
    for tier in ("low", "mid", "high"):
        tr = bk[tier]
        res["M_stratified_samepool"]["tiers"][tier] = {
            "n_bo": sum(1 for r in tr if r["pattern"] == "bo_only"),
            "n_bb": sum(1 for r in tr if r["pattern"] == "bottom_burst"),
            "mfr_high": {
                "bo_only_median": _median([r["mfr_high"] for r in tr if r["pattern"] == "bo_only"]),
                "bb_median": _median([r["mfr_high"] for r in tr if r["pattern"] == "bottom_burst"]),
            },
            "mfr_close": {
                "bo_only_median": _median([r["mfr_close"] for r in tr if r["pattern"] == "bo_only"]),
                "bb_median": _median([r["mfr_close"] for r in tr if r["pattern"] == "bottom_burst"]),
            },
        }

    # ---- 方法2 · 归一化 mfr/M_t(整体 + 同池) --------------------------------
    for label, sample in (("overall", bo + bb), ("samepool", pool)):
        norm = []
        for r in sample:
            if r["mfr_high"] is not None and r["M_t"] and np.isfinite(r["M_t"]) and r["M_t"] > 0:
                norm.append({"pattern": r["pattern"], "mfr_high/M": r["mfr_high"] / r["M_t"]})
        res.setdefault("normalized", {})[label] = {
            "mfr_high_over_M": {
                "bo_only": _stats([x["mfr_high/M"] for x in norm if x["pattern"] == "bo_only"]),
                "bb": _stats([x["mfr_high/M"] for x in norm if x["pattern"] == "bottom_burst"]),
            },
        }

    Path("/tmp/mfr_results.json").write_text(json.dumps(res, ensure_ascii=False, indent=2))
    print("[wrote] /tmp/mfr_results.json")

    # 控制台速览
    print("\n=== A. 整体 mfr_high ===")
    _show(res["A_overall"]["mfr_high"])
    print("=== A. 整体 mfr_close ===")
    _show(res["A_overall"]["mfr_close"])
    print("=== B. 同池 mfr_high ===")
    _show(res["B_samepool"]["mfr_high"])
    print("=== B. 同池 mfr_close ===")
    _show(res["B_samepool"]["mfr_close"])
    print("=== 方法1 · M 分层(同池)mfr_high 中位数 ===")
    for tier, t in res["M_stratified_samepool"]["tiers"].items():
        print(f"  {tier}(n_bo={t['n_bo']} n_bb={t['n_bb']}): "
              f"bo={t['mfr_high']['bo_only_median']} bb={t['mfr_high']['bb_median']}")
    print("=== 方法2 · 归一化 mfr_high/M ===")
    _show(res["normalized"]["overall"]["mfr_high_over_M"], label_a="bo", label_b="bb")
    _show(res["normalized"]["samepool"]["mfr_high_over_M"], label_a="bo", label_b="bb")


def _median(vals):
    vals = [v for v in vals if v is not None and np.isfinite(v)]
    return float(np.median(vals)) if vals else None


def _show(d, label_a="bo_only", label_b="bb"):
    a, b = d.get(label_a) or d.get("bo_only"), d.get(label_b) or d.get("bb")
    if not a or not b or a.get("n", 0) == 0 or b.get("n", 0) == 0:
        print(f"  [insufficient] a={a} b={b}"); return
    print(f"  {label_a}: n={a['n']} med={a['median']:.4f} mean={a['mean']:.4f} "
          f"q25={a['q25']:.4f} q75={a['q75']:.4f} q90={a['q90']:.4f}")
    print(f"  {label_b}: n={b['n']} med={b['median']:.4f} mean={b['mean']:.4f} "
          f"q25={b['q25']:.4f} q75={b['q75']:.4f} q90={b['q90']:.4f}")
    print(f"  Δmedian(bb-bo)={b['median']-a['median']:+.4f} "
          f"({(b['median']-a['median'])/a['median']*100:+.1f}%)")


if __name__ == "__main__":
    main()
