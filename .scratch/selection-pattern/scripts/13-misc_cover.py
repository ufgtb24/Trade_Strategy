"""13 外部信息 · 几个免费源的格式与目标池覆盖：Nasdaq 财报日历、SEC 交割失败数据、StockTwits、CBOE VIX。

读 scratchpad/13/dl-*/body（视为不可信，只取字段；压缩包在内存里读，不解到磁盘）。
只看覆盖、字段和时间戳，不碰任何涨跌。
输出：本目录 13-misc_cover_out.txt
运行：uv run python -I .scratch/selection-pattern/scripts/13-misc_cover.py
"""
from __future__ import annotations

import io
import json
import os
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

SCR = Path("/tmp/claude-1000/-home-yu-PycharmProjects-Trade-Strategy/151ccac1-47bb-476f-8b64-dc09e9407cc5/scratchpad")
HERE = Path(os.path.abspath(__file__)).parent
POOL = "dv2M_px20_cap100M"  # 默认池：剔封闭式基金与 SPAC 壳


def pool_on(d):
    z = np.load(SCR / "09/panel.npz", allow_pickle=True)
    symbols, cal = z["symbols"], pd.DatetimeIndex(z["calendar"])
    m = np.load(SCR / "09/pool_masks.npz", allow_pickle=True)[POOL]
    i = cal.get_indexer([pd.Timestamp(d)], method="ffill")[0]
    return set(symbols[m[:, i]])


def main():
    out = []
    w = out.append
    for name, d in (("dl-nasdaq-earn", "2024-02-14"), ("dl-nasdaq-earn2", "2026-08-12")):
        x = json.loads((SCR / "13" / name / "body").read_text())
        rows = pd.DataFrame(x["data"]["rows"])
        pool = pool_on(d)
        pr = rows[rows.symbol.isin(pool)]
        ests = pd.to_numeric(pr["noOfEsts"], errors="coerce").fillna(0)
        w(f"Nasdaq 财报日历 {d}：全表 {len(rows)} 行，字段 {list(rows.columns)}；其中目标池 {len(pr)} 只，"
          f"有分析师预期的 {int((ests > 0).sum())} 只，时段分布 {pr['time'].value_counts().to_dict()}")
    z = zipfile.ZipFile(io.BytesIO((SCR / "13/dl-sec-ftd/body").read_bytes()))
    nm = z.namelist()[0]
    ftd = pd.read_csv(z.open(nm), sep="|", dtype=str, encoding="latin-1", on_bad_lines="skip")
    ftd.columns = [c.strip() for c in ftd.columns]
    w(f"SEC 交割失败 {nm}：{len(ftd)} 行，字段 {list(ftd.columns)}，结算日 {ftd.iloc[:, 0].min()}～{ftd.iloc[:, 0].max()}")
    for d in ("20240102", "20240110"):
        day = ftd[ftd.iloc[:, 0] == d]
        pool = pool_on(f"{d[:4]}-{d[4:6]}-{d[6:]}")
        w(f"  {d}：当天 {len(day)} 只证券有交割失败；目标池 {len(pool)} 只中出现 {len(pool & set(day['SYMBOL']))} 只")
    st = json.loads((SCR / "13/dl-stocktwits/body").read_text())
    msgs = st.get("messages", [])
    if msgs:
        ts = [m_["created_at"] for m_ in msgs]
        lab = sum(1 for m_ in msgs if (m_.get("entities") or {}).get("sentiment"))
        w(f"StockTwits SHLS 首页：{len(msgs)} 条，时间 {min(ts)} ～ {max(ts)}，带用户自标看多/看空的 {lab} 条；"
          f"游标 {st.get('cursor')}")
    v = pd.read_csv(SCR / "13/dl-cboe-vix/body")
    w(f"CBOE VIX 日线：{len(v)} 行，{v.DATE.iloc[0]} ～ {v.DATE.iloc[-1]}")
    (HERE / "13-misc_cover_out.txt").write_text("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
