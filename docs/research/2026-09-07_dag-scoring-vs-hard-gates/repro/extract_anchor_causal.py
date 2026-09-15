"""锚放宽的因果修正版:三份 spec 对照(现状 / 放宽 / 放宽+因果闸)。

stats 抓到的缺陷:放宽版 `ContainmentEdge(burst,bo) + TemporalEdge(bo,tb)` 没有任何
东西约束 `burst.end_idx < tb.start_idx`。burst 是回顾型事件(confirm_idx = end_idx),
所以一个 tb 可以配上买点之后才成形的 burst —— 前瞻偏差。

修法(本脚本验证):加第三条边 `TemporalEdge(burst, tb, min_gap=1, max_gap=tb.max_span)`。
  · min_gap=1 恰好复刻现状 spec 已有的因果纪律:现状边锚 last_bo、而
    burst.end_idx == last_bo.end_idx,故现状本来就要求 tb.start - burst.end >= 1。
    这条修正只放开身份约束,不放开因果约束。
  · max_gap 取 tb.max_span 不 binding:tb.start - burst.end <= tb.start - bo.end <= max_span。

口径其余部分与同目录 extract_anchor_widen.py / extract_wide.py 完全一致。

用法: uv run python .../repro/extract_anchor_causal.py
"""
from __future__ import annotations

import sys, time
from dataclasses import replace
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from path2.calc.atr import FP_ATR_WINDOW, rolling_atr_pct_nanmedian   # noqa: E402
from path2.dag.edges import ContainmentEdge, TemporalEdge             # noqa: E402
from path2.dag.engine import analyze as dag_analyze                   # noqa: E402
from path2.eval import (match_first_passage, match_forward_drawdowns, # noqa: E402
                        match_forward_returns)
from path2_apps.bb_v1.dag_spec import build_pattern                   # noqa: E402
from path2_apps.bb_v1.params import load_params                       # noqa: E402
from path2_web.data import slice_window                               # noqa: E402
from path2_web.serialize import _resolve_end_events                   # noqa: E402

DATA_DIR = Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls")
OUT_DIR = Path(__file__).parent
RATIO, HEAD_BUFFER, LABEL_HORIZON, FP_K = 1.65, 63, 40, 5.0
PRICE_MIN, PRICE_MAX, VOLUME_MIN = 0.5, 30.0, 10000.0
WINDOWS = {"w2025": ("2025-01-01", "2026-01-01"), "w2024": ("2024-01-01", "2025-01-01")}


def _wide_edges(params):
    return (ContainmentEdge("burst", "bo"),
            TemporalEdge("bo", "tb", min_gap=1, max_gap=params.tb.max_span,
                         anchor_field="anchor_bo_id"))


def build_specs(params):
    base = build_pattern(params)
    return {
        "cur":    base,
        "wide":   replace(base, edges=_wide_edges(params)),
        # ★ 因果闸:burst 必须在买点之前确认(burst 是回顾型,confirm_idx = end_idx)
        "causal": replace(base, edges=_wide_edges(params) + (
            TemporalEdge("burst", "tb", min_gap=1, max_gap=params.tb.max_span),)),
    }


def _one(args):
    sym, sd, ed = args
    try:
        start_ts, end_ts = pd.Timestamp(sd), pd.Timestamp(ed)
        df = pd.read_pickle(DATA_DIR / f"{sym}.pkl")
        win = slice_window(df,
                           (start_ts - pd.Timedelta(days=round(HEAD_BUFFER * RATIO))).date(),
                           (end_ts + pd.Timedelta(days=round(LABEL_HORIZON * RATIO))).date())
        if len(win) == 0:
            return sym, [], None
        sw = win[(win["date"] >= start_ts) & (win["date"] <= end_ts)]
        if len(sw) == 0 or sw["volume"].mean() <= VOLUME_MIN:
            return sym, [], None
        params = load_params()
        specs = build_specs(params)
        lo = int(win["date"].searchsorted(start_ts, "left"))
        hi = int(win["date"].searchsorted(end_ts, "right")) - 1
        M = rolling_atr_pct_nanmedian(win["high"], win["low"], win["close"],
                                      FP_ATR_WINDOW).values

        per: dict = {}
        for name, sp in specs.items():
            keep = {}
            for m in dag_analyze(sp, win, params).matches:
                evs = _resolve_end_events(m, "tb")
                if not any(start_ts <= win["date"].iat[e.start_idx] <= end_ts for e in evs):
                    continue
                if not any(PRICE_MIN <= float(win["close"].iat[e.start_idx]) <= PRICE_MAX
                           for e in evs):
                    continue
                tb, bu = m.node_index["tb"], m.node_index["burst"]
                # 每个买点留「最早确认的 burst」作代表
                if tb.instance_id not in keep or bu.end_idx < keep[tb.instance_id][1].end_idx:
                    keep[tb.instance_id] = (m, bu, tb)
            per[name] = keep

        cur_tbs = set(per["cur"])
        rows = []
        for name in ("cur", "wide", "causal"):
            for tid, (m, bu, tb) in per[name].items():
                t0 = tb.start_idx
                fp = {k_: match_first_passage(m, "tb", win, LABEL_HORIZON, k=k_,
                                              sample_window=(lo, hi), M=M)
                      for k_ in (4.0, 5.0, 6.0)}
                rows.append(dict(
                    symbol=sym, variant=name, tb_id=tid, bo_id=tb.anchor_bo_id,
                    burst_id=bu.instance_id,
                    group=("原有" if tid in cur_tbs else "新增"),
                    burst_end=int(bu.end_idx), tb_start=int(t0),
                    # 因果余量:>=1 即买点当日 burst 已确认
                    causal_gap=int(t0 - bu.end_idx),
                    n_bo_after=int(sum(1 for x in bu.members if x.end_idx >= t0)),
                    tb_date=str(win["date"].iat[t0])[:10],
                    fr=match_forward_returns(m, "tb", win, [LABEL_HORIZON],
                                             sample_window=(lo, hi))[LABEL_HORIZON],
                    dd=match_forward_drawdowns(m, "tb", win, [LABEL_HORIZON],
                                               sample_window=(lo, hi))[LABEL_HORIZON],
                    fp4_up=fp[4.0]["up"], fp4_down=fp[4.0]["down"],
                    fp_up=fp[5.0]["up"], fp_down=fp[5.0]["down"],
                    fp6_up=fp[6.0]["up"], fp6_down=fp[6.0]["down"],
                    n_buy_bars=sum(fp[5.0].values()),
                    atr_pct=float(M[t0]) if np.isfinite(M[t0]) else np.nan,
                ))
        return sym, rows, None
    except Exception as e:                                    # noqa: BLE001
        return sym, [], f"{type(e).__name__}: {e}"


def main():
    syms = sorted(p.stem for p in DATA_DIR.glob("*.pkl"))
    for tag, (sd, ed) in WINDOWS.items():
        t0 = time.time()
        rows, errs = [], []
        with Pool(24) as pool:
            for sym, r, err in pool.imap_unordered(
                    _one, [(s, sd, ed) for s in syms], chunksize=16):
                rows.extend(r)
                if err:
                    errs.append((sym, err))
        d = pd.DataFrame(rows)
        d.to_csv(OUT_DIR / f"causal_{tag}.csv", index=False)
        print(f"\n===== {tag} =====  errors={len(errs)} wall={time.time()-t0:.0f}s")
        cur = set(d[d.variant == "cur"].tb_id)
        for name in ("cur", "wide", "causal"):
            v = d[d.variant == name]
            print(f"  {name:7} 买点={len(v):5}  新增={int((v.group=='新增').sum()):5}"
                  f"  最小 causal_gap={int(v.causal_gap.min()) if len(v) else 0:4}"
                  f"  非因果(gap<1)={int((v.causal_gap < 1).sum()):5}"
                  f"  丢失原有={len(cur - set(v.tb_id)):3}")
        print(f"\n  {'变体·组':<16}{'买点':>6}{'买点日':>7}"
              f"{'FPR k=4':>9}{'FPR k=5':>9}{'FPR k=6':>9}{'fr 中位':>10}{'dd 中位':>10}")
        for name in ("cur", "causal", "wide"):
            for g in ("原有", "新增"):
                v = d[(d.variant == name) & (d.group == g)]
                if not len(v):
                    continue
                def _r(u, dn):
                    n = v[u].sum() + v[dn].sum()
                    return v[u].sum() / n if n else float("nan")
                print(f"  {name + '·' + g:<16}{len(v):>6}{int(v.n_buy_bars.sum()):>7}"
                      f"{_r('fp4_up','fp4_down'):>9.3f}{_r('fp_up','fp_down'):>9.3f}"
                      f"{_r('fp6_up','fp6_down'):>9.3f}"
                      f"{v.fr.median():>+10.4f}{v.dd.median():>+10.4f}")


if __name__ == "__main__":
    main()
