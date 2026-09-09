"""锚语义放宽的全宇宙抽取:现状(锚簇末 bo) vs 放宽(锚簇内任一 bo),两窗。

口径完全照抄同目录 extract_wide.py(窗口公式 / volume 与 price 过滤 / sample_window
截取 / 官方 label API / 随机日基线),两处不同:
  1. 参数**不放宽任何闸**——就是 params.yaml 的 SSoT 底座。本研究改的是边,不是闸。
  2. 跑两份 spec:
       cur  = build_pattern(params)                      现状,1 条边,锚 burst.last_bo
       wide = 同 nodes,edges 换成两条:
              ContainmentEdge(burst, bo) + TemporalEdge(bo, tb, anchor_bo_id)
     等价性前提(逐条核过):burst 跨度 = 首成员.start..末成员.end、members 是 bo 流里
     按 start 排序的连续片段、BOEvent.is_point → 「几何落在 burst 跨度内」严格等价于
     「是该 burst 的成员」。

样本单位与去重(照 stats 的键):(symbol, tb_id, bo_id)。放宽后同一个 tb 会被多个 burst
前缀同时包含 → 多行 match 指向同一个买点。**买点才是物理量**,所以每行额外带:
  n_burst_variants  该 (tb, bo) 下有几个 burst 前缀成立(现状恒为 1)
  is_rep            1 = 该 (tb, bo) 的代表行(取 burst_count 最小者 = 最早确认的前缀,
                    并列时取 burst_id 字典序最小);过滤 is_rep==1 即得买点级样本
group: 原有 = 该 tb_id 在 cur 里也命中;新增 = 只在 wide 里命中。
own_burst_*: 该 tb 的锚 bo 所"自带"的那个前缀(last_bo == anchor bo)在现状下的状况——
  回答「新增买点是真的从无到有,还是本来就有别的 burst 能锚上」。

用法: uv run python .../repro/extract_anchor_widen.py
"""
from __future__ import annotations

import sys
import time
from dataclasses import replace
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from path2.calc.atr import FP_ATR_WINDOW, rolling_atr_pct_nanmedian   # noqa: E402
from path2.dag.edges import ContainmentEdge, TemporalEdge             # noqa: E402
from path2.dag.engine import analyze as dag_analyze, run_streams      # noqa: E402
from path2.eval import (_first_passage_at, _ticker_seed,              # noqa: E402
                        match_first_passage, match_forward_drawdowns,
                        match_forward_returns)
from path2_apps.bb_v1.dag_spec import build_pattern                   # noqa: E402
from path2_apps.bb_v1.params import load_params                       # noqa: E402
from path2_web.data import slice_window                               # noqa: E402
from path2_web.serialize import _resolve_end_events                   # noqa: E402

DATA_DIR = Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls")
OUT_DIR = Path(__file__).parent
RATIO = 1.65
HEAD_BUFFER = 63
LABEL_HORIZON = 40
FP_K = 5.0
PRICE_MIN, PRICE_MAX = 0.5, 30.0
VOLUME_MIN = 10000.0
BASE_N_DAYS = 20
WORKERS = 24

WINDOWS = {"w2025": ("2025-01-01", "2026-01-01"),
           "w2024": ("2024-01-01", "2025-01-01")}


def build_widened(params):
    spec = build_pattern(params)
    return replace(spec, edges=(
        ContainmentEdge("burst", "bo"),
        TemporalEdge("bo", "tb", min_gap=1, max_gap=params.tb.max_span,
                     anchor_field="anchor_bo_id"),
    ))


def _random_days(sym, win, start_ts, end_ts, n_days, M):
    """照抄 extract_wide._random_days(同一批随机日、同一 seed → 两份研究的基线可并排)。"""
    hi_a, lo_a, cl_a = (win["high"].to_numpy(float), win["low"].to_numpy(float),
                        win["close"].to_numpy(float))
    dts = win["date"].values
    n = len(win)
    cand = [i for i in range(n)
            if start_ts <= pd.Timestamp(dts[i]) <= end_ts and i + LABEL_HORIZON < n]
    if not cand:
        return []
    rng = np.random.default_rng(_ticker_seed(sym))
    picks = rng.choice(cand, size=min(n_days, len(cand)), replace=False)
    out = []
    for t in picks:
        t = int(t)
        st = _first_passage_at(hi_a, lo_a, cl_a, M, t, LABEL_HORIZON, FP_K)
        if st is None:
            continue
        st4 = _first_passage_at(hi_a, lo_a, cl_a, M, t, LABEL_HORIZON, 4.0)
        st6 = _first_passage_at(hi_a, lo_a, cl_a, M, t, LABEL_HORIZON, 6.0)
        out.append(dict(symbol=sym, t=t, date=str(dts[t])[:10], fp=st,
                        fp4=st4, fp6=st6,
                        fr=float(hi_a[t + 1:t + LABEL_HORIZON + 1].max()) / cl_a[t] - 1.0,
                        dd=float(lo_a[t + 1:t + LABEL_HORIZON + 1].min()) / cl_a[t] - 1.0,
                        atr_pct=float(M[t])))
    return out


def _collect(res, win, start_ts, end_ts, lo, hi, M, sym):
    """一份 spec 的 match → {(tb_id, bo_id): [每个 burst 前缀一条 raw]}(已过窗口/价格闸)。"""
    acc: dict = {}
    for m in res.matches:
        events = _resolve_end_events(m, "tb")
        if not any(start_ts <= win["date"].iat[ev.start_idx] <= end_ts for ev in events):
            continue
        closes = [float(win["close"].iat[ev.start_idx]) for ev in events]
        if not any(PRICE_MIN <= c <= PRICE_MAX for c in closes):
            continue
        tb, burst = m.node_index["tb"], m.node_index["burst"]
        acc.setdefault((tb.instance_id, tb.anchor_bo_id), []).append((m, tb, burst))
    return acc


def _one(args):
    sym, start_date, end_date = args
    try:
        start_ts, end_ts = pd.Timestamp(start_date), pd.Timestamp(end_date)
        buf_start = start_ts - pd.Timedelta(days=round(HEAD_BUFFER * RATIO))
        buf_end = end_ts + pd.Timedelta(days=round(LABEL_HORIZON * RATIO))
        df = pd.read_pickle(DATA_DIR / f"{sym}.pkl")
        win = slice_window(df, buf_start.date(), buf_end.date())
        if len(win) == 0:
            return sym, [], [], None
        scan_win = win[(win["date"] >= start_ts) & (win["date"] <= end_ts)]
        if len(scan_win) == 0 or scan_win["volume"].mean() <= VOLUME_MIN:
            return sym, [], [], None

        params = load_params()
        spec_cur, spec_wide = build_pattern(params), build_widened(params)
        res_cur = dag_analyze(spec_cur, win, params)
        res_wide = dag_analyze(spec_wide, win, params)
        lo = int(win["date"].searchsorted(start_ts, "left"))
        hi = int(win["date"].searchsorted(end_ts, "right")) - 1
        M = rolling_atr_pct_nanmedian(win["high"], win["low"], win["close"],
                                      FP_ATR_WINDOW).values

        acc_cur = _collect(res_cur, win, start_ts, end_ts, lo, hi, M, sym)
        acc_wide = _collect(res_wide, win, start_ts, end_ts, lo, hi, M, sym)
        cur_tbs = {tb for tb, _ in acc_cur}

        # 该 sym 全部 burst 事件(未过 where)→ 供 own_burst_* 判断
        streams = run_streams(spec_cur, win, params)
        bnode = next(n for n in spec_cur.nodes if n.node_id == "burst")
        burst_by_lastbo = {}
        for b in streams.get("burst", []):
            if b.members:
                burst_by_lastbo[b.members[-1].instance_id] = b

        rows = []
        for (tb_id, bo_id), items in acc_wide.items():
            items = sorted(items, key=lambda x: (x[2].count, x[2].instance_id))
            n_var = len(items)
            own = burst_by_lastbo.get(bo_id)
            own_ok = (own is not None
                      and all(fn(own) for _, fn in bnode.where))
            for rank, (m, tb, burst) in enumerate(items):
                t0 = tb.start_idx
                fr = match_forward_returns(m, "tb", win, [LABEL_HORIZON],
                                           sample_window=(lo, hi))[LABEL_HORIZON]
                dd = match_forward_drawdowns(m, "tb", win, [LABEL_HORIZON],
                                             sample_window=(lo, hi))[LABEL_HORIZON]
                fp = match_first_passage(m, "tb", win, LABEL_HORIZON, k=FP_K,
                                         sample_window=(lo, hi), M=M)
                # 三 k 稳健性(FC-004 惯例:k=4/5/6 同向才算数)
                fp4 = match_first_passage(m, "tb", win, LABEL_HORIZON, k=4.0,
                                          sample_window=(lo, hi), M=M)
                fp6 = match_first_passage(m, "tb", win, LABEL_HORIZON, k=6.0,
                                          sample_window=(lo, hi), M=M)
                rows.append(dict(
                    symbol=sym, match_id=m.match_id,
                    tb_id=tb_id, bo_id=bo_id, burst_id=burst.instance_id,
                    group=("原有" if tb_id in cur_tbs else "新增"),
                    n_burst_variants=n_var, is_rep=int(rank == 0),
                    # 锚 bo 自带的那个前缀(last_bo == anchor bo)在现状下的状况
                    own_burst_exists=int(own is not None),
                    own_burst_qualified=int(bool(own_ok)),
                    # burst 前缀几何:锚 bo 在簇内的位置(混杂排查用)
                    burst_count=int(burst.count),
                    bo_rank_in_burst=next(
                        (i + 1 for i, mm in enumerate(burst.members)
                         if mm.instance_id == bo_id), -1),
                    bars_bo_to_burst_end=int(burst.end_idx - next(
                        (mm.end_idx for mm in burst.members
                         if mm.instance_id == bo_id), burst.end_idx)),
                    first_bo_idx=int(burst.members[0].end_idx) if burst.members else -1,
                    last_bo_idx=int(burst.members[-1].end_idx) if burst.members else -1,
                    tb_start=int(t0), tb_end=int(tb.end_idx),
                    tb_date=str(win["date"].iat[t0])[:10],
                    first_drought=int(burst.first_drought),
                    distinct_pk=int(burst.distinct_pk),
                    max_bar_vol_ratio=float(burst.max_bar_vol_ratio),
                    peak_age_max=int(burst.peak_age_max),
                    fr=fr, dd=dd,
                    fp_up=fp["up"], fp_down=fp["down"],
                    fp_both=fp["both"], fp_none=fp["none"],
                    n_buy_bars=sum(fp.values()),
                    fp4_up=fp4["up"], fp4_down=fp4["down"],
                    fp6_up=fp6["up"], fp6_down=fp6["down"],
                    atr_pct=float(M[t0]) if np.isfinite(M[t0]) else np.nan,
                    close_at_buy=float(win["close"].iat[t0]),
                ))
        # 自检:cur 的每个买点必须原样出现在 wide 里(放宽只增不减)
        lost = sorted(cur_tbs - {tb for tb, _ in acc_wide})
        return sym, rows, _random_days(sym, win, start_ts, end_ts, BASE_N_DAYS, M), lost
    except Exception as e:                                    # noqa: BLE001
        return sym, [], [], f"ERR {type(e).__name__}: {e}"


def main():
    syms = sorted(p.stem for p in DATA_DIR.glob("*.pkl"))
    print(f"universe = {len(syms)} 只", flush=True)
    for tag, (sd, ed) in WINDOWS.items():
        t0 = time.time()
        rows, base, lost_all, errs = [], [], [], []
        with Pool(WORKERS) as pool:
            for i, (sym, r, b, lost) in enumerate(
                    pool.imap_unordered(_one, [(s, sd, ed) for s in syms], chunksize=16)):
                if isinstance(lost, str):
                    errs.append((sym, lost))
                elif lost:
                    lost_all.extend((sym, x) for x in lost)
                rows.extend(r)
                base.extend(b)
                if (i + 1) % 2000 == 0:
                    print(f"  [{tag}] {i+1}/{len(syms)} rows={len(rows)} "
                          f"{time.time()-t0:.0f}s", flush=True)
        df = pd.DataFrame(rows)
        df.to_csv(OUT_DIR / f"anchor_{tag}.csv", index=False)
        pd.DataFrame(base).to_csv(OUT_DIR / f"anchor_baseline_{tag}.csv", index=False)
        rep = df[df.is_rep == 1] if len(df) else df
        print(f"\n[{tag}] match 行={len(df)} 买点(is_rep)={len(rep)} "
              f"票={df['symbol'].nunique() if len(df) else 0} "
              f"基线日={len(base)} errors={len(errs)} wall={time.time()-t0:.0f}s")
        if len(rep):
            g = rep.groupby("group")
            print(f"  买点分组: " + " / ".join(f"{k} {len(v)}" for k, v in g))
            print(f"  ★ 自检 放宽后丢失的原有买点 = {len(lost_all)}(必须为 0)")
            new = rep[rep.group == "新增"]
            if len(new):
                print(f"  ★ 新增买点里「锚 bo 自带前缀存在但没过闸」= "
                      f"{int((new.own_burst_exists == 1).sum())}/{len(new)};"
                      f"「自带前缀根本不存在」= {int((new.own_burst_exists == 0).sum())}")
                print(f"  ★ 新增买点里自带前缀已过闸的 = "
                      f"{int((new.own_burst_qualified == 1).sum())}(应为 0)")
        if len(rep):
            print(f"  {'组':<6}{'买点':>6}{'买点日':>7}"
                  f"{'FPR k=4':>9}{'FPR k=5':>9}{'FPR k=6':>9}{'fr 中位':>10}{'dd 中位':>10}")
            for g in ("原有", "新增"):
                v = rep[rep.group == g]
                if not len(v):
                    continue
                def _r(u, d):
                    n = v[u].sum() + v[d].sum()
                    return v[u].sum() / n if n else float("nan")
                print(f"  {g:<6}{len(v):>6}{int(v.n_buy_bars.sum()):>7}"
                      f"{_r('fp4_up','fp4_down'):>9.3f}{_r('fp_up','fp_down'):>9.3f}"
                      f"{_r('fp6_up','fp6_down'):>9.3f}"
                      f"{v.fr.median():>+10.4f}{v.dd.median():>+10.4f}")
            bs = pd.DataFrame(base)
            for kk, col in (("k=4", "fp4"), ("k=5", "fp"), ("k=6", "fp6")):
                n = (bs[col] == "up").sum() + (bs[col] == "down").sum()
                print(f"  随机日基线(未层匹配,仅供 stats 层匹配用) {kk}: "
                      f"{(bs[col]=='up').sum()/n:.3f}  n={int(n)}")
        if errs:
            print("  errs sample:", errs[:3])


if __name__ == "__main__":
    main()
