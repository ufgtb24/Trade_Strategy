"""13 外部信息 · 解析 EDGAR 申报清单：目标池样本的覆盖、各类申报的数量、时间戳。

读 scratchpad/13/dl-sec-sub/（13-edgar_fetch.py 下载的 submissions JSON，视为不可信，只取字段）。
统计窗口 2024-01-01 ～ 2026-10-06。
  - 申报人类别：窗口内交 10-Q/10-K 的算美国本土申报人；交 20-F/40-F/6-K 的算外国申报人。
  - 各类申报的条数：8-K 及其事项编号、内部人交易（Form 4）、增发相关（S-1/S-3/F-1/F-3/424B*）、
    大股东持股（13D/13G）、财报（10-Q/10-K/20-F/6-K）。
  - 时间戳：acceptanceDateTime 是 UTC（已用申报索引页核对：JSON 的 20:38:39Z = 索引页 16:38:39 美东），
    换成美东时间，看几成在盘后（16:00 以后）、几成的「申报日期」晚于实际接收日。
  - 清单深度：recent 段是否已覆盖到 2024-01-01，不够的列出要补拉的翻页文件。
输出：本目录 13-edgar_analyze_out.txt
运行：uv run python -I .scratch/selection-pattern/scripts/13-edgar_analyze.py
"""
from __future__ import annotations

import glob
import json
import os
from collections import Counter
from pathlib import Path

import pandas as pd

SCR = Path("/tmp/claude-1000/-home-yu-PycharmProjects-Trade-Strategy/151ccac1-47bb-476f-8b64-dc09e9407cc5/scratchpad/13")
HERE = Path(os.path.abspath(__file__)).parent
W0, W1 = "2024-01-01", "2026-10-06"
OFFER = ("S-1", "S-1/A", "S-3", "S-3/A", "F-1", "F-1/A", "F-3", "F-3/A", "S-3ASR", "F-3ASR")


def load_rows(path, more_dir):
    d = json.loads(Path(path).read_text())
    frames = [pd.DataFrame(d["filings"]["recent"])]
    for f in d["filings"].get("files", []):
        p = more_dir / f["name"]
        if p.exists():
            frames.append(pd.DataFrame(json.loads(p.read_text())))
    df = pd.concat(frames, ignore_index=True)
    return d, df


def fam(form):
    f = form.upper()
    if f in ("8-K", "8-K/A"):
        return "8-K"
    if f in ("4", "4/A"):
        return "Form4"
    if f in ("10-Q", "10-K", "10-Q/A", "10-K/A", "10-KT"):
        return "10-Q/K"
    if f in ("20-F", "40-F", "20-F/A", "40-F/A"):
        return "20-F/40-F"
    if f in ("6-K", "6-K/A"):
        return "6-K"
    if f in OFFER or f.startswith("424B"):
        return "增发相关"
    if "13D" in f or "13G" in f:
        return "13D/13G"
    if f.startswith("25"):
        return "Form25"
    return "其他"


def main():
    more_dir = SCR / "dl-sec-sub-more"
    # 普查样本只算落在默认池（剔封闭式基金与 SPAC 壳）里的
    ext = set(pd.read_csv(SCR / "pool_ever_ext.csv").symbol)
    census = set((SCR / "sample_census150.txt").read_text().split()) & ext
    rows, need_more, items_all, hours = [], [], Counter(), []
    late_date = 0
    tot_acc = 0
    for p in sorted(glob.glob(str(SCR / "dl-sec-sub/*.json"))):
        t = os.path.basename(p).split("__")[0]
        d, df = load_rows(p, more_dir)
        earliest = df["filingDate"].min()
        files = d["filings"].get("files", [])
        covered = earliest <= W0 or not files or all((more_dir / f["name"]).exists() for f in files)
        if not covered:
            need_more += [f["name"] for f in files if f["filingTo"] >= W0]
        win = df[(df["filingDate"] >= W0) & (df["filingDate"] <= W1)].copy()
        win["fam"] = win["form"].map(fam)
        c = win["fam"].value_counts().to_dict()
        k8 = win[win["fam"] == "8-K"]
        it = Counter(i for s in k8["items"] for i in str(s).split(",") if i)
        if t in census:
            items_all.update({k: v for k, v in it.items()})
        acc = pd.to_datetime(win["acceptanceDateTime"], utc=True, errors="coerce").dt.tz_convert("America/New_York")
        if t in census:
            hours += list(acc.dt.hour + acc.dt.minute / 60)
            late_date += int((acc.dt.strftime("%Y-%m-%d") != win["filingDate"]).sum())
            tot_acc += int(acc.notna().sum())
        kind = "本土" if c.get("10-Q/K", 0) else ("外国" if c.get("20-F/40-F", 0) or c.get("6-K", 0) else "窗口内无定期报告")
        rows.append(dict(t=t, census=t in census, kind=kind, sic=d.get("sic") or "", cat=d.get("category") or "",
                         ex=",".join(d.get("exchanges") or []), covered=covered, n_win=len(win),
                         k8=c.get("8-K", 0), f4=c.get("Form4", 0), offer=c.get("增发相关", 0),
                         s13=c.get("13D/13G", 0), q=c.get("10-Q/K", 0), f20=c.get("20-F/40-F", 0), k6=c.get("6-K", 0),
                         i202=it.get("2.02", 0), i301=it.get("3.01", 0), i302=it.get("3.02", 0),
                         i503=it.get("5.03", 0), i101=it.get("1.01", 0), i701=it.get("7.01", 0), i801=it.get("8.01", 0)))
    R = pd.DataFrame(rows)
    out = []
    w = out.append
    w(f"窗口 {W0} ～ {W1}；样本 {len(R)} 只有 CIK（另 1 只 FRBA 在 SEC 代码表里查不到）")
    w(f"清单深度未覆盖到窗口起点、需要补拉翻页的：{sum(~R.covered)} 只；翻页文件 {sorted(set(need_more))}")
    C = R[R.census]
    w(f"\n== 普查 {len(C)} 只（随机 150 只里落在默认池、且查到 CIK 的） ==")
    w("申报人类别：" + str(C.kind.value_counts().to_dict()))
    w("有 SIC 行业码：" + str((C.sic != "").sum()))
    w("交易所：" + str(Counter(C.ex).most_common(6)))
    for col, name in [("k8", "8-K"), ("f4", "内部人交易 Form 4"), ("offer", "增发相关 S-1/S-3/F-1/F-3/424B"),
                      ("s13", "13D/13G 大股东持股"), ("q", "10-Q/10-K"), ("k6", "6-K"),
                      ("i202", "8-K 2.02 业绩发布"), ("i301", "8-K 3.01 不符合挂牌标准/摘牌通知"),
                      ("i302", "8-K 3.02 未登记发行股份"), ("i503", "8-K 5.03 章程修订（反向拆股常走这一项）"),
                      ("i101", "8-K 1.01 重大协议"), ("i701", "8-K 7.01 公平披露"), ("i801", "8-K 8.01 其他事项")]:
        for kind in ("本土", "外国"):
            sub = C[C.kind == kind][col]
            if len(sub) == 0:
                continue
            w(f"  {name:<34s} {kind}({len(sub)}只)：有过的 {int((sub > 0).sum())} 只，"
              f"每只中位 {sub.median():.0f} 条，合计 {int(sub.sum())} 条（约 2.75 年）")
    w("\n8-K 事项编号出现次数（普查样本合计，前 15）：" + str(items_all.most_common(15)))
    h = pd.Series(hours)
    w(f"\n== 接收时间（美东）分布，普查样本窗口内全部申报 {len(h)} 条 ==")
    bins = [0, 9.5, 16, 17.5, 22, 24.01]
    lab = ["开盘前(<9:30)", "盘中(9:30-16:00)", "收盘后到17:30", "17:30-22:00", "22:00后"]
    w(str(pd.cut(h, bins, right=False, labels=lab).value_counts(sort=False).to_dict()))
    w(f"申报日期与美东接收日期不同的：{late_date}/{tot_acc}")
    w("\n== 逐只明细（前 24 只是三个日期的抽样） ==")
    w(R.sort_values(["census", "t"]).to_string(index=False))
    (HERE / "13-edgar_analyze_out.txt").write_text("\n".join(out) + "\n")
    print("\n".join(out[:60]))


if __name__ == "__main__":
    main()
