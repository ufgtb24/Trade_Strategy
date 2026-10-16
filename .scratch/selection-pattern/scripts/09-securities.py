"""09 目标池票 · 证券类别：哪些代码不是普通股。

两套口径，互相核对：
  A. 按名称：Nasdaq 网站股票筛选器的下载件（三个交易所的当前挂牌证券，含证券全名与当前市值），
     名称里写明是票据 / 债券、优先股、认股权证、SPAC 单位、权利的，判为非普通股；
     封闭式基金、SPAC 壳（尚未完成合并的 Acquisition Corp）单列，是否剔除另议。
  B. 按代码：5 位代码以 U / W / R 结尾（SPAC 单位、认股权证、权利），或含 - / .（优先股、类别股）。
名称只读当前挂牌的，证券类别不随时间变（票据一直是票据），所以不构成前视。

下载件当作不可信数据，只解析字段；放在 scratchpad/09/dl-nq/，由本目录外的命令下载：
  api.nasdaq.com/api/screener/stocks?tableonly=true&limit=10000&download=true&exchange={nasdaq,nyse,amex}

输出：scratchpad/09/securities.csv（symbol, name, mcap, cls, sym_rule）与本目录 09-securities_out.txt
运行：uv run python -I .scratch/selection-pattern/scripts/09-securities.py
"""
from __future__ import annotations

import glob
import json
import os
import re

import pandas as pd

ROOT = "/home/yu/PycharmProjects/Trade_Strategy"
SCR = "/tmp/claude-1000/-home-yu-PycharmProjects-Trade-Strategy/151ccac1-47bb-476f-8b64-dc09e9407cc5/scratchpad/09"
HERE = os.path.dirname(os.path.abspath(__file__))

# 顺序即优先级：先命中者为准
RULES = [
    ("adr", r"American Depositary|\bADS\b|\bADR\b"),
    ("debt", r"\b(?:Notes?|Debentures?|Baby Bonds?)\b(?!.*Common Stock)"),
    ("preferred", r"Preferred|Preference Shares|Trust Preferred|Perpetual"),
    ("mlp", r"Limited Partner|\bL\.?P\.?(?:\s|$)|Partnership Units|Common Units|Partners\b.*Units"),
    ("warrant", r"\bWarrants?\b"),
    ("right", r"\bRights?\b|Contingent Value"),
    ("unit", r"\bUnits?\b"),
    ("structured", r"STRATS|Trust Certificates|Corporate Backed Trust|PPLUS|SATURNS|CABCO"),
    ("cef", r"\bFund\b|Closed[- ]End|Municipal|Muni\b|Income Trust\b|Opportunities Trust|"
            r"Income Securities|High Yield|Credit Strategies|Dividend Trust|Bond\b"),
    ("spac_shell", r"(?i:Acquisition (?:Corp|Corporation|Company|Co\b|Ltd|Limited|Inc)|Acquisition Holdings)|\bSPAC\b"),
]
# 当前挂牌名单里找不到名称、代码规则又没命中的：人工核过的非普通股（STRATS 信托与资本信托证券）
MANUAL = {"GJP": "structured", "GJR": "structured", "GJT": "structured", "NHPBP": "preferred", "DDT": "preferred"}


def classify(name: str) -> str:
    if not isinstance(name, str) or not name:
        return "unknown"
    for cls, pat in RULES:
        flags = 0 if cls == "spac_shell" else re.I
        if re.search(pat, name, flags=flags):
            return cls
    return "common"


def sym_rule(s: str) -> bool:
    return bool(re.search(r"[-.]", s)) or (len(s) == 5 and s[-1] in "UWR")


def main():
    rows = []
    for ex in ("nasdaq", "nyse", "amex"):
        for rw in json.load(open(f"{SCR}/dl-nq/screener_{ex}.json"))["data"]["rows"]:
            rows.append({"nsym": str(rw["symbol"]).strip(), "name": rw.get("name"),
                         "mcap": pd.to_numeric(rw.get("marketCap"), errors="coerce"), "ex": ex})
    sc = pd.DataFrame(rows)
    sc["symbol"] = sc["nsym"].str.replace("/", "-").str.replace("^", "-P", regex=False)
    sc = sc.drop_duplicates("symbol").set_index("symbol")
    ours = sorted(os.path.basename(p)[:-4] for p in glob.glob(f"{ROOT}/datasets/pkls/*.pkl"))
    df = pd.DataFrame({"symbol": ours}).set_index("symbol").join(sc[["name", "mcap", "ex"]])
    df["cls"] = df["name"].map(classify)
    df["sym_rule"] = [sym_rule(s) for s in df.index]
    for s, c in MANUAL.items():
        if s in df.index and df.at[s, "cls"] == "unknown":
            df.at[s, "cls"] = c
    unk = (df["cls"] == "unknown") & df["sym_rule"]
    df.loc[unk, "cls"] = [{"U": "unit", "W": "warrant", "R": "right"}.get(s[-1], "other") for s in df.index[unk]]
    df.reset_index().to_csv(f"{SCR}/securities.csv", index=False)

    lines = []
    w = lines.append
    w(f"本地股票 {len(df)}；在当前挂牌名单里找到名称的 {df['name'].notna().sum()}，没找到的 {df['name'].isna().sum()}")
    w("")
    w("按名称分类（cls）：")
    vc = df["cls"].value_counts()
    for c, n in vc.items():
        ex = df[df["cls"] == c].head(8)
        w(f"  {c}: {n}  例：" + "；".join(f"{s}={str(nm)[:60]}" for s, nm in zip(ex.index, ex["name"])))
    w("")
    w("按代码规则（5 位以 U/W/R 结尾或含 - .）命中的：%d" % df["sym_rule"].sum())
    w("  其中按名称的分类：" + str(df.loc[df["sym_rule"], "cls"].value_counts().to_dict()))
    w("  名称判为 common/adr 但代码规则命中的：" +
      str(df.loc[df["sym_rule"] & df["cls"].isin(["common", "adr"]), "name"].head(20).to_dict()))
    w("")
    w("没找到名称、按普通股处理（unknown）的代码：" + ", ".join(df.index[df["cls"] == "unknown"]))
    w("")
    for c in ("debt", "preferred", "structured", "cef", "spac_shell", "mlp", "unit", "right"):
        sub = df[df["cls"] == c]
        w(f"== {c} 全部 {len(sub)} 个 ==")
        w("; ".join(f"{s}={str(nm)[:50]}" for s, nm in zip(sub.index, sub["name"])))
    out = "\n".join(lines)
    print(out)
    open(f"{HERE}/09-securities_out.txt", "w").write(out + "\n")


if __name__ == "__main__":
    main()
