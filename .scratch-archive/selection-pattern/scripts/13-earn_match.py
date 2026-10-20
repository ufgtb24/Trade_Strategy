"""13 外部信息 · Nasdaq 免费财报日历对目标池的漏报率：拿 SEC 的业绩发布公告（8-K 2.02）当真值核对。

真值：普查样本里本土申报人在 4 个业绩高峰日的 8-K 2.02（scratchpad/13/edgar_202_dates.csv，由 EDGAR 接收时刻换算的美东日期）。
盘后发布的，Nasdaq 日历可能记在当天或次日，所以当天和次日两张日历都查。
读 scratchpad/13/dl-nasdaq-earn3/*.json（视为不可信，只取字段）。
输出：本目录 13-earn_match_out.txt
运行：uv run python -I .scratch/selection-pattern/scripts/13-earn_match.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd

SCR = Path("/tmp/claude-1000/-home-yu-PycharmProjects-Trade-Strategy/151ccac1-47bb-476f-8b64-dc09e9407cc5/scratchpad/13")
HERE = Path(os.path.abspath(__file__)).parent
DAYS = {"2024-11-07": "2024-11-08", "2024-08-08": "2024-08-09", "2025-05-08": "2025-05-09", "2025-08-07": "2025-08-08"}


def cal(d):
    x = json.loads((SCR / f"dl-nasdaq-earn3/{d}.json").read_text())
    rows = (x.get("data") or {}).get("rows") or []
    return pd.DataFrame(rows)


def main():
    e = pd.read_csv(SCR / "edgar_202_dates.csv")
    out = []
    hit = tot = withest = 0
    for d, nxt in DAYS.items():
        a, b = cal(d), cal(nxt)
        truth = set(e[e.d == d].t)
        found = truth & (set(a.get("symbol", [])) | set(b.get("symbol", [])))
        both = pd.concat([a, b])
        est = both[both.symbol.isin(found)]
        n_est = int((pd.to_numeric(est["noOfEsts"], errors="coerce").fillna(0) > 0).groupby(est.symbol).max().sum()) if len(est) else 0
        out.append(f"{d}：SEC 显示样本里 {len(truth)} 只发了业绩，Nasdaq 日历（当天+次日）列出 {len(found)} 只，其中有分析师预期的 {n_est} 只；"
                   f"漏掉的 {sorted(truth - found)}")
        hit += len(found)
        tot += len(truth)
        withest += n_est
    out.append(f"合计：{hit}/{tot} 被日历列出（{hit/tot:.0%}），列出的里面有分析师预期的 {withest}/{hit}")
    (HERE / "13-earn_match_out.txt").write_text("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
