"""锚语义放宽的 label 质量:全宇宙 × 两窗,样本单位 = 买点(tb 实例)。

在 framework 的两份 spec 上加三件他没做的事:全宇宙两窗、波动率层匹配基线 + 整簇
自助 CI、以及**因果性拆分**。

因果性拆分是本脚本的重点。`burst` 是**回顾型**事件(`confirm_idx = end_idx`,区段走完
才能确认)。现状 spec 锚簇末 bo、且 `min_gap>=1`,所以恒有 `burst.end_idx < tb.start_idx`
——买点时刻 burst 已确认。放宽成「锚簇内任一 bo」后,这个约束没了:一个 tb 可以配上
一个**在买点之后才确认**的 burst。若新增买点大量落在这一类,它们的 label 优势就不是
「救回被连坐的样本」,而是「用了买点当天还不知道的信息」。

每个买点记:
  - group: 原有(现状 spec 也命中该 tb) / 新增(只有放宽 spec 命中)
  - causal: 是否存在**至少一个**匹配 burst 满足 end_idx < tb.start_idx(买点时已确认)
  - n_bo_after: 最长匹配 burst 里落在买点当日或之后的成员 bo 数(机械续涨的直接度量)
  - pos_from_end: 锚 bo 在最长匹配 burst 里距末尾的成员数(现状恒为 0)
label 只与 tb 有关,故同一 tb 只算一次。
"""
from __future__ import annotations

import dataclasses
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

from path2.calc.atr import FP_ATR_WINDOW, rolling_atr_pct_nanmedian   # noqa: E402
from path2.dag.edges import ContainmentEdge, TemporalEdge             # noqa: E402
from path2.dag.engine import analyze as dag_analyze                   # noqa: E402
from path2.eval import (match_first_passage, match_forward_drawdowns,  # noqa: E402
                        match_forward_returns)
from path2_apps.bb_v1 import dag_spec as bb                           # noqa: E402
from path2_web.data import slice_window                               # noqa: E402
from path2_web.serialize import _resolve_end_events                   # noqa: E402
from extract_wide import (_random_days, DATA_DIR, HEAD_BUFFER,        # noqa: E402
                          LABEL_HORIZON, FP_K, PRICE_MIN, PRICE_MAX,
                          RATIO, VOLUME_MIN, BASE_N_DAYS, WINDOWS)


def build_widened(params):
    """framework 的放宽写法(逐字):锚末 bo → 锚簇内任一 bo,只改 edges。"""
    spec = bb.build_pattern(params)
    return dataclasses.replace(spec, edges=(
        ContainmentEdge("burst", "bo"),
        TemporalEdge("bo", "tb", min_gap=1, max_gap=params.tb.max_span,
                     anchor_field="anchor_bo_id"),
    ))


def _keep(m, win, s, e):
    """serialize 同口径过滤:end_node 事件起点 ∈ 窗 且 收盘价 ∈ [PRICE_MIN, PRICE_MAX]。"""
    evs = _resolve_end_events(m, "tb")
    if not any(s <= win["date"].iat[ev.start_idx] <= e for ev in evs):
        return False
    return any(PRICE_MIN <= float(win["close"].iat[ev.start_idx]) <= PRICE_MAX
               for ev in evs)


def _one(args):
    sym, sd, ed = args
    try:
        s, e = pd.Timestamp(sd), pd.Timestamp(ed)
        win = slice_window(pd.read_pickle(DATA_DIR / f"{sym}.pkl"),
                           (s - pd.Timedelta(days=round(HEAD_BUFFER * RATIO))).date(),
                           (e + pd.Timedelta(days=round(LABEL_HORIZON * RATIO))).date())
        if len(win) == 0:
            return sym, [], []
        sw = win[(win["date"] >= s) & (win["date"] <= e)]
        if len(sw) == 0 or sw["volume"].mean() <= VOLUME_MIN:
            return sym, [], []
        params = bb.load_params()                       # SSoT
        lo = int(win["date"].searchsorted(s, "left"))
        hi = int(win["date"].searchsorted(e, "right")) - 1
        M = rolling_atr_pct_nanmedian(win["high"], win["low"], win["close"],
                                      FP_ATR_WINDOW).values

        res_cur = dag_analyze(bb.build_pattern(params), win, params)
        res_wide = dag_analyze(build_widened(params), win, params)
        cur_tb = {m.node_index["tb"].instance_id for m in res_cur.matches
                  if _keep(m, win, s, e)}

        # 放宽 spec:按 tb 聚合它匹配到的全部 burst
        by_tb: dict = {}
        for m in res_wide.matches:
            if not _keep(m, win, s, e):
                continue
            tb, bu = m.node_index["tb"], m.node_index["burst"]
            by_tb.setdefault(tb.instance_id, {"m": m, "tb": tb, "bursts": []})
            by_tb[tb.instance_id]["bursts"].append(bu)

        rows = []
        for tid, d in by_tb.items():
            tb, m = d["tb"], d["m"]
            t0 = int(tb.start_idx)
            bursts = d["bursts"]
            # 因果性:存在至少一个「买点时已确认」的 burst(burst.confirm_idx = end_idx)
            causal = any(int(b.end_idx) < t0 for b in bursts)
            longest = max(bursts, key=lambda b: len(b.members))
            members = [int(x.end_idx) for x in longest.members]
            anchor = int(tb.anchor_bo_id.split("_")[-1].split("#")[0]) \
                if False else None                       # 不解析 id,用 members 定位
            # 锚 bo 的 end_idx:tb.anchor_bo_id 指向的那根,从任一 burst 的 members 里找
            a_idx = None
            for b in bursts:
                for x in b.members:
                    if x.instance_id == tb.anchor_bo_id:
                        a_idx = int(x.end_idx)
                        break
                if a_idx is not None:
                    break
            fr = match_forward_returns(m, "tb", win, [LABEL_HORIZON],
                                       sample_window=(lo, hi))[LABEL_HORIZON]
            dd = match_forward_drawdowns(m, "tb", win, [LABEL_HORIZON],
                                         sample_window=(lo, hi))[LABEL_HORIZON]
            fps = {}
            for k in (4.0, 5.0, 6.0):
                c = match_first_passage(m, "tb", win, LABEL_HORIZON, k=k,
                                        sample_window=(lo, hi), M=M)
                fps[k] = c
            rows.append(dict(
                symbol=sym, tb_id=tid, group=("原有" if tid in cur_tb else "新增"),
                causal=causal, n_burst=len(bursts),
                tb_start=t0, tb_date=str(win["date"].iat[t0])[:10],
                anchor_idx=a_idx if a_idx is not None else -1,
                burst_end_max=int(max(int(b.end_idx) for b in bursts)),
                burst_end_min=int(min(int(b.end_idx) for b in bursts)),
                n_bo_after=int(sum(1 for x in members if x >= t0)),
                pos_from_end=int(sum(1 for x in members if a_idx is not None and x > a_idx)),
                first_drought=int(longest.first_drought),
                distinct_pk=int(longest.distinct_pk),
                vol_spike=float(longest.max_bar_vol_ratio),
                peak_age=int(longest.peak_age_max),
                fr=fr, dd=dd,
                fp_up=fps[5.0]["up"], fp_down=fps[5.0]["down"],
                fp_both=fps[5.0]["both"], fp_none=fps[5.0]["none"],
                up4=fps[4.0]["up"], dn4=fps[4.0]["down"],
                up6=fps[6.0]["up"], dn6=fps[6.0]["down"],
                n_buy_bars=sum(fps[5.0].values()),
                atr_pct=float(M[t0]) if np.isfinite(M[t0]) else np.nan,
            ))
        # 自检:现状 spec 的买点必须全部出现在放宽 spec 里(放宽应为超集)
        lost = cur_tb - set(by_tb)
        base = _random_days(sym, win, s, e, BASE_N_DAYS, M)
        return sym, rows, base, sorted(lost)
    except Exception as ex:                                   # noqa: BLE001
        return sym, [], [], f"ERR {type(ex).__name__}: {ex}"


def main():
    syms = sorted(p.stem for p in DATA_DIR.glob("*.pkl"))
    for tag, (sd, ed) in WINDOWS.items():
        t0 = time.time()
        rows, base, lost, errs = [], [], [], []
        with Pool(24) as pool:
            for out in pool.imap_unordered(_one, [(s, sd, ed) for s in syms],
                                           chunksize=16):
                sym, r, b = out[0], out[1], out[2]
                extra = out[3] if len(out) > 3 else []
                if isinstance(extra, str):
                    errs.append((sym, extra))
                elif extra:
                    lost.append((sym, extra))
                rows.extend(r)
                base.extend(b)
        df = pd.DataFrame(rows)
        df.to_csv(HERE / f"stats_anchor_{tag}.csv", index=False)
        pd.DataFrame(base).to_csv(HERE / f"stats_anchor_base_{tag}.csv", index=False)
        g = df.group.value_counts().to_dict() if len(df) else {}
        print(f"[{tag}] 买点 {len(df)} {g} 票={df.symbol.nunique() if len(df) else 0} "
              f"因果={int(df.causal.sum()) if len(df) else 0} "
              f"基线日={len(base)} 现状买点丢失={len(lost)} 异常={len(errs)} "
              f"wall={time.time()-t0:.0f}s", flush=True)
        if lost:
            print("  ⚠ 丢失样本(放宽不是超集):", lost[:5], flush=True)
        if errs:
            print("  errs:", errs[:3], flush=True)


if __name__ == "__main__":
    main()
