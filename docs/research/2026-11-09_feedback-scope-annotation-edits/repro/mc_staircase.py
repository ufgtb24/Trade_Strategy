"""method_critic：台阶式连续阶跃（user_sim2 的反例）下，第二次阶跃的样本按默认推断会收哪些成员框。
假想：在 INDO、CRNC 下一次阶跃后放一个正样本，并照用户习惯画一个从阶跃前很早开始的「站上新平台」框。
只在内存里加框，不写标注；只经 read_annotations / read_bars 读。"""
from path2_web.config import load_config, view_dataset_dir
from path2_web.data import read_bars
from path2_web.annotation.store import read_annotations
from path2_web.annotation.membership import sample_members

cfg = load_config()
st = read_annotations(cfg)["state"]
fname = {f["id"]: f["name"] for f in st["features"]}
plat = next(k for k, v in fname.items() if v == "站上新平台")
charts = {c["symbol"]: c for c in st["charts"]}
cases = [("INDO", "2022-03-02", 18), ("INDO", "2022-03-02", 30), ("CRNC", "2025-01-03", 47), ("CRNC", "2025-01-03", 23)]
for sym, step, lead in cases:
    days = [d.strftime("%Y-%m-%d") for d in read_bars(view_dataset_dir(cfg), sym).index]
    i = days.index(step)
    start, sd = days[i - lead], days[i + 3]          # 框从阶跃前 lead 根画起，样本放在阶跃后第 3 根
    boxes = charts[sym]["boxes"] + [{"id": "b-hyp", "feature": plat, "start": start, "end": sd}]
    mem = sample_members(sd, boxes, days)
    old = {s["id"]: s["members"] for s in charts[sym]["samples"]}
    shared = [sid for sid, m in old.items() if set(m) & set(mem)]
    print(f"{sym} step {step} box {start}~{sd} members={mem} shares_box_with={shared}")
