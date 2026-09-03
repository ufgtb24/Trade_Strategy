"""「一次多值」vs「逐档真扫」逐 event 对拍(pipeline-structure.md §B 的等价性证据)。

四项实验(子集股票,单进程):
  E1 gap_max × min_bos:一次遍历 bo 序列、按每个 g 维护簇首指针,导出所有 g 的前缀族;
     再按 count ≥ m 过滤 —— 对拍 BurstDetector(g, m) 的输出(逐字段)。
  E2 stop_confirm_bars × big_rise_k:一次 phase-1 遍历 + 每 K 一次 phase-2 遍历,导出全部
     (K, k) 组合的 (confirm, end, outcome) —— 对拍 evaluate_throwback(K, k) 逐 burst。
  E3 min_relative_height / exceed_threshold:证明「非子集」—— 严档 BO 不在松档里的个数,
     以及共同 BO 的 drought 字段是否漂移(状态机分叉的直接证据)。
  E4 端到端:反转循环(bo 一次 → burst 多 g → tb 多 (K,k))得到的每格 match 集合,对拍
     engine.analyze(build_pattern(params_cell)) 的 match 集合(随机抽格)。

用法:改 main() 起始参数,`uv run python docs/research/2026-08-24_region-search-budget/repro/multi_value_equiv.py`
"""
from __future__ import annotations

import itertools
import json
import pathlib
import random
import subprocess
import sys
import time
from dataclasses import replace

REPO = pathlib.Path(subprocess.check_output(
    ["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO))

import pandas as pd  # noqa: E402

from path2 import config  # noqa: E402
from path2.runner import run  # noqa: E402
from path2.calc.atr import calculate_atr  # noqa: E402
from path2.calc.measure import measure_at  # noqa: E402
from path2.calc.volume import calculate_vol_ratio  # noqa: E402
from path2.atoms.breakout import BODetector, BurstDetector  # noqa: E402
from path2.atoms import throwback_v1 as tbm  # noqa: E402
from path2.dag.engine import analyze  # noqa: E402
from path2_web.data import slice_window  # noqa: E402
from path2_web.scan import _list_pkls, TRADING_TO_CALENDAR_RATIO  # noqa: E402
from path2_apps.bb_v1.dag_spec import build_pattern  # noqa: E402
from path2_apps.bb_v1.params import Params  # noqa: E402


# ───────────────────────── 多值实现(实验用,不进正式代码) ─────────────────────────

def bursts_multi_g(bos, df, gs, vol_baseline_period):
    """一次遍历导出所有 g 的前缀族(min_bos=1)。返回 {g: [BurstEvent]}(与 detect 同序)。
    依据 breakout.py:131-160:簇首 = 最近一次 gap > g 的位置;前缀实例 = seq[head:k+1]。"""
    det = BurstDetector(gap_max=0, min_bos=1, vol_baseline_period=vol_baseline_period)  # 只借 _make_burst
    seq = sorted(bos, key=lambda e: (e.start_idx, e.end_idx))
    vr = calculate_vol_ratio(df["volume"], vol_baseline_period)
    heads = {g: 0 for g in gs}
    out = {g: [] for g in gs}
    for k in range(len(seq)):
        if k > 0:
            gap = seq[k].start_idx - seq[k - 1].start_idx
            for g in gs:
                if gap > g:
                    heads[g] = k
        for g in gs:
            out[g].append(det._make_burst(seq[heads[g]: k + 1], vr))
    for g in gs:
        out[g].sort(key=lambda e: (e.end_idx, e.start_idx))
    return out


def burst_key(b):
    return (b.start_idx, b.end_idx, b.count, b.distinct_pk, round(b.max_bar_vol_ratio, 12),
            b.first_drought, b.peak_age_max, tuple(m.start_idx for m in b.members))


def tb_multi(df, bo_idx, anchor, atr, Ks, ks, *, max_start_gap, max_window,
             judged_measure, reference_measure, scb_mode):
    """一次 phase-1 遍历 + 每 K 一次 phase-2 遍历 → {(K, k): (confirm, end, outcome) | None}。
    依据 throwback_v1.py:_find_confirm_idx / _find_end_idx 的语句顺序:
      每根 i:① break(K/k 无关)→ ② trough/rising 更新(K/k 无关)→ ③ rise≥k·atr(只依赖 k)
      → ④ bars_ok(K) ∧ stop signal(只依赖 K)→ ⑤ base_min 更新(K/k 无关)。
    故 confirm_K = 首个满足 ④ 的 i;k 的「死亡点」death_k = 首个满足 ③ 的 i;
    (K,k) 有事件 ⟺ confirm_K 存在 ∧ confirm_K < death_k(③ 先于 ④,同根即死)。"""
    n = len(df)
    if bo_idx < 1 or bo_idx >= n or atr <= 0.0:
        return {(K, k): None for K in Ks for k in ks}
    end = min(bo_idx + max_start_gap, n - 1)
    trough = bo_idx + 1
    rising = 0
    base_min = float("inf")
    confirm = {}            # K -> (i, trough)
    death = {}              # k -> i
    pending = set(Ks)
    for i in range(bo_idx + 1, end + 1):
        if measure_at(df, i, judged_measure) < anchor:
            break
        m_i = measure_at(df, i, reference_measure)
        if m_i < measure_at(df, trough, reference_measure):
            trough = i
            rising = 0
        elif scb_mode == "rising":
            if measure_at(df, i, judged_measure) >= measure_at(df, i - 1, judged_measure):
                rising += 1
            else:
                rising = 0
        if i >= bo_idx + 2:
            rise = float(df["high"].iat[i]) - base_min
            for k in ks:
                if k not in death and rise >= k * atr:
                    death[k] = i
        if pending:
            has_sig = None
            for K in sorted(pending):
                bars_ok = (rising >= K) if scb_mode == "rising" else (i - trough >= K)
                if not bars_ok:
                    continue
                if has_sig is None:
                    has_sig = any(tbm._has_stop_signal(df, t) for t in range(trough, i + 1))
                if has_sig:
                    confirm[K] = (i, trough)
                    pending.discard(K)
        lo_i = float(df["low"].iat[i])
        if lo_i < base_min:
            base_min = lo_i
    out = {}
    for K in Ks:
        if K not in confirm:
            for k in ks:
                out[(K, k)] = None
            continue
        ci, ti = confirm[K]
        # phase 2:一次遍历记录 (i, rise_i) 与首个 break/weak 退出
        end_scan = min(ci + max_window, n - 1)
        bm = float(df["low"].iloc[ti: ci + 1].min())
        trough_price = measure_at(df, ti, reference_measure)
        rises = []
        first_exit = None
        for i in range(ci + 1, end_scan + 1):
            ms = measure_at(df, i, judged_measure)
            if ms < anchor:
                first_exit = (i - 1, "break"); break
            if ms < trough_price:
                first_exit = (i - 1, "weak"); break
            rises.append((i, float(df["high"].iat[i]) - bm))
            lo_i = float(df["low"].iat[i])
            if lo_i < bm:
                bm = lo_i
        for k in ks:
            if k in death and death[k] <= ci:
                out[(K, k)] = None
                continue
            res = None
            for i, r in rises:
                if r >= k * atr:
                    res = (ci, i - 1, "rise"); break
            if res is None:
                res = (ci, first_exit[0], first_exit[1]) if first_exit else (ci, end_scan, "timeout")
            out[(K, k)] = res
    return out


def tb_ref(df, bo, anchor, K, k, *, max_start_gap, max_window, atr_window,
           judged_measure, reference_measure, scb_mode):
    r = tbm.evaluate_throwback(bo, df, anchor=anchor, max_start_gap=max_start_gap,
                               max_window=max_window, atr_window=atr_window,
                               big_rise_k=k, stop_confirm_bars=K,
                               judged_measure=judged_measure,
                               reference_measure=reference_measure, scb_mode=scb_mode)
    return None if r is None else (r.start_idx, r.end_idx, r.outcome)


def span_min_anchor(df, burst, reference_measure):
    return min(measure_at(df, i, reference_measure) for i in range(burst.start_idx, burst.end_idx + 1))


def main(E4B_WHERES=None) -> None:
    # ===== 参数 =====
    DATA_DIR = "/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls"
    TICKER_REGEX = "^A[A-C]"
    START_DATE, END_DATE = "2024-01-01", "2026-01-01"
    HEAD_BUFFER, LABEL_HORIZON = 250, 40
    REF_SCAN = REPO / "outputs/path2_web/scans/20260818T223413.json"
    WIDE_OVERRIDES = dict(burst=dict(first_drought_min=0, distinct_pk_min=1, vol_spike_min=0),
                          tb=dict(max_day_drop_pct=None))
    GS = [4, 8, 12, 20]
    MS = [1, 2, 3, 4]
    KS_SCB = [0, 1, 2, 3, 4]
    KS_RISE = [3.0, 5.0, 8.0, 12.0]
    MRH = [0.1, 0.15, 0.2, 0.3]
    EXC = [0.001, 0.003, 0.01, 0.03]
    E4_CELLS = 16            # 端到端随机抽格数
    E4B_CELLS = 64           # E4b 6 维随机抽格数(另加 4 维 16 角点)
    SEED = 0
    # ==================
    config.set_runtime_checks(False)   # 实验路径手动分段,不经 annotate,关掉 run() 的重复对象检查
    snap = json.loads(REF_SCAN.read_text())["per_pattern"]["bb_v1"]["params_snapshot"]
    for s2, kv in WIDE_OVERRIDES.items():
        snap[s2].update(kv)
    base = Params.from_dict(snap)
    start_ts, end_ts = pd.to_datetime(START_DATE), pd.to_datetime(END_DATE)
    buf_start = str((start_ts - pd.Timedelta(days=round(HEAD_BUFFER * TRADING_TO_CALENDAR_RATIO))).date())
    buf_end = str((end_ts + pd.Timedelta(days=round(LABEL_HORIZON * TRADING_TO_CALENDAR_RATIO))).date())
    wins = []
    for pk in _list_pkls(DATA_DIR, TICKER_REGEX):
        w = slice_window(pd.read_pickle(pk), buf_start, buf_end)
        if len(w) > 300:
            wins.append((pk.stem, w))
    print(f"stocks={len(wins)}")

    # ATR 一次预算(对拍双方共用;与逐候选重算的等价性由 profile_stages.py 断言)
    atr_cache = {}
    orig_atr_at = tbm._atr_at

    def _cached_atr_at(df, idx, period):
        key = (id(df), period)
        if key not in atr_cache:
            atr_cache[key] = calculate_atr(df["high"], df["low"], df["close"], period).to_numpy()
        v = float(atr_cache[key][idx])
        return v if v == v else 0.0
    tbm._atr_at = _cached_atr_at

    tb_kw = dict(max_start_gap=base.tb.max_start_gap, max_window=base.tb.max_window,
                 judged_measure=base.tb.judged_measure, reference_measure=base.tb.reference_measure,
                 scb_mode=base.tb.scb_mode)

    # ---------- E1 ----------
    t0 = time.perf_counter()
    e1_mismatch = 0; e1_cmp = 0
    bo_cache = {}
    for sym, w in wins:
        bos = list(run(BODetector(**base.bo_kwargs()), w))
        bo_cache[sym] = bos
        multi = bursts_multi_g(bos, w, GS, base.burst.vol_baseline_period)
        for g in GS:
            for m in MS:
                derived = [burst_key(b) for b in multi[g] if b.count >= m]
                ref = [burst_key(b) for b in run(BurstDetector(gap_max=g, min_bos=m,
                                                               vol_baseline_period=base.burst.vol_baseline_period), bos, w)]
                e1_cmp += 1
                if derived != ref:
                    e1_mismatch += 1
    print(f"E1 gap_max×min_bos: {e1_cmp} (stock,g,m) 对拍, mismatch={e1_mismatch}  [{time.perf_counter()-t0:.1f}s]")

    # ---------- E2 ----------
    t0 = time.perf_counter()
    e2_cmp = e2_mismatch = 0; e2_nonnull = 0; n_bursts = 0; n_distinct_anchor = 0
    for sym, w in wins:
        bos = bo_cache[sym]
        bursts = list(run(BurstDetector(gap_max=8, min_bos=1, vol_baseline_period=63), bos, w))
        seen = set()
        for b in bursts:
            n_bursts += 1
            anchor = span_min_anchor(w, b, base.tb.reference_measure)
            key = (b.members[-1].end_idx, anchor)
            if key in seen:
                continue
            seen.add(key); n_distinct_anchor += 1
            atr = _cached_atr_at(w, b.members[-1].end_idx - 1, base.tb.atr_window)
            multi = tb_multi(w, b.members[-1].end_idx, anchor, atr, KS_SCB, KS_RISE, **tb_kw)
            for K in KS_SCB:
                for k in KS_RISE:
                    ref = tb_ref(w, b.members[-1], anchor, K, k, atr_window=base.tb.atr_window, **tb_kw)
                    e2_cmp += 1
                    e2_nonnull += ref is not None
                    if ref != multi[(K, k)]:
                        e2_mismatch += 1
                        if e2_mismatch <= 5:
                            print("   E2 mismatch", sym, b.members[-1].end_idx, K, k, ref, multi[(K, k)])
    print(f"E2 stop_confirm_bars×big_rise_k: bursts={n_bursts} distinct(last_bo,anchor)={n_distinct_anchor} "
          f"{e2_cmp} 组合对拍, 非空={e2_nonnull}, mismatch={e2_mismatch}  [{time.perf_counter()-t0:.1f}s]")

    # ---------- E3 ----------
    t0 = time.perf_counter()
    def bo_sets(field, levels):
        rows = []
        for sym, w in wins:
            per = {}
            for lv in levels:
                kw = base.bo_kwargs(); kw[field] = lv
                per[lv] = {e.start_idx: e.drought for e in run(BODetector(**kw), w)}
            rows.append(per)
        return rows
    for field, levels, loose_first in (("min_relative_height", MRH, True), ("exceed_threshold", EXC, True)):
        rows = bo_sets(field, levels)
        tot_strict = 0; not_in_loose = 0; drought_drift = 0; common = 0
        for per in rows:
            for a, b in zip(levels[:-1], levels[1:]):     # a 松 b 严
                sa, sb = per[a], per[b]
                tot_strict += len(sb)
                not_in_loose += sum(1 for i in sb if i not in sa)
                for i in sb:
                    if i in sa:
                        common += 1
                        drought_drift += sa[i] != sb[i]
        print(f"E3 {field}: 相邻档(松→严)严档 BO 总数={tot_strict}, 不在松档里={not_in_loose} "
              f"({not_in_loose/max(1,tot_strict):.1%}); 共同 BO={common}, drought 漂移={drought_drift} "
              f"({drought_drift/max(1,common):.1%})  [{time.perf_counter()-t0:.1f}s]")

    # ---------- E4 ----------
    t0 = time.perf_counter()
    rng = random.Random(SEED)
    cells = [(g, m, K, k) for g in GS for m in MS for K in KS_SCB for k in KS_RISE]
    picked = rng.sample(cells, E4_CELLS)
    # 反转循环:每股 bo 一次 → burst 多 g → tb 多 (K,k)(按 (last_bo, anchor) 记忆化)
    derived = {c: set() for c in picked}
    for sym, w in wins:
        bos = bo_cache[sym]
        multi_b = bursts_multi_g(bos, w, GS, base.burst.vol_baseline_period)
        memo = {}
        for g in GS:
            for b in multi_b[g]:
                anchor = span_min_anchor(w, b, base.tb.reference_measure)
                lb = b.members[-1].end_idx
                key = (lb, anchor)
                if key not in memo:
                    atr = _cached_atr_at(w, lb - 1, base.tb.atr_window)
                    memo[key] = tb_multi(w, lb, anchor, atr, KS_SCB, KS_RISE, **tb_kw)
                for (g2, m, K, k) in picked:
                    if g2 != g or b.count < m:
                        continue
                    r = memo[key][(K, k)]
                    if r is not None:
                        derived[(g, m, K, k)].add((sym, lb, b.start_idx, r[0], r[1], r[2]))
    t_derived = time.perf_counter() - t0
    # 逐格真跑 engine.analyze
    t0 = time.perf_counter()
    e4_mismatch = 0
    for (g, m, K, k) in picked:
        p = replace(base, burst=replace(base.burst, gap_max=g, min_bos=m),
                    tb=replace(base.tb, stop_confirm_bars=K, big_rise_k=k))
        spec = build_pattern(p)
        got = set()
        n_tb = n_match = 0
        for sym, w in wins:
            res = analyze(spec, w, p)
            n_match += len(res.matches)
            for mt in res.matches:
                b = mt.node_index["burst"]; tb = mt.node_index["tb"]
                got.add((sym, b.members[-1].end_idx, b.start_idx, tb.start_idx, tb.end_idx, tb.outcome))
            n_tb += sum(1 for e in res.events if type(e).__name__ == "ThrowbackEventV1")
        ok = got == derived[(g, m, K, k)]
        e4_mismatch += not ok
        print(f"   E4 cell g={g} m={m} K={K} k={k}: analyze matches={n_match} tb_events={n_tb} "
              f"derived={len(derived[(g, m, K, k)])} {'OK' if ok else 'MISMATCH'}")
    print(f"E4 端到端: {len(picked)} 格, mismatch={e4_mismatch}; 反转循环导出全部 {len(cells)} 格耗时 {t_derived:.1f}s "
          f"vs 逐格 analyze {len(picked)} 格耗时 {time.perf_counter()-t0:.1f}s(ATR 已缓存)")

    # ---------- E4b:6 维 + 最终 where 配置(params.yaml 当前值)+ revert 毒药闸 ----------
    t0 = time.perf_counter()
    E4B_WHERES = E4B_WHERES or [("yaml", dict(first_drought_min=40, distinct_pk_min=3, vol_spike_min=10, peak_age_min=125), 0.20),
                                ("dataclass-default", dict(first_drought_min=20, distinct_pk_min=4, vol_spike_min=8, peak_age_min=125), 0.20)]
    for WHERE_TAG, YAML_WHERE, MAX_DAY_DROP in E4B_WHERES:
      rng = random.Random(SEED + 1)
      cells6 = [(a, b, g, m, K, k) for a in MRH for b in EXC for g in GS for m in MS for K in KS_SCB for k in KS_RISE]
      corners4 = [(base.bo.min_relative_height, base.bo.exceed_threshold, g, m, K, k)
                  for g in (GS[0], GS[-1]) for m in (MS[0], MS[-1]) for K in (KS_SCB[0], KS_SCB[-1]) for k in (KS_RISE[0], KS_RISE[-1])]
      picked6 = rng.sample(cells6, E4B_CELLS) + corners4
      bo_lv_cache = {}
      def bo_of(sym, w, a, b):
          key = (sym, a, b)
          if key not in bo_lv_cache:
              kw = base.bo_kwargs(); kw["min_relative_height"] = a; kw["exceed_threshold"] = b
              bo_lv_cache[key] = list(run(BODetector(**kw), w))
          return bo_lv_cache[key]
      e4b_mismatch = 0; e4b_rows = []
      for cell in picked6:
          a, b, g, m, K, k = cell
          p = replace(base, bo=replace(base.bo, min_relative_height=a, exceed_threshold=b),
                      burst=replace(base.burst, gap_max=g, min_bos=m, **YAML_WHERE),
                      tb=replace(base.tb, stop_confirm_bars=K, big_rise_k=k, max_day_drop_pct=MAX_DAY_DROP))
          spec = build_pattern(p)
          where_fns = [fn for _, fn in spec.nodes[1].where]          # burst node 的 where(与 _solve.py:231-232 同一 fn)
          derived = set(); got = set(); n_tb_a = 0
          for sym, w in wins:
              bos = bo_of(sym, w, a, b)
              mb = bursts_multi_g(bos, w, [g], base.burst.vol_baseline_period)[g]
              memo = {}
              for bst in mb:
                  if bst.count < m or not all(fn(bst) for fn in where_fns):
                      continue
                  lb = bst.members[-1].end_idx
                  anchor = span_min_anchor(w, bst, base.tb.reference_measure)
                  key = (lb, anchor)
                  if key not in memo:
                      atr = _cached_atr_at(w, lb - 1, base.tb.atr_window) if lb >= 1 else 0.0
                      memo[key] = tb_multi(w, lb, anchor, atr, [K], [k], **tb_kw)
                  r = memo[key][(K, k)]
                  if r is None:
                      continue
                  if tbm._revert_max_day_drop(w, lb, r[0]) >= MAX_DAY_DROP:   # 毒药闸按 (anchor, confirm_K) 判定
                      continue
                  derived.add((sym, lb, bst.start_idx, r[0], r[1], r[2]))
              res = analyze(spec, w, p)
              n_tb_a += sum(1 for e in res.events if type(e).__name__ == "ThrowbackEventV1")
              for mt in res.matches:
                  bb, tb = mt.node_index["burst"], mt.node_index["tb"]
                  got.add((sym, bb.members[-1].end_idx, bb.start_idx, tb.start_idx, tb.end_idx, tb.outcome))
          ok = got == derived
          e4b_mismatch += not ok
          e4b_rows.append((cell, len(got), n_tb_a, ok))
          if not ok:
              print("   E4b MISMATCH", cell, len(got), len(derived), sorted(got ^ derived)[:5])
      print(f"E4b[{WHERE_TAG} where={YAML_WHERE} day_drop={MAX_DAY_DROP}] 6 维: {len(picked6)} 格({E4B_CELLS} 随机 + {len(corners4)} 个 4 维角点), "
            f"mismatch={e4b_mismatch}, analyze match 数 min/median/max = "
            f"{min(r[1] for r in e4b_rows)}/{sorted(r[1] for r in e4b_rows)[len(e4b_rows)//2]}/{max(r[1] for r in e4b_rows)}, "
            f"tb 事件(未过 where 的 burst 也产)合计 {sum(r[2] for r in e4b_rows)} vs match 合计 {sum(r[1] for r in e4b_rows)}  "
            f"[{time.perf_counter()-t0:.0f}s]")
    tbm._atr_at = orig_atr_at


if __name__ == "__main__":
    main()
