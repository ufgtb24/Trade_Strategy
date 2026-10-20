"""13 外部信息 · XBRL 财务事实能不能按「公开那一刻」取：样本股票的 companyfacts。

看三件事：
  1. 每条数值是否带申报日（filed）和申报编号（accn）——有就能按申报日还原「当时知道的值」。
  2. 事后修订会不会覆盖原值：同一指标、同一报告期，在不同申报里出现几次、数值是否不同。
     出现多次且数值不同 = 原值和修订值都留着（没有被覆盖）。
  3. 流通股数（封面的 EntityCommonStockSharesOutstanding）的覆盖与申报日——可拿来近似当时市值。
读 scratchpad/13/dl-sec-facts/（视为不可信，只取字段）。
输出：本目录 13-xbrl_check_out.txt
运行：uv run python -I .scratch/selection-pattern/scripts/13-xbrl_check.py
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path

import pandas as pd

SCR = Path("/tmp/claude-1000/-home-yu-PycharmProjects-Trade-Strategy/151ccac1-47bb-476f-8b64-dc09e9407cc5/scratchpad/13")
HERE = Path(os.path.abspath(__file__)).parent
REV = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet",
       "RevenueFromContractWithCustomerIncludingAssessedTax"]


def main():
    out = []
    w = out.append
    for p in sorted(glob.glob(str(SCR / "dl-sec-facts/*.json"))):
        t = os.path.basename(p).split("__")[0]
        d = json.loads(Path(p).read_text())
        facts = d.get("facts", {})
        gaap = facts.get("us-gaap", {})
        ifrs = facts.get("ifrs-full", {})
        dei = facts.get("dei", {})
        rows = []
        for tax, block in (("us-gaap", gaap), ("ifrs-full", ifrs)):
            for tag, v in block.items():
                for unit, lst in v.get("units", {}).items():
                    for x in lst:
                        rows.append((tax, tag, unit, x.get("start"), x.get("end"), x.get("val"), x.get("filed"), x.get("form"), x.get("accn")))
        df = pd.DataFrame(rows, columns=["tax", "tag", "unit", "start", "end", "val", "filed", "form", "accn"])
        has_filed = df.filed.notna().mean() if len(df) else float("nan")
        g = df.groupby(["tag", "unit", "start", "end"], dropna=False)
        multi = g.val.transform("size") > 1
        nuniq = g.val.transform("nunique")
        n_period = g.ngroups
        n_multi = df[multi].groupby(["tag", "unit", "start", "end"], dropna=False).ngroups
        n_diff = df[nuniq > 1].groupby(["tag", "unit", "start", "end"], dropna=False).ngroups
        rev = df[df.tag.isin(REV)]
        rev_recent = rev[rev.filed >= "2024-01-01"]
        so = dei.get("EntityCommonStockSharesOutstanding", {}).get("units", {}).get("shares", [])
        so_recent = [x for x in so if x.get("filed", "") >= "2024-01-01"]
        w(f"{t:6s} 数值 {len(df):6d} 条，带申报日 {has_filed:.0%}；指标×报告期 {n_period} 组，其中出现在多份申报里的 {n_multi} 组，"
          f"多份申报数值不同（原值与修订值并存）{n_diff} 组；营收类 2024 后 {len(rev_recent)} 条；"
          f"流通股数 2024 后申报 {len(so_recent)} 次" + (f"（例：{so_recent[-1]['end']} 截至 {so_recent[-1]['val']:,} 股，{so_recent[-1]['filed']} 申报）" if so_recent else ""))
        if n_diff:
            ex = df[nuniq > 1].sort_values(["tag", "end", "filed"]).groupby(["tag", "unit", "start", "end"], dropna=False).head(3).head(3)
            w("       例：" + "; ".join(f"{r.tag} {r.start}~{r.end} = {r.val} ({r.form} {r.filed})" for r in ex.itertuples()))
    (HERE / "13-xbrl_check_out.txt").write_text("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
