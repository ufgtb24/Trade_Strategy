"""汇总 point-in-time 财务序列可算性 + 净利润符号分布。

纪律声明：本脚本刻意 **不** 计算任何财务量与 fr40 的关系。
112 行是尚未被本通道使用过的样本，任何「先看结果再定阈值」都会烧掉它的预注册价值。
本文件只出「可算性 / 作用面 / 分布形状」这些与 outcome 无关的量。
"""
from __future__ import annotations

import json
import statistics as st
from collections import Counter
from pathlib import Path

OUT = Path(__file__).resolve().parent
RAW = sorted(OUT.glob("financial_series_*.json"))[-1]


def pct(a, b):
    return f"{a}/{b} = {a/b:.1%}" if b else "n/a"


def main() -> None:
    rows = json.loads(RAW.read_text())
    n = len(rows)
    print(f"源 {RAW.name} · {n} 行 bb 买点（point-in-time：只用 filed<=buy_date 的原报值）\n")

    ok = [r for r in rows if r.get("status") == "ok"]
    print(f"[A] 有 XBRL 的行 {pct(len(ok), n)}")

    # --- 可算性阶梯 ---
    print("\n[B] 可算性阶梯（分母 = 112 行，即实盘每次决策的真实可用率）")
    steps = [
        ("有季度营收点 >=1", lambda r: r.get("n_rev_q", 0) >= 1),
        ("有季度营收点 >=5（YoY 所需最短序列）", lambda r: r.get("n_rev_q", 0) >= 5),
        ("YoY 营收增速真的算出来了", lambda r: r.get("rev_yoy_q") is not None),
        ("QoQ 营收增速算出来了", lambda r: r.get("rev_qoq") is not None),
        ("年度营收 YoY（20-F 也能算）", lambda r: r.get("rev_yoy_a") is not None),
        ("季度净利润 >=1 点", lambda r: r.get("n_ni_q", 0) >= 1),
        ("净利润符号可判（季或年）", lambda r: r.get("ni_sign") is not None),
        ("季度经营现金流 >=1 点", lambda r: r.get("n_cfo_q", 0) >= 1),
        ("季度毛利 >=1 点", lambda r: r.get("n_gp_q", 0) >= 1),
        ("毛利率水平可算", lambda r: r.get("gm_latest") is not None),
        ("毛利率 YoY 变化可算", lambda r: r.get("gm_yoy_delta") is not None),
        ("加权股本 YoY（稀释率）可算", lambda r: r.get("shares_yoy") is not None),
        ("现金 runway（仅烧钱公司）可算", lambda r: r.get("runway_quarters") is not None),
    ]
    for label, f in steps:
        k = sum(1 for r in rows if f(r))
        print(f"  {label:38s} {k:3d}/{n} = {k/n:6.1%}")

    # --- YoY 失败原因 ---
    fails = Counter()
    for r in rows:
        if r.get("rev_yoy_q") is None:
            dg = r.get("rev_yoy_diag")
            if r.get("status") != "ok":
                fails["无 XBRL（外国/OTC 非申报）"] += 1
            elif r.get("n_rev_q", 0) == 0:
                fails["零营收公司（pre-revenue：生物/矿业/概念股）"] += 1
            elif isinstance(dg, dict) and dg.get("reason") == "no_yoy_pair":
                fails[f"季度点不足以配对 YoY（n_q={dg.get('n_quarters')}）"] += 1
            else:
                fails["其他"] += 1
    print("\n[C] 营收 YoY 算不出来的原因分解")
    for k, v in fails.most_common():
        print(f"  {k:52s} {v:3d}")

    # --- 净利润 ---
    print("\n[D] 净利润符号分布（回答「是否排除净利润」）")
    sg = Counter(r.get("ni_sign") for r in rows)
    print(f"  {dict(sg)}")
    have = [r for r in rows if r.get("ni_sign")]
    neg = [r for r in have if r["ni_sign"] == "neg"]
    print(f"  可判符号 {pct(len(have), n)}；其中亏损 {pct(len(neg), len(have))}")
    cfo_sg = Counter(r.get("cfo_sign") for r in rows if r.get("cfo_sign"))
    print(f"  经营现金流符号: {dict(cfo_sg)} → 现金流为负 "
          f"{pct(cfo_sg.get('neg',0), sum(cfo_sg.values()))}")
    both = [r for r in rows if r.get("ni_sign") and r.get("cfo_sign")]
    print(f"  净利亏损 ∧ 现金流为负: "
          f"{pct(sum(1 for r in both if r['ni_sign']=='neg' and r['cfo_sign']=='neg'), len(both))}")
    print(f"  净利亏损 ∧ 现金流为正: "
          f"{pct(sum(1 for r in both if r['ni_sign']=='neg' and r['cfo_sign']=='pos'), len(both))}")

    # --- 分布形状（无 outcome）---
    def dist(key, label, scale=1.0):
        v = [r[key] * scale for r in rows if r.get(key) is not None]
        if len(v) < 4:
            print(f"  {label:26s} n={len(v)} 太少"); return
        q = st.quantiles(v, n=4)
        print(f"  {label:26s} n={len(v):3d}  q10={sorted(v)[len(v)//10]:8.3f} "
              f"q25={q[0]:8.3f} med={st.median(v):8.3f} q75={q[2]:8.3f} "
              f"q90={sorted(v)[9*len(v)//10]:8.3f}")
    print("\n[E] 分布形状（与 outcome 无关；用于判断阈值分组是否有作用面）")
    dist("rev_yoy_q", "营收 YoY（季）")
    dist("rev_qoq", "营收 QoQ")
    dist("gm_latest", "毛利率水平")
    dist("gm_yoy_delta", "毛利率 YoY 变化")
    dist("shares_yoy", "加权股本 YoY（稀释率）")
    dist("runway_quarters", "现金 runway（季度）")
    dist("rev_lag_days", "最新营收数据的申报账龄（日）")

    # --- 分组作用面：若按 YoY>0.2 切，两侧各多少行 ---
    print("\n[F] 若以「营收 YoY >= 阈值」分组，各组行数（分母 112）")
    for th in (0.0, 0.10, 0.20, 0.30, 0.50):
        hi = sum(1 for r in rows if (r.get("rev_yoy_q") or -9) >= th)
        print(f"  YoY>={th:4.0%}: 高增长组 {hi:3d} 行 · 低增长组 "
              f"{sum(1 for r in rows if r.get('rev_yoy_q') is not None) - hi:3d} 行 · "
              f"无值组 {sum(1 for r in rows if r.get('rev_yoy_q') is None):3d} 行")


if __name__ == "__main__":
    main()
