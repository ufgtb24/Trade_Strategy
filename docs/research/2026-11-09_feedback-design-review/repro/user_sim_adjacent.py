"""user_sim 临时:按 episodes.txt 的买点日,数「前后 1 根 K 线内还有别的买点」的买点占比——
即单个买点反馈按 NEG_TOL=1 判冲突时,那天本身被砍掉后仍会因邻日买点而一直朱红的比例。不入库。"""
import re, ast
from path2_web.data import read_bars
D = "datasets/pkls_until_20251231"
txt = open("docs/research/2026-11-09_feedback-design-review/repro/episodes.txt").read()
blocks = re.split(r"=+ (\w+) samples ", txt)[1:]
tot = adj = 0
for sym, body in zip(blocks[::2], blocks[1::2]):
    samples = set(ast.literal_eval(body.split("\n")[0]))
    buys = set()
    for m in re.finditer(r"buys=\d+: (\[.*?\])", body):
        buys |= set(ast.literal_eval(m.group(1)))
    idx = [str(d)[:10] for d in read_bars(D, sym).index]
    pos = {d: i for i, d in enumerate(idx)}
    bl = sorted(buys)
    a = [d for d in bl if any(idx[pos[d]+k] in buys for k in (-1, 1) if 0 <= pos[d]+k < len(idx))]
    a_s = [d for d in bl if any(idx[pos[d]+k] in samples for k in (-1, 1) if 0 <= pos[d]+k < len(idx))]
    print(sym, "buys", len(bl), "adjacent-to-other-buy", len(a), "adjacent-to-pos-sample", a_s)
    tot += len(bl); adj += len(a)
print("total", tot, "adjacent", adj, f"{adj/tot:.0%}")
