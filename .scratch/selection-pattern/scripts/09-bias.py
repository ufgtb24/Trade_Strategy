"""09 目标池票 · 池子里的幸存者偏差：沿用 04 的推演，把「同档对照」换成「池内同档对照」。

04 的模型（见 04-bias_chart.py 头注）：
  偏差 = Σ_q w_q · (h_X,q − h_q) · G
    h_q   第 q 档对照里「本该有、却因以后被摘牌而缺掉」的比例
    h_X,q 处于状态 X 的买点里同一比例
    w_q   状态 X 的买点落在第 q 档的比例（本地实测）
    G     以后被摘牌的股票比幸存股方向得分低多少（模拟：0.25，区间 0.15–0.40）
池内版本（全部只用当天及以前的数据）：
  档 = 每个抽样日在池内按 M 切五档；w_q、b_s,q（幸存股里状态 X 在池内第 q 档的占比）实测。
  以后被摘牌的股票怎么进池：把最高波动档（全市场档）按「离一年高点跌了多深」分成五个细状态
    （跌掉九成五以上 / 九成到九成五 / 七成到九成 / 一半到七成 / 不到一半）。
    以后被摘牌的股票在这些细状态上的分布 = 04 的假设（中间：跌掉九成以上 0.45、七成以上 0.75、一半以上 0.90，
    另加九成五以上 0.30）。
    在同一个细状态里，它们过池子成交额关的比例 = 幸存股同状态的实测比例 × κ。
      κ = 「同样跌得这么深，以后被摘牌的股票成交额更小」的折扣：低 0.4 / 中 0.6 / 高 1.0。
      锚：2026-10-05 当天，最高档里跌掉七成以上的幸存股，市值 5000 万以下的过 100 万成交额关的只有 8%，
      全部只有 16%（市值来自 Nasdaq 筛选器）；交易所摘牌的 84% 事先都在 5000 万以下待过（04 引 SEC 表 2）。
    过价格关的比例假设 0.95（0.9–1.0；10 美元上限 0.9，0.8–1.0）。
  于是：ρ（以后被摘牌的股票落在池内的比例）= Σ 细状态分布 × 幸存股过关率 × κ × 过价格关比例；
        进池以后它们在各细状态上的分布 ∝ 细状态分布 × 幸存股过关率（κ 约掉）；
        池内缺掉的 / 池内幸存的 = f/(1−f) × ρ/π，π = 幸存股落在池内的比例（实测）。
  c'_q  以后被摘牌、进了池子的股票落在池内各档的比例：沿用 04 的三套。
  摘牌率：2022 2.6%、2023 4.5%（04 的文献读数）；2024–2026 年三套：低 = 04 原假设 3%/年；
          中 = 4.5% / 5.0% / 4.0%；高 = 5.5% / 6.0% / 5.0%（依据 09-edgar_counts 的 Nasdaq 书面摘牌决定数）。
低 / 中 / 高三套假设整体捆绑（与 04 相同），给的是范围，不是置信区间。

输出：research/09-survivorship-pool.png、本目录 09-bias_out.txt、scratchpad/09/bias_results.pkl
运行：uv run python .scratch/selection-pattern/scripts/09-bias.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

SCR = Path("/tmp/claude-1000/-home-yu-PycharmProjects-Trade-Strategy/151ccac1-47bb-476f-8b64-dc09e9407cc5/scratchpad")
HERE = Path(__file__).resolve().parent
END = pd.Timestamp("2026-10-05")
SC = ("low", "mid", "high")
RATES = {
    "low": {2022: 0.026, 2023: 0.045, 2024: 0.03, 2025: 0.03, 2026: 0.03},
    "mid": {2022: 0.026, 2023: 0.045, 2024: 0.045, 2025: 0.05, 2026: 0.04},
    "high": {2022: 0.026, 2023: 0.045, 2024: 0.055, 2025: 0.06, 2026: 0.05},
}
C_SETS = {"low": (0.05, 0.05, 0.10, 0.30, 0.50), "mid": (0.03, 0.03, 0.09, 0.25, 0.60),
          "high": (0.02, 0.02, 0.06, 0.20, 0.70)}
G = {"low": 0.15, "mid": 0.25, "high": 0.40}
KAPPA = {"low": 0.4, "mid": 0.6, "high": 1.0}
PRICE_PASS = {20: {"low": 0.90, "mid": 0.95, "high": 1.0}, 10: {"low": 0.80, "mid": 0.90, "high": 1.0},
              None: {"low": 1.0, "mid": 1.0, "high": 1.0}}
# 以后被摘牌的股票（最高档里）离一年高点跌掉 ≥95% / ≥90% / ≥70% / ≥50% 的累计比例（04 的假设，95% 一档为本票新增）
CUM_D = {"low": (0.15, 0.30, 0.60, 0.80), "mid": (0.30, 0.45, 0.75, 0.90), "high": (0.45, 0.60, 0.90, 0.95)}
FINE = ("dd05", "dd10", "dd30", "dd50", "rest")     # 细状态：≤0.05、(0.05,0.1]、(0.1,0.3]、(0.3,0.5]、>0.5
P2_DEAD = {"low": 0.3, "mid": 0.5, "high": 0.7}     # 挖数据第二档：以后被摘牌的那批里当时价格 ≤2 美元的比例（假设）

POOLS = {  # 名称: (成交额下限, 价格上限, 成交额上限)
    "all_ext": (0, None, None),
    "dv1M_cap100M": (1e6, None, 1e8),
    "dv2M_cap100M": (2e6, None, 1e8),
    "dv1M_px20_cap100M": (1e6, 20, 1e8),
    "dv2M_px20_cap100M": (2e6, 20, 1e8),
    "dv5M_px20_cap100M": (5e6, 20, 1e8),
    "dv2M_px10_cap100M": (2e6, 10, 1e8),
}
STATE_ORDER = ["底部：跌掉一半以上", "底部：跌掉七成以上", "底部：跌掉九成以上",
               "burst：反弹型", "burst：高位型", "创一年新高",
               "挖数据：跌掉九成以上 + 成交额贴着下限", "挖数据：跌掉九成五以上 + 成交额贴着下限 + 复权价 ≤2 美元"]


def f_of(t, rates):
    surv, cur = 1.0, t
    while cur < END:
        nxt = min(pd.Timestamp(f"{cur.year + 1}-01-01"), END)
        surv *= (1 - rates[cur.year]) ** ((nxt - cur).days / 365.25)
        cur = nxt
    return 1 - surv


def fine_state(dd):
    return np.select([dd <= 0.05, dd <= 0.1, dd <= 0.3, dd <= 0.5], [0, 1, 2, 3], 4)


def load_panel():
    z = np.load(SCR / "09/panel.npz", allow_pickle=True)
    cal = pd.DatetimeIndex(z["calendar"])
    cols = np.flatnonzero(cal >= "2022-01-03")[::5]
    masks = np.load(SCR / "09/pool_masks.npz")
    rows = []
    for j in cols:
        ok = masks["all_ext"][:, j]
        df = pd.DataFrame({k: z[k][ok, j] for k in ("close", "dv20", "M", "dd", "nb20", "hi252")})
        df["date"] = cal[j]
        rows.append(df)
    p = pd.concat(rows, ignore_index=True)
    p = p[np.isfinite(p.M) & (p.M > 0) & np.isfinite(p.dd)]
    p["mq"] = p.groupby("date")["M"].transform(
        lambda s: np.searchsorted(np.unique(np.quantile(s, [.2, .4, .6, .8])), s, side="left"))
    p["fs"] = fine_state(p.dd.to_numpy())
    return p


def pool_mask(p, lo, px, hi):
    m = p.dv20 >= lo
    if px is not None:
        m &= p.close <= px
    if hi is not None:
        m &= p.dv20 <= hi
    return m


def dead_fine(s):
    c = CUM_D[s]
    return np.array([c[0], c[1] - c[0], c[2] - c[1], c[3] - c[2], 1 - c[3]])


def bias_series(dates, wq, bs, ratio, k_of_t, s):
    out = []
    for t in dates:
        k = k_of_t(t)
        tot = 0.0
        for qq in range(5):
            if wq[qq] == 0:
                continue
            cq = C_SETS[s][qq]
            hq = k * cq / (k * cq + 0.2)
            bd = min(ratio * bs[qq], 0.95)
            hx = hq * bd / (hq * bd + (1 - hq) * bs[qq]) if bs[qq] > 0 else hq
            tot += wq[qq] * (hx - hq) * G[s]
        out.append(tot)
    return np.array(out)


def amp_gap(m, hq, hx, n=200_000, seed=4):
    """04 第 E 节同法：最高档里幸存股漂移 0、以后被摘牌的股票每年往下漂 −1.0（40 日 −0.16），
    窗口内最大涨幅的混合分布中位数；返回 补全后 pattern 中位 − 对照中位（负数 = 只看幸存股时幅度领先被抬高这么多）。"""
    rng = np.random.default_rng(seed)
    s = 0.69 * m
    surv = np.expm1(np.maximum(np.cumsum(s * rng.standard_normal((n, 40)), axis=1).max(1), 0))
    dead = np.expm1(np.maximum(np.cumsum(-0.16 / 40 + s * rng.standard_normal((n, 40)), axis=1).max(1), 0))

    def mixed(h):
        k = int(round(h * n))
        return float(np.median(np.concatenate([surv[: n - k], dead[:k]])))
    return mixed(hx) - mixed(hq)


def main():
    p = load_panel()
    top = p.mq == 4
    lines = []
    w = lines.append
    dates_eval = [pd.Timestamp(x) for x in ("2022-01-03", "2023-01-03", "2024-01-02", "2025-01-02", "2026-01-02", "2026-07-01")]
    chart_dates = pd.date_range("2022-01-01", "2026-08-01", freq="MS")
    n_years = (p.date.max() - p.date.min()).days / 365.25
    results, meta = {}, {}
    for pname, (lo, px, hi) in POOLS.items():
        inpool = pool_mask(p, lo, px, hi)
        pi = inpool.groupby(p.date).mean().mean()
        dvpass = pool_mask(p, lo, None, hi)
        floor = lo if lo > 0 else 1e6
        near_all = (p.dv20 >= floor) & (p.dv20 < 2 * floor)
        # 最高档各细状态：幸存股过成交额关的比例；过关者里成交额贴着下限的比例
        pass_s = np.array([dvpass[top & (p.fs == i)].mean() for i in range(5)])
        near_s = np.array([near_all[top & dvpass & (p.fs == i)].mean() for i in range(5)])
        q = p.loc[inpool].copy()
        q["pq"] = q.groupby("date")["M"].transform(
            lambda s: np.searchsorted(np.unique(np.quantile(s, [.2, .4, .6, .8])), s, side="left"))
        near = (q.dv20 >= floor) & (q.dv20 < 2 * floor)
        reb = q.dd <= 0.5
        burst = q.nb20 >= 3
        masks = {
            "底部：跌掉一半以上": q.dd <= 0.5, "底部：跌掉七成以上": q.dd <= 0.3, "底部：跌掉九成以上": q.dd <= 0.1,
            "burst：反弹型": burst & reb, "burst：高位型": burst & ~reb, "创一年新高": q.hi252 >= 1,
            "挖数据：跌掉九成以上 + 成交额贴着下限": (q.dd <= 0.1) & near,
            "挖数据：跌掉九成五以上 + 成交额贴着下限 + 复权价 ≤2 美元": (q.dd <= 0.05) & near & (q.close <= 2),
        }
        topq = q.pq == 4
        bs_top = {k: v[topq].mean() for k, v in masks.items()}
        rho, comp = {}, {}
        for s in SC:
            dfine = dead_fine(s)
            kappa = KAPPA[s] if lo > 0 else 1.0     # 没有成交额下限时谈不上「更难过关」
            rho[s] = float((dfine * pass_s).sum() * kappa * PRICE_PASS[px][s])
            comp[s] = dfine * pass_s / (dfine * pass_s).sum()   # 进池以后的细状态分布
        w(f"== 池子 {pname}：π = {pi:.3f}；ρ 低/中/高 = {rho['low']:.3f}/{rho['mid']:.3f}/{rho['high']:.3f}；"
          f"ρ/π = {rho['low'] / pi:.2f}/{rho['mid'] / pi:.2f}/{rho['high'] / pi:.2f} ==")
        w(f"   最高档各细状态（≤0.05/≤0.1/≤0.3/≤0.5/其余）幸存股过成交额关比例 {np.round(pass_s, 3).tolist()}；"
          f"过关者贴着下限的比例 {np.round(near_s, 2).tolist()}")
        w(f"   以后被摘牌、进了池的股票在细状态上的分布（中）{np.round(comp['mid'], 3).tolist()}")
        meta[pname] = dict(pi=pi, rho=rho, years=n_years)
        for sname in STATE_ORDER:
            mask = masks[sname]
            wq = q.loc[mask, "pq"].value_counts(normalize=True).reindex(range(5), fill_value=0).to_numpy()
            bs = q.assign(m=mask).groupby("pq")["m"].mean().reindex(range(5)).to_numpy()
            per_year_days = mask.sum() * 5 / n_years
            res = {}
            for s in SC:
                c = comp[s]
                bd_cum = {"底部：跌掉一半以上": c[:4].sum(), "底部：跌掉七成以上": c[:3].sum(),
                          "底部：跌掉九成以上": c[:2].sum()}
                if sname in bd_cum:
                    ratio = bd_cum[sname] / max(bs_top[sname], 1e-6)
                elif sname == "burst：反弹型":
                    r50 = bd_cum["底部：跌掉一半以上"] / max(bs_top["底部：跌掉一半以上"], 1e-6)
                    r30 = bd_cum["底部：跌掉七成以上"] / max(bs_top["底部：跌掉七成以上"], 1e-6)
                    ratio = {"low": 1.0, "mid": r50, "high": r30}[s]
                elif sname in ("burst：高位型", "创一年新高"):
                    ratio = {"low": 0.1, "mid": 0.3, "high": 0.6}[s]
                elif sname.startswith("挖数据：跌掉九成以上"):
                    ratio = (c[:2] * near_s[:2]).sum() / max(bs_top[sname], 1e-6)
                else:
                    ratio = c[0] * near_s[0] * P2_DEAD[s] / max(bs_top[sname], 1e-6)
                k_of_t = (lambda t, s=s: f_of(t, RATES[s]) / (1 - f_of(t, RATES[s])) * rho[s] / pi)
                res[s] = bias_series(list(chart_dates) + dates_eval, wq, bs, ratio, k_of_t, s)
                res[s + "_ratio"] = ratio
            res["per_year_days"] = per_year_days
            # 幅度：只算中间假设、池内最高档、两个买入日
            m_top = float(q.loc[topq, "M"].median())
            amps = []
            for t in (dates_eval[0], dates_eval[2]):
                k = f_of(t, RATES["mid"]) / (1 - f_of(t, RATES["mid"])) * rho["mid"] / pi
                hq = k * C_SETS["mid"][4] / (k * C_SETS["mid"][4] + 0.2)
                bd = min(res["mid_ratio"] * bs[4], 0.95)
                hx = hq * bd / (hq * bd + (1 - hq) * bs[4]) if bs[4] > 0 else hq
                amps.append(-amp_gap(m_top, hq, hx))
            res["amp_mid"] = amps
            res["bs_top"] = bs_top[sname]
            results[(pname, sname)] = res
            ne = len(chart_dates)
            cells = " | ".join(f"{t.date()}: {res['low'][ne + i]:+.3f}/{res['mid'][ne + i]:+.3f}/{res['high'][ne + i]:+.3f}"
                               for i, t in enumerate(dates_eval))
            w(f"  {sname}：池内每年约 {per_year_days:,.0f} 个股票日；池内最高档幸存股处于该状态 {bs_top[sname]:.3f}；"
              f"「以后被摘牌 / 幸存」该状态的比例之比 中 {res['mid_ratio']:.2f}")
            w(f"     白得的方向领先（低/中/高）：{cells}")
            w(f"     白得的幅度领先（中间假设、只算最高档，前瞻收益中位，百分点）：2022-01 {res['amp_mid'][0] * 100:+.1f}，"
              f"2024-01 {res['amp_mid'][1] * 100:+.1f}")
        w("")
    out = "\n".join(lines)
    print(out)
    (HERE / "09-bias_out.txt").write_text(out + "\n")
    pd.to_pickle({"results": results, "meta": meta, "chart_dates": chart_dates, "dates_eval": dates_eval},
                 SCR / "09/bias_results.pkl")


if __name__ == "__main__":
    main()
