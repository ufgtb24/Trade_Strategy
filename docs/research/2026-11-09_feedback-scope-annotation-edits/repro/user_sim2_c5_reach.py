"""user_sim2 C5 场景：app 多买的日子里，补一个正样本要几下。

口径：从 episodes.txt 抄出 new_step 第二版在 6 只股票上的买点日（去重）；去掉用户已有的样本日。
对每个多买日，看现有「站上新平台」框里有没有一个终点 <= 这天、且相隔 <= GAP(20) 根 K 线的
（spec 5.5 成员框自动推断第 2 步的第一跳）。有 → 放 point 一下就自动带上依据框；没有 → 要先画框。
另记这一天之后 20 根 K 线的收益（只为看「看得见后续走势时，补哪些日子会被结果带偏」）。
"""
import re
from pathlib import Path
import pandas as pd
from path2_web.config import load_config
from path2_web.annotation.store import read_annotations
from path2_web.data import read_bars

HERE = Path(__file__).resolve()
EP = HERE.parents[2] / "2026-11-09_feedback-design-review/repro/episodes.txt"
GAP = 20
FWD = 20

buys: dict[str, set] = {}
sym = None
for line in EP.read_text().splitlines():
    m = re.match(r"=+ (\w+) samples", line)
    if m:
        sym = m.group(1); buys[sym] = set(); continue
    m = re.search(r"buys=\d+: (\[.*\])", line)
    if m and sym:
        buys[sym] |= set(eval(m.group(1)))

st = read_annotations(load_config())["state"]
feat = {f["id"]: f["name"] for f in st["features"]}
rows = []
for c in st["charts"]:
    s = c["symbol"]
    if s not in buys:
        continue
    df = read_bars("datasets/pkls_until_20251231", s)
    idx = {d.strftime("%Y-%m-%d"): i for i, d in enumerate(df.index)}
    close = df["close"].values
    sdates = {x["date"] for x in c["samples"]}
    boxes = [b for b in c["boxes"] if feat.get(b["feature"]) == "站上新平台"]
    for d in sorted(buys[s]):
        if d in sdates:
            continue
        i = idx[d]
        reach = [b["id"] for b in boxes if b["end"] <= d and i - idx[b["end"]] <= GAP]
        fwd = close[i + FWD] / close[i] - 1 if i + FWD < len(close) else float("nan")
        rows.append(dict(symbol=s, date=d, one_click=bool(reach), fwd20=round(fwd * 100, 1)))
out = pd.DataFrame(rows)
print(out.to_string())
print()
print(out.groupby("one_click").agg(n=("date", "size"), fwd20_median=("fwd20", "median")))
print("total extra buy days", len(out))

# ---- 第二部分：用真正的成员推断（path2_web.annotation.membership.sample_members）核一遍，
# 并算「底部平稳」在正样本里的占比，在三种补法下怎么变（先删掉 SMX 2025-11-24）。
from path2_web.annotation.membership import sample_members
from path2_web.config import view_dataset_dir

cfg = load_config()
pos_feats = []   # 每个正样本收的特征名集合
added = {"crnc_only": [], "all23": []}
for c in st["charts"]:
    s = c["symbol"]
    days = [d.strftime("%Y-%m-%d") for d in read_bars(view_dataset_dir(cfg), s).index]
    bx = {b["id"]: b for b in c["boxes"]}
    for x in c["samples"]:
        if s == "SMX" and x["date"] == "2025-11-24":
            continue
        pos_feats.append({feat.get(bx[m]["feature"]) for m in x["members"]})
    for r in rows:
        if r["symbol"] != s or not r["one_click"]:
            continue
        mem = sample_members(r["date"], c["boxes"], days)
        names = {feat.get(bx[m]["feature"]) for m in mem}
        added["all23"].append(names)
        if s == "CRNC":
            added["crnc_only"].append(names)
        print("  add", s, r["date"], sorted(n for n in names if n))

def share(lst, name):
    k = sum(name in f for f in lst)
    return f"{k}/{len(lst)}"

for label, extra in [("现状(删 SMX 11-24 后)", []), ("只补 CRNC 一键的", added["crnc_only"]), ("23 个一键的全补", added["all23"])]:
    lst = pos_feats + extra
    print(label, "底部平稳", share(lst, "底部平稳"), "站上新平台", share(lst, "站上新平台"))
