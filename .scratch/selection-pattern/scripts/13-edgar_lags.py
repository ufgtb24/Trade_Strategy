"""13 外部信息 · EDGAR 的三种日期差多少：事件日（reportDate）→ 接收时刻（acceptanceDateTime，UTC→美东）。

回答「拿事件日当公开日会偷看多少」：8-K 事件日、Form 4 交易日、10-Q/10-K 报告期末，分别比实际公开早几天；
另看 8-K 2.02（业绩发布）的接收时刻落在盘前还是盘后。普查样本、窗口 2024-01-01 ～ 2026-10-06。
输出：本目录 13-edgar_lags_out.txt
运行：uv run python -I .scratch/selection-pattern/scripts/13-edgar_lags.py
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

SCR = Path("/tmp/claude-1000/-home-yu-PycharmProjects-Trade-Strategy/151ccac1-47bb-476f-8b64-dc09e9407cc5/scratchpad/13")
HERE = Path(os.path.abspath(__file__)).parent


def main():
    # 普查样本只算落在默认池（剔封闭式基金与 SPAC 壳）里的
    ext = set(pd.read_csv(SCR / "pool_ever_ext.csv").symbol)
    census = set((SCR / "sample_census150.txt").read_text().split()) & ext
    fr = []
    for p in glob.glob(str(SCR / "dl-sec-sub/*.json")):
        t = os.path.basename(p).split("__")[0]
        if t not in census:
            continue
        df = pd.DataFrame(json.loads(Path(p).read_text())["filings"]["recent"])
        df["t"] = t
        fr.append(df)
    df = pd.concat(fr, ignore_index=True)
    df = df[(df.filingDate >= "2024-01-01") & (df.filingDate <= "2026-10-06")]
    acc = pd.to_datetime(df.acceptanceDateTime, utc=True, errors="coerce").dt.tz_convert("America/New_York")
    df["acc_day"] = pd.to_datetime(acc.dt.strftime("%Y-%m-%d"))
    df["acc_hr"] = acc.dt.hour + acc.dt.minute / 60
    df["rep"] = pd.to_datetime(df.reportDate, errors="coerce")
    out = []
    w = out.append
    for name, mask in [("8-K 事件日→接收", df.form == "8-K"), ("Form 4 交易日→接收", df.form == "4"),
                       ("10-Q 报告期末→接收", df.form == "10-Q"), ("10-K 报告期末→接收", df.form == "10-K"),
                       ("20-F 报告期末→接收", df.form == "20-F")]:
        s = df[mask].dropna(subset=["rep"])
        bd = np.busday_count(s.rep.values.astype("datetime64[D]"), s.acc_day.values.astype("datetime64[D]"))
        q = np.percentile(bd, [50, 90, 99]) if len(bd) else [np.nan] * 3
        w(f"{name}：{len(s)} 条；相隔工作日 中位 {q[0]:.0f}，90% 分位 {q[1]:.0f}，99% 分位 {q[2]:.0f}，最大 {bd.max() if len(bd) else 'na'}")
    e = df[(df.form == "8-K") & df["items"].astype(str).str.contains("2.02")]
    bins = [0, 9.5, 16, 24.01]
    w(f"8-K 2.02 业绩发布 {len(e)} 条，接收时刻（美东）：" +
      str(pd.cut(e.acc_hr, bins, right=False, labels=["盘前", "盘中", "盘后"]).value_counts(sort=False).to_dict()))
    (HERE / "13-edgar_lags_out.txt").write_text("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
