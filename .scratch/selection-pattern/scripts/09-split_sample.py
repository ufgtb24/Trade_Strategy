"""09 目标池票 · 当时价格还原不了时，用复权价设价格上限会错放多少（只用最近半年的拆合股记录估量级）。

Yahoo 在当前出口连不上（TLS 握手被切断），拆合股全历史拿不到。Nasdaq 网站的拆合股日历只给最近约半年
（2026-04 至今）的记录，用它做一个样本：
  某次拆合股（a 股换 b 股，r = a/b）之前的每一天，当时价格 = 复权价 × r（忽略分红复权，偏差几个百分点以内）。
  数一数在成交额 ≥ X 的池子里，有多少股票日的「复权价 ≤ 上限」与「当时价格 ≤ 上限」结论相反。
只读拆合股记录与买入当天的价格，不读任何买点之后的涨跌。

下载件当作不可信数据，只解析字段：scratchpad/09/dl-nq/nasdaq_splits_recent.json（该接口忽略 date 参数，返回最近半年）
输出：本目录 09-split_sample_out.txt
运行：uv run python .scratch/selection-pattern/scripts/09-split_sample.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

SCR = Path("/tmp/claude-1000/-home-yu-PycharmProjects-Trade-Strategy/151ccac1-47bb-476f-8b64-dc09e9407cc5/scratchpad")
HERE = Path(__file__).resolve().parent


def main():
    z = np.load(SCR / "09/panel.npz", allow_pickle=True)
    symbols, calendar = list(z["symbols"]), pd.DatetimeIndex(z["calendar"])
    close, dv = z["close"], z["dv20"]
    masks = np.load(SCR / "09/pool_masks.npz")
    rows = json.load(open(SCR / "09/dl-nq/nasdaq_splits_recent.json"))["data"]["rows"]
    sp = []
    for rw in rows:
        m = re.match(r"\s*([\d.,]+)\s*:\s*([\d.,]+)", rw["ratio"])
        if not m:
            continue
        a, b = (float(x.replace(",", "")) for x in m.groups())
        d = pd.Timestamp(pd.to_datetime(rw["executionDate"], format="%m/%d/%Y"))
        sp.append((rw["symbol"].strip(), d, a / b))
    sp = pd.DataFrame(sp, columns=["symbol", "date", "r"]).drop_duplicates()
    sp = sp[(sp["date"] <= calendar[-1]) & sp["symbol"].isin(symbols)]
    lines = []
    w = lines.append
    w(f"Nasdaq 拆合股日历：{len(rows)} 条，落在本地股票、生效日 ≤ {calendar[-1].date()} 的 {len(sp)} 条"
      f"（{sp['date'].min().date()}..{sp['date'].max().date()}）；合股（r<1）{(sp['r'] < 1).sum()}，拆股 {(sp['r'] > 1).sum()}")
    w("r 的分布（新股数/旧股数）：" + str(sp["r"].describe(percentiles=[.1, .5, .9]).round(4).to_dict()))
    w("")
    base_names = ["dv1M", "dv2M", "dv5M"]
    for cap in (20, 10):
        for bn in base_names:
            pool_dv = masks[bn]          # 只按成交额与非普通股定义（价格条件另算）
            wrong_in, wrong_out, n_sym = 0, 0, 0
            for s, d, r in sp.itertuples(index=False):
                i = symbols.index(s)
                cols = calendar < d
                adj = close[i, cols]
                act = adj * r
                inpool = pool_dv[i, cols]
                a_ok, t_ok = adj <= cap, act <= cap
                wi = int((inpool & a_ok & ~t_ok).sum())    # 复权价放进来、当时其实更贵
                wo = int((inpool & ~a_ok & t_ok).sum())    # 复权价挡在外面、当时其实便宜
                wrong_in += wi
                wrong_out += wo
                n_sym += (wi + wo) > 0
            denom = int((pool_dv & (close <= cap)).sum())
            w(f"价格上限 {cap} 美元，{bn} 池：只这半年的拆合股就让 {n_sym} 只股票的历史被判错；"
              f"错放进来 {wrong_in} 个股票日，错挡在外 {wrong_out} 个股票日；"
              f"合计占「复权价 ≤{cap}」口径股票日的 {(wrong_in + wrong_out) / denom:.2%}")
    w("")
    w("外推（粗略）：拆合股大致均匀发生在 5 年里，每次只影响它之前的历史；最近半年的拆合股影响的是几乎全部历史，")
    w("更早的平均只影响一半左右。所以 5 年全部拆合股造成的错判 ≈ 上面数字 × (5 年 / 0.5 年) × 0.5 ≈ 5 倍（量级，非实测）。")
    out = "\n".join(lines)
    print(out)
    (HERE / "09-split_sample_out.txt").write_text(out + "\n")


if __name__ == "__main__":
    main()
