"""S3: 下游(bb_v1 完整 pattern)对照 —— union / 交集 / 单 measure,含 distinct_pk 去重键之争。

UnionBODetector 在 repro 内组合两个库 BODetector(不改库代码),把同一 bar 上的两次
突破合成 **一个** BOEvent(bo 是点事件,同 bar 两个 event 会污染 burst.count 与
event_id)。去重键两种模式,正对应硬问题 1:
  naive:  (measure, pk_id)      —— 「high_pk 与 close_pk 是两个对象」
  bybar:  peak 的 bar index     —— 「同一根 bar 的两种测量 = 一个对象」

variants:
  base_high / base_close : 库 BODetector 原样(对照基准)
  wrap_high              : 自检 —— wrapper 单 measure 必须与 base_high 逐 bar 相同
  union_naive/union_bybar: 并集(用户设想的「信号更多」)
  inter                  : 交集(两口径都触发才算 bo)= 确认式合取,并集的反面

对每个 variant 扫 distinct_pk_min ∈ {3,4,5,6} 作计数匹配对照(不重标定就比 = 拿
「更多测量」比「同阈值 + 更大群体」,是混淆)。
"""
from __future__ import annotations

import pickle
import random
import sys
from dataclasses import replace
from multiprocessing import Pool
from pathlib import Path
from typing import ClassVar

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from path2.atoms.breakout import BODetector, BOEvent            # noqa: E402
from path2.calc.atr import FP_ATR_WINDOW, rolling_atr_pct_nanmedian  # noqa: E402
from path2.eval import (_first_passage_at, _ticker_seed,        # noqa: E402
                        match_first_passage, match_forward_returns)
from path2_apps.bb_v1.dag_spec import build_pattern             # noqa: E402
from path2_apps.bb_v1.params import Params, load_params                      # noqa: E402
from path2.dag.engine import analyze as engine_analyze          # noqa: E402
from path2_web.data import slice_window                         # noqa: E402

PKL_DIR = Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls")
START, END = "2021-01-01", "2026-03-08"
HORIZON = 40
FP_K = 5.0
RANDOM_DAYS = 12


class UnionBODetector:
    """并集/交集 bo 生产者。measures = 多个 peak_measure;mode ∈ {union, inter}。"""
    has_debug_hooks: ClassVar[bool] = False
    event_cls = BOEvent
    on_gate = None

    def __init__(self, measures, mode="union", dedup="bybar", nbhd_gap=6, **bo_kwargs):
        self.measures = list(measures)
        self.mode = mode
        self.dedup = dedup          # bybar | naive | nbhd
        self.nbhd_gap = nbhd_gap    # dedup="nbhd": bar 距 <= 此值视作同一个顶
        self.bo_kwargs = dict(bo_kwargs)
        self.bo_kwargs.pop("peak_measure", None)

    def _nbhd_map(self, per):
        """所有被突破过的 peak bar 做单链聚类(gap <= nbhd_gap 归一簇),返回 bar -> 簇代表。

        skeptic 的一锤定音判据:若按邻近去重后下游塌回单 measure 基线,则并集的收益
        全部来自「同一个局部顶被数两次」,而不是新结构。
        """
        bars = sorted({rp[0] for m in per for e in per[m].values() for rp in e.referenced_points})
        out, rep = {}, None
        prev = None
        for b in bars:
            if prev is None or b - prev > self.nbhd_gap:
                rep = b
            out[b] = rep
            prev = b
        return out

    def detect(self, df):
        per = {}
        for m in self.measures:
            det = BODetector(peak_measure=m, **self.bo_kwargs)
            per[m] = {e.start_idx: e for e in det.detect(df)}
        bars = set()
        if self.mode == "union":
            for m in self.measures:
                bars |= set(per[m])
        else:
            bars = set(per[self.measures[0]])
            for m in self.measures[1:]:
                bars &= set(per[m])

        nbhd = self._nbhd_map(per) if self.dedup == "nbhd" else None
        last = None
        for t in sorted(bars):
            evs = [(m, per[m][t]) for m in self.measures if t in per[m]]
            ids, refs = set(), {}
            for m, e in evs:
                for j, pid in enumerate(e.broken_peak_ids):
                    pk_bar = e.referenced_points[j][0]
                    if self.dedup == "naive":
                        key = (m, pid)
                    elif self.dedup == "nbhd":
                        key = nbhd[pk_bar]
                    else:
                        key = pk_bar
                    ids.add(key)
                    refs.setdefault(pk_bar, (pk_bar, e.referenced_points[j][1],
                                             f"pk{m[0]}{pid}"))
            base = evs[0][1]
            yield replace(
                base,
                drought=None if last is None else t - last,
                pk_count=len(ids),
                broken_peak_ids=tuple(sorted(hash(k) & 0xFFFFFF for k in ids)),
                peak_vol_max=max(e.peak_vol_max for _, e in evs),
                peak_age_max=max(e.peak_age_max for _, e in evs),
                referenced_points=tuple(refs[k] for k in sorted(refs)),
            )
            last = t


def make_spec(params, bo_detector=None):
    spec = build_pattern(params)
    if bo_detector is None:
        return spec
    nodes = tuple(replace(n, detector=bo_detector) if n.node_id == "bo" else n
                  for n in spec.nodes)
    return replace(spec, nodes=nodes)


def variants(p):
    kw = p.bo_kwargs()
    kw_nopm = {k: v for k, v in kw.items() if k != "peak_measure"}
    return {
        "base_high":   None,                                   # 库原样(peak=high)
        "base_close":  BODetector(peak_measure="close", **kw_nopm),
        "wrap_high":   UnionBODetector(["high"], "union", "bybar", **kw_nopm),
        "union_naive": UnionBODetector(["high", "close"], "union", "naive", **kw_nopm),
        "union_bybar": UnionBODetector(["high", "close"], "union", "bybar", **kw_nopm),
        # skeptic 的一锤定音对照:邻近(<= min_side_bars)视作同一个顶
        "union_nbhd":  UnionBODetector(["high", "close"], "union", "nbhd",
                                       nbhd_gap=p.bo.min_side_bars, **kw_nopm),
        # 公平起见,单 measure 也上同一把邻近去重尺子(否则是拿去重过的比没去重的)
        "base_high_nbhd": UnionBODetector(["high"], "union", "nbhd",
                                          nbhd_gap=p.bo.min_side_bars, **kw_nopm),
        "inter":       UnionBODetector(["high", "close"], "inter", "bybar", **kw_nopm),
    }


PK_GRID = [3, 4, 5, 6]


def process(f):
    """单股处理:返回 (rows, base_rows, selfcheck_ok) 或 None。"""
    try:
        with open(f, "rb") as fh:
            raw = pickle.load(fh)
        if not isinstance(raw, pd.DataFrame):
            return None
        win = slice_window(raw, START, END)
    except Exception:
        return None
    if len(win) < 300:
        return None
    sym = Path(f).stem
    hi, lo, cl = win["high"].values, win["low"].values, win["close"].values
    M = rolling_atr_pct_nanmedian(win["high"], win["low"], win["close"],
                                  FP_ATR_WINDOW).values
    n_bars = len(win)
    rows, base_rows = [], []
    bo_sets = {}
    try:
        p = load_params()
        p = replace(p, burst=replace(p.burst, distinct_pk_min=min(PK_GRID)))
        for vname, det in variants(p).items():
            spec = make_spec(p, det)
            res = engine_analyze(spec, win, p)
            bo_sets[vname] = {e.start_idx for e in res.events if isinstance(e, BOEvent)}
            for m in res.matches:
                rets = match_forward_returns(m, "tb", win, [HORIZON])
                fp = match_first_passage(m, "tb", win, HORIZON, k=FP_K, M=M)
                tb = m.node_index["tb"]
                rows.append(dict(symbol=sym, variant=vname,
                                 dpk=m.node_index["burst"].distinct_pk,
                                 tb_start=tb.start_idx, tb_end=tb.end_idx,
                                 date=str(pd.Timestamp(win["date"].iloc[tb.start_idx]).date()),
                                 mfr=rets[HORIZON],
                                 **{f"fp_{k}": v for k, v in fp.items()}))
    except Exception as e:
        print(f"skip {sym}: {type(e).__name__} {e}", file=sys.stderr)
        return None

    cand = [i for i in range(n_bars) if i + HORIZON < n_bars
            and np.isfinite(M[i]) and M[i] > 0]
    if cand:
        rng = np.random.default_rng(_ticker_seed(sym))
        for i in rng.choice(cand, size=min(RANDOM_DAYS, len(cand)), replace=False):
            i = int(i)
            base_rows.append(dict(
                symbol=sym,
                mfr=float(hi[i + 1:i + HORIZON + 1].max()) / float(cl[i]) - 1.0,
                fp=_first_passage_at(hi, lo, cl, M, i, HORIZON, FP_K)))
    return rows, base_rows, bo_sets.get("base_high") == bo_sets.get("wrap_high")


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    nproc = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    files = sorted(PKL_DIR.glob("*.pkl"))
    random.Random(20260831).shuffle(files)
    files = [str(x) for x in files[: n * 2]]

    rows, base_rows = [], []
    done = 0
    selfcheck_bad = 0
    with Pool(nproc) as pool:
        for out in pool.imap_unordered(process, files, chunksize=4):
            if out is None:
                continue
            r, b, ok = out
            rows += r
            base_rows += b
            selfcheck_bad += (0 if ok else 1)
            done += 1
            if done >= n:
                pool.terminate()
                break

    df = pd.DataFrame(rows)
    bs = pd.DataFrame(base_rows)
    outdir = Path(__file__).parent
    df.to_csv(outdir / "s3_downstream.csv", index=False)
    bs.to_csv(outdir / "s3_baseline.csv", index=False)

    print(f"样本股票数 = {done}  窗口 {START}~{END}  horizon={HORIZON} k={FP_K}")
    print(f"自检(wrapper 单 measure ≡ 库 BODetector)不一致股票数 = {selfcheck_bad}  (须为 0)")
    if len(bs):
        up = (bs.fp == "up").mean(); dn = (bs.fp == "down").mean()
        print(f"随机日基线: n={len(bs)} mfr_med={bs.mfr.median():+.4f} "
              f"FP up={up:.3f} down={dn:.3f} up-down={up-dn:+.3f}")
    print()
    if not len(df):
        print("no matches"); return
    print(f"{'variant':12s} {'pk':>3s} {'matches':>8s} {'stocks':>7s} {'mfr_med':>9s} "
          f"{'FPup':>6s} {'FPdn':>6s} {'up-dn':>7s}")
    for vname in ["base_high", "base_high_nbhd", "base_close", "union_naive",
                  "union_bybar", "union_nbhd", "inter"]:
        for pk in PK_GRID:
            sub = df[(df.variant == vname) & (df.dpk >= pk)]
            if not len(sub):
                print(f"{vname:12s} {pk:3d} {0:8d}")
                continue
            tot = sub[["fp_up", "fp_down", "fp_both", "fp_none"]].sum().sum()
            up = sub.fp_up.sum() / tot if tot else float("nan")
            dn = sub.fp_down.sum() / tot if tot else float("nan")
            print(f"{vname:12s} {pk:3d} {len(sub):8d} {sub.symbol.nunique():7d} "
                  f"{sub.mfr.median():+9.4f} {up:6.3f} {dn:6.3f} {up-dn:+7.3f}")


if __name__ == "__main__":
    main()
