"""两件事，都是对我自己 Phase 4 结论的检验：

(A) 【Falsifier 致命 1】§6.1b 的 77.1% 是不是基率复读？
    旱期被 first_drought>=40 硬闸定义成长段，本来就占掉时间轴绝大部分。
    必须与「财报日均匀随机落点」的基率对照。
    两个零假设都算：
      H0-uniform : 财报日在 [drought_start, buy_date] 全窗均匀
      H0-recent  : 「最近一次财报」= max(filings <= buy_date)，若季报间隔 P，
                   它只能落在 [buy_date - P, buy_date] 内且在该区间均匀。
                   这个 null 更贴实际，且会把基率朝 burst/回踩 方向推。

(B) 【lead 指派】g = 财报公布日 -> buy_date 的累计涨幅，实测分布。
    我在 §1b 断言「旱期 => g ~ 0 是几何强制的、后半句白送」。
    但旱期只禁止「创新突破」，不禁止区间内爬升 => 必须实测，不能推理。
    报原始版 + 减同波动率层基准版；按落点段分层。
"""
from __future__ import annotations

import json
import random
import statistics as st
from datetime import date, datetime
from math import comb
from pathlib import Path

import pandas as pd

OUT = Path(__file__).resolve().parent
PKL = Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls")
BURST = sorted(OUT.glob("burst_start_*.json"))[-1]
COV = sorted(OUT.glob("xbrl_coverage_*.json"))[-1]
N_BENCH = 400
SEED = 42


def d(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def binom_tail_ge(k, n, p):
    """P(X >= k) under Binomial(n, p)。"""
    return sum(comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1))


def binom_tail_le(k, n, p):
    return sum(comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(0, k + 1))


def atr_pct(df, idx, n=20):
    """ATR%(n) at row idx（含当根）。df 需有 high/low/close。"""
    if idx < n:
        return None
    h = df["high"].values[idx - n + 1: idx + 1]
    l = df["low"].values[idx - n + 1: idx + 1]
    pc = df["close"].values[idx - n: idx]
    tr = [max(hi - lo, abs(hi - c), abs(lo - c)) for hi, lo, c in zip(h, l, pc)]
    c0 = df["close"].values[idx]
    return (sum(tr) / n) / c0 if c0 else None


def idx_on_or_after(dates, target):
    """dates 为升序 date 数组；返回第一个 >= target 的位置，无则 None。"""
    lo, hi = 0, len(dates)
    while lo < hi:
        mid = (lo + hi) // 2
        if dates[mid] < target:
            lo = mid + 1
        else:
            hi = mid
    return lo if lo < len(dates) else None


def idx_on_or_before(dates, target):
    lo, hi = 0, len(dates)
    while lo < hi:
        mid = (lo + hi) // 2
        if dates[mid] <= target:
            lo = mid + 1
        else:
            hi = mid
    return lo - 1 if lo > 0 else None


def main() -> None:
    rows = json.loads(BURST.read_text())["rows"]
    by = json.loads(COV.read_text())["by_symbol"]

    # ---------- 组装：每行的 财报日 / 各段边界 ----------
    recs = []
    for r in rows:
        if not r.get("drought_start_date"):
            continue
        sym, bd = r["symbol"], d(r["buy_date"])
        sub = by.get(sym, {}).get("submissions") or {}
        alld = sorted({x for x in (sub.get("all_10Q_dates", []) + sub.get("all_10K_dates", []))})
        cands = [x for x in alld if d(x) <= bd]
        if not cands:
            continue
        filed = d(max(cands, key=d))
        # 上一次定期报告（用于估该票的真实申报间隔 P）
        prior = [x for x in alld if d(x) < filed]
        gap = (filed - d(max(prior, key=d))).days if prior else None
        ds, bs, be = d(r["drought_start_date"]), d(r["burst_start_date"]), d(r["burst_end_date"])
        seg = ("旱期之前" if filed < ds else "旱期内" if filed < bs
               else "burst 期内" if filed <= be else "回踩期内")
        recs.append({"symbol": sym, "buy_date": r["buy_date"], "filed": filed,
                     "drought_start": ds, "burst_start": bs, "burst_end": be,
                     "seg": seg, "filing_gap_days": gap})

    n = len(recs)
    print(f"n = {n} 行\n" + "=" * 72)

    # ---------- (A) 基率对照 ----------
    print("\n【A】§6.1b 的基率检验（Falsifier 致命 1）\n")
    # 各段的自然日长度
    share = {"旱期": [], "burst 期": [], "回踩期": []}
    share_recent = {"旱期": [], "burst 期": [], "回踩期": []}
    for r in recs:
        tot = (d(r["buy_date"]) - r["drought_start"]).days
        if tot <= 0:
            continue
        seg_len = {"旱期": (r["burst_start"] - r["drought_start"]).days,
                   "burst 期": (r["burst_end"] - r["burst_start"]).days,
                   "回踩期": (d(r["buy_date"]) - r["burst_end"]).days}
        for k in share:
            share[k].append(seg_len[k] / tot)
        # H0-recent：最近一次财报只能落在 [buy_date - P, buy_date]
        P = r["filing_gap_days"] or 91
        w0 = d(r["buy_date"]) - pd.Timedelta(days=P).to_pytimedelta()
        w0 = max(w0, r["drought_start"])
        wlen = (d(r["buy_date"]) - w0).days
        if wlen <= 0:
            continue
        ov = {"旱期": max(0, (min(r["burst_start"], d(r["buy_date"])) - max(w0, r["drought_start"])).days),
              "burst 期": max(0, (min(r["burst_end"], d(r["buy_date"])) - max(w0, r["burst_start"])).days),
              "回踩期": max(0, (d(r["buy_date"]) - max(w0, r["burst_end"])).days)}
        for k in share_recent:
            share_recent[k].append(ov[k] / wlen)

    obs = {"旱期": sum(1 for r in recs if r["seg"] == "旱期内"),
           "burst 期": sum(1 for r in recs if r["seg"] == "burst 期内"),
           "回踩期": sum(1 for r in recs if r["seg"] == "回踩期内")}
    before = sum(1 for r in recs if r["seg"] == "旱期之前")
    print(f"（另有 {before}/{n} 行财报落在旱期之前，不参与下表）\n")
    print(f"{'段':10s} {'H0-uniform 基率':>16s} {'H0-recent 基率':>16s} {'实测':>10s} "
          f"{'lift(unif)':>11s} {'lift(recent)':>13s}")
    for k in ("旱期", "burst 期", "回踩期"):
        bu = st.mean(share[k]); br = st.mean(share_recent[k]) if share_recent[k] else float("nan")
        o = obs[k] / n
        print(f"{k:10s} {bu:16.1%} {br:16.1%} {o:10.1%} "
              f"{o/bu if bu else float('nan'):11.2f}x {o/br if br else float('nan'):13.2f}x")
    print()
    for k in ("旱期", "burst 期", "回踩期"):
        bu = st.mean(share[k]); br = st.mean(share_recent[k])
        k_obs = obs[k]
        p_hi_u = binom_tail_ge(k_obs, n, bu); p_lo_u = binom_tail_le(k_obs, n, bu)
        p_hi_r = binom_tail_ge(k_obs, n, br); p_lo_r = binom_tail_le(k_obs, n, br)
        print(f"  {k:10s} 单尾二项 p: H0-uniform 高={p_hi_u:.3f} 低={p_lo_u:.3f} | "
              f"H0-recent 高={p_hi_r:.3f} 低={p_lo_r:.3f}")

    # ---------- (B) g 的实测 ----------
    print("\n" + "=" * 72)
    print("\n【B】g = 财报公布日 -> buy_date 的累计涨幅（lead 指派）\n")
    cache: dict[str, pd.DataFrame] = {}

    def load(sym):
        if sym not in cache:
            p = PKL / f"{sym}.pkl"
            if not p.exists():
                cache[sym] = None
            else:
                df = pd.read_pickle(p).reset_index()   # DatetimeIndex(name='date') -> 'date' 列
                df["_d"] = pd.to_datetime(df["date"]).dt.date
                cache[sym] = df
        return cache[sym]

    for r in recs:
        df = load(r["symbol"])
        if df is None:
            continue
        dates = df["_d"].tolist()
        i0 = idx_on_or_after(dates, r["filed"])
        i1 = idx_on_or_before(dates, d(r["buy_date"]))
        if i0 is None or i1 is None or i1 <= i0:
            continue
        c0, c1 = df["close"].iat[i0], df["close"].iat[i1]
        if not c0:
            continue
        r["g_raw"] = c1 / c0 - 1
        r["i0"], r["i1"] = i0, i1
        r["td"] = i1 - i0
        r["atr_pct_at_filed"] = atr_pct(df, i0)
        # 路径信息：窗内最高/最低相对 c0
        hi = df["high"].values[i0:i1 + 1].max(); lo = df["low"].values[i0:i1 + 1].min()
        r["path_max"] = hi / c0 - 1
        r["path_min"] = lo / c0 - 1

    have = [r for r in recs if "g_raw" in r]
    print(f"可算 g 的行：{len(have)}/{n}\n")

    # 基准：随机 N_BENCH 只 pkl，同 ATR% 三分位、同日历窗的中位收益
    random.seed(SEED)
    allp = sorted(p.stem for p in PKL.glob("*.pkl"))
    bench_syms = random.sample(allp, min(N_BENCH, len(allp)))
    print(f"基准池：随机 {len(bench_syms)} 只 pkl（seed={SEED}）")
    bench = {}
    for s in bench_syms:
        try:
            df = pd.read_pickle(PKL / f"{s}.pkl").reset_index()
            df["_d"] = pd.to_datetime(df["date"]).dt.date
            bench[s] = df
        except Exception:                                    # noqa: BLE001
            pass
    print(f"成功载入 {len(bench)} 只\n")

    # 用本样本的 ATR% 分三分位切点
    atrs = sorted(r["atr_pct_at_filed"] for r in have if r.get("atr_pct_at_filed"))
    t1, t2 = atrs[len(atrs) // 3], atrs[2 * len(atrs) // 3]
    print(f"ATR% 三分位切点：{t1:.4f} / {t2:.4f}")

    def tercile(v):
        return 0 if v is None else (0 if v <= t1 else 1 if v <= t2 else 2)

    for r in have:
        tq = tercile(r.get("atr_pct_at_filed"))
        peers = []
        for s, df in bench.items():
            dates = df["_d"].tolist()
            j0 = idx_on_or_after(dates, r["filed"])
            j1 = idx_on_or_before(dates, d(r["buy_date"]))
            if j0 is None or j1 is None or j1 <= j0:
                continue
            a = atr_pct(df, j0)
            if a is None or tercile(a) != tq:
                continue
            c0 = df["close"].iat[j0]
            if not c0:
                continue
            peers.append(df["close"].iat[j1] / c0 - 1)
        r["bench_n"] = len(peers)
        r["bench"] = st.median(peers) if len(peers) >= 10 else None
        if r["bench"] is not None:
            r["g_adj"] = r["g_raw"] - r["bench"]

    def rep(label, vals):
        if len(vals) < 4:
            print(f"  {label:22s} n={len(vals)} 太少"); return
        v = sorted(vals); q = st.quantiles(v, n=4)
        print(f"  {label:22s} n={len(v):3d} min={v[0]:+.3f} q10={v[len(v)//10]:+.3f} "
              f"q25={q[0]:+.3f} med={st.median(v):+.3f} q75={q[2]:+.3f} "
              f"q90={v[9*len(v)//10]:+.3f} max={v[-1]:+.3f}")
        print(f"  {'':22s} |g|<=10% 的比例 {sum(1 for x in v if abs(x)<=0.10)/len(v):.1%} · "
              f"|g|<=20% {sum(1 for x in v if abs(x)<=0.20)/len(v):.1%} · "
              f"g>0 的比例 {sum(1 for x in v if x>0)/len(v):.1%}")

    print("\n[B1] 全体")
    rep("g_raw（原始）", [r["g_raw"] for r in have])
    rep("g_adj（减同波动层）", [r["g_adj"] for r in have if r.get("g_adj") is not None])
    print(f"  持有天数 td: med={st.median([r['td'] for r in have]):.0f} 交易日")
    print(f"  基准可用的行: {sum(1 for r in have if r.get('g_adj') is not None)}/{len(have)}；"
          f"基准 peer 数中位 {st.median([r['bench_n'] for r in have]):.0f}")

    for segname in ("旱期内", "burst 期内"):
        sel = [r for r in have if r["seg"] == segname]
        print(f"\n[B2] 财报落在【{segname}】 n={len(sel)}")
        rep("g_raw", [r["g_raw"] for r in sel])
        rep("g_adj", [r["g_adj"] for r in sel if r.get("g_adj") is not None])

    print("\n[B3] 路径（相对财报日收盘）")
    rep("窗内最高 path_max", [r["path_max"] for r in have])
    rep("窗内最低 path_min", [r["path_min"] for r in have])

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    (OUT / f"baserate_and_g_{stamp}.json").write_text(json.dumps(
        [{k: (v.isoformat() if isinstance(v, date) else v) for k, v in r.items()}
         for r in recs], ensure_ascii=False, indent=1, default=str))
    print(f"\n-> baserate_and_g_{stamp}.json")


if __name__ == "__main__":
    main()
