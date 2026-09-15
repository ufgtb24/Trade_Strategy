"""锚语义放宽:新增买点的 label 质量(临时脚本,不改正式代码)。

沿用 path2_web 扫描的**规范口径**(与 UI 上看到的数一致):
  slice_window(buf 窗) → engine.analyze → serialize_per_pattern_result(注入
  forward_return / forward_drawdown / first_passage)+ random_day_first_passage 基线。
head buffer 取 bb_v1 的 eval_meta();样本消费窗截到 [start, end]。

分组单位是**买点(leaf = tb 实例)**不是 match——放宽后一个 tb 可以同时配上多个 burst
前缀,match 数会重复计同一个买点;买点是物理量,label 也只按买点算一次。

用法: uv run python .../repro/probe_anchor_widen_label.py
"""
from __future__ import annotations

import dataclasses, statistics, sys
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from probe_anchor_widen import build_widened               # noqa: E402
from path2_apps.bb_v1 import dag_spec as bb                # noqa: E402
from path2.dag.engine import analyze as engine_analyze     # noqa: E402
from path2.eval import random_day_first_passage            # noqa: E402
from path2_web.data import slice_window                    # noqa: E402
from path2_web.serialize import serialize_per_pattern_result  # noqa: E402
from path2_web.scan import TRADING_TO_CALENDAR_RATIO       # noqa: E402


def leaves_of(out) -> dict:
    """{leaf instance_id: {fr, dd, fp}} —— 同 leaf 的多条 match 只留一份。"""
    acc = {}
    for md in out["analysis"]["matches"]:
        lf = md["leaf"]
        if lf not in acc:
            acc[lf] = {"fr": md["forward_return"], "dd": md["forward_drawdown"],
                       "fp": md["first_passage"]}
        elif acc[lf]["fp"] is None and md["first_passage"] is not None:
            acc[lf]["fp"] = md["first_passage"]
    return acc


def summarize(name, leaves):
    frs = [v["fr"] for v in leaves.values() if v["fr"] is not None]
    dds = [v["dd"] for v in leaves.values() if v["dd"] is not None]
    fp = {"up": 0, "down": 0, "both": 0, "none": 0}
    for v in leaves.values():
        if v["fp"]:
            for s in fp:
                fp[s] += v["fp"][s]
    den = fp["up"] + fp["down"]
    ratio = fp["up"] / den if den else None
    return {"name": name, "n_leaf": len(leaves), "n_fr": len(frs),
            "fr_med": statistics.median(frs) if frs else None,
            "dd_med": statistics.median(dds) if dds else None,
            "fp": fp, "n_bar": sum(fp.values()), "ratio": ratio}


def main() -> None:
    DATA_DIR = REPO / "datasets" / "pkls"
    START, END = "2024-01-01", "2026-01-01"
    N_STOCK = 400
    import os
    LABEL_HORIZON = int(os.environ.get("HORIZON", 40))   # configs/path2_web.yaml 的项目默认=40
    FP_K = float(os.environ.get("FP_K", 5.0))
    # ================
    params = bb.load_params()                      # SSoT
    head_buffer = bb.eval_meta(params)["head_buffer_trading_days"]
    end_node = bb.eval_meta(params)["end_node"]
    start_ts, end_ts = pd.to_datetime(START), pd.to_datetime(END)
    buf_start = start_ts - pd.Timedelta(days=round(head_buffer * TRADING_TO_CALENDAR_RATIO))
    buf_end = end_ts + pd.Timedelta(days=round(LABEL_HORIZON * TRADING_TO_CALENDAR_RATIO))
    print(f"head_buffer={head_buffer} 交易日 · end_node={end_node} · horizon={LABEL_HORIZON} · k={FP_K}")

    specs = {"cur": bb.build_pattern(params), "wide": build_widened(params)}
    all_leaves = {"cur": {}, "wide": {}}
    n_match = {"cur": 0, "wide": 0}
    rnd = {"up": 0, "down": 0, "both": 0, "none": 0}
    n_ok = n_hit = 0

    for p in sorted(DATA_DIR.glob("*.pkl"))[:N_STOCK]:
        sym = p.stem
        try:
            df = pd.read_pickle(p)
            win = slice_window(df, buf_start.date(), buf_end.date())
            if len(win) < 200:
                continue
            lo = int(win["date"].searchsorted(start_ts, "left"))
            hi = int(win["date"].searchsorted(end_ts, "right")) - 1
            outs = {}
            for k, sp in specs.items():
                res = engine_analyze(sp, win, params)
                outs[k] = serialize_per_pattern_result(
                    res, end_node=end_node, label_horizon=LABEL_HORIZON,
                    win=win, start_ts=start_ts, end_ts=end_ts,
                    first_passage_k=FP_K, sample_window=(lo, hi))
        except Exception as e:                              # noqa: BLE001
            print(f"  [skip] {sym}: {type(e).__name__}: {e}")
            continue
        n_ok += 1
        hit = False
        for k in specs:
            lv = leaves_of(outs[k])
            n_match[k] += outs[k]["summary"]["matches"]
            all_leaves[k].update({f"{sym}|{i}": v for i, v in lv.items()})
            if lv:
                hit = True
        if hit:
            n_hit += 1
            # n_days 提到 100(默认 RANDOM_DAY_K=3 太少,124 根基线噪声压不住);
            # 股票池仍限命中股,口径不变——只提精度,不换对照组
            r = random_day_first_passage(sym, win, start_ts, end_ts, LABEL_HORIZON,
                                         FP_K, n_days=100)
            for s in rnd:
                rnd[s] += r["counts"][s]

    cur, wide = all_leaves["cur"], all_leaves["wide"]
    new = {k: v for k, v in wide.items() if k not in cur}
    kept = {k: v for k, v in wide.items() if k in cur}

    print(f"\n股票数 = {n_ok}(其中有命中 {n_hit})")
    print(f"match 数:现状 {n_match['cur']} → 放宽 {n_match['wide']}")
    print(f"买点(leaf)数:现状 {len(cur)} → 放宽 {len(wide)}"
          f"(其中沿用 {len(kept)}、新增 {len(new)})")
    miss = set(cur) - set(wide)
    print(f"放宽后丢失的原有买点 = {len(miss)}(应为 0——放宽只增不减)")

    rows = [summarize("现状 26 那批(cur)", cur),
            summarize("放宽后全体(wide)", wide),
            summarize("  └ 其中沿用的", kept),
            summarize("  └ 其中新增的", new)]
    print(f"\n{'':22}{'买点数':>7}{'fr 中位':>10}{'dd 中位':>10}"
          f"{'买点日':>8}{'up':>6}{'down':>6}{'首穿率':>9}")
    for r in rows:
        fm = f"{r['fr_med']:+.4f}" if r['fr_med'] is not None else "  n/a"
        dm = f"{r['dd_med']:+.4f}" if r['dd_med'] is not None else "  n/a"
        rt = f"{r['ratio']:.3f}" if r['ratio'] is not None else "n/a"
        print(f"{r['name']:22}{r['n_leaf']:>7}{fm:>10}{dm:>10}"
              f"{r['n_bar']:>8}{r['fp']['up']:>6}{r['fp']['down']:>6}{rt:>9}")
    den = rnd["up"] + rnd["down"]
    print(f"{'随机日基线':22}{'':>7}{'':>10}{'':>10}"
          f"{sum(rnd.values()):>8}{rnd['up']:>6}{rnd['down']:>6}"
          f"{(rnd['up']/den if den else float('nan')):>9.3f}")


if __name__ == "__main__":
    main()
