"""13 外部信息 · SEC 内部人交易结构化数据集（季度包）对目标池的作用面：一个季度里池内有几只出现公开市场买入。

读 scratchpad/13/dl-sec-insider/body（2024 年一季度 form345 压缩包，视为不可信，内存里按制表符分列）。
公开市场买入 = 交易代码 P；卖出 = S；其余大多是授予、行权、代扣税，不代表主动看多看空。
池子取季度内任一天在池的股票（scratchpad/09 的池子表）。只数条数和只数，不碰任何涨跌。
输出：本目录 13-insider_cover_out.txt
运行：uv run python -I .scratch/selection-pattern/scripts/13-insider_cover.py
"""
from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

SCR = Path("/tmp/claude-1000/-home-yu-PycharmProjects-Trade-Strategy/151ccac1-47bb-476f-8b64-dc09e9407cc5/scratchpad")
HERE = Path(os.path.abspath(__file__)).parent
POOL = "dv2M_px20_cap100M"  # 默认池：剔封闭式基金与 SPAC 壳


def main():
    z = np.load(SCR / "09/panel.npz", allow_pickle=True)
    symbols, cal = z["symbols"], pd.DatetimeIndex(z["calendar"])
    m = np.load(SCR / "09/pool_masks.npz", allow_pickle=True)[POOL]
    q = (cal >= "2024-01-01") & (cal <= "2024-03-31")
    pool = set(symbols[m[:, q].any(1)])
    zf = zipfile.ZipFile(SCR / "13/dl-sec-insider/body")
    sub = pd.read_csv(zf.open("SUBMISSION.tsv"), sep="\t", dtype=str)
    tr = pd.read_csv(zf.open("NONDERIV_TRANS.tsv"), sep="\t", dtype=str, usecols=lambda c: c in (
        "ACCESSION_NUMBER", "TRANS_CODE", "TRANS_DATE", "TRANS_SHARES", "TRANS_PRICEPERSHARE"))
    sub["sym"] = sub["ISSUERTRADINGSYMBOL"].str.upper().str.strip()
    t = tr.merge(sub[["ACCESSION_NUMBER", "sym", "DOCUMENT_TYPE", "FILING_DATE"]], on="ACCESSION_NUMBER")
    out = []
    w = out.append
    w(f"2024Q1 数据集：申报 {len(sub)} 份，非衍生品交易 {len(tr)} 行；SUBMISSION 字段 {list(sub.columns)}")
    w(f"季度内曾在池 {len(pool)} 只；其中有任何 Form 3/4/5 申报的 {len(pool & set(sub.sym))} 只")
    tp = t[t.sym.isin(pool)]
    w("池内交易代码分布（行数，前 8）：" + str(tp.TRANS_CODE.value_counts().head(8).to_dict()))
    for code, name in (("P", "公开市场买入"), ("S", "公开市场卖出")):
        k = tp[tp.TRANS_CODE == code]
        w(f"  {name}：池内 {k.sym.nunique()} 只出现过（占池 {k.sym.nunique()/len(pool):.1%}），{k.ACCESSION_NUMBER.nunique()} 份申报")
    (HERE / "13-insider_cover_out.txt").write_text("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
