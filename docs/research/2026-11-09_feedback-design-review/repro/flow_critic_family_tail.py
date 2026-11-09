"""临时(flow_critic):从 episodes.txt 数每个有买点的阶跃族——买点跨度、实例跨度、最后买点之后还有几天实例;
以及每只股票的买点日数。只读 episodes.txt,不读行情。不入库。"""
import re, sys, collections
from pathlib import Path

txt = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).with_name("episodes.txt")).read_text()
sym = None
rows, buydays = [], collections.defaultdict(set)
for line in txt.splitlines():
    m = re.match(r"=+ (\w+) samples", line)
    if m:
        sym = m.group(1); continue
    m = re.match(r"\s+step (\S+)\.\.(\S+) days (\S+)\.\.(\S+) n=(\d+) buys=(\d+): \[(.*)\]", line)
    if m:
        s, e, d0, d1, n, nb, bl = m.groups()
        buys = re.findall(r"'([\d-]+)'", bl)
        buydays[sym].update(buys)
        rows.append((sym, s, e, d0, d1, int(n), buys))
print(f"{'sym':5} {'step':23} {'inst':23} n  buys first..last         tail_after_last_buy(cal days)")
import datetime as dt
D = lambda x: dt.date.fromisoformat(x)
tails = []
for sym, s, e, d0, d1, n, buys in rows:
    tail = (D(d1) - D(buys[-1])).days
    tails.append(tail)
    print(f"{sym:5} {s}..{e} {d0}..{d1} {n:2} {len(buys):2} {buys[0]}..{buys[-1]}  {tail}")
print("families with buys:", len(rows), " median tail (calendar days):", sorted(tails)[len(tails)//2])
print("families whose instances run >=14 calendar days past last buy:", sum(t >= 14 for t in tails))
print("unique buy days per stock:", {k: len(v) for k, v in buydays.items()}, " total:", sum(len(v) for v in buydays.values()))

# hits 行按 hit 起点折族;new_step 的 hit 起点 = 旧平台起点 = 阶跃起点往前固定长度,所以同一阶跃起点的几种前缀是一行。
rows_by_start = collections.defaultdict(lambda: [None, None, set()])
for sym, s, e, d0, d1, n, buys in rows:
    g = rows_by_start[(sym, s)]
    g[0] = max(g[0] or d1, d1)
    g[2].update(buys)
folded = [(k, v[0], sorted(v[2])) for k, v in rows_by_start.items()]
ft = [(D(last) - D(b[-1])).days for k, last, b in folded]
print("folded hits rows:", len(folded), " median tail:", sorted(ft)[len(ft)//2], " rows with tail>=14:", sum(t >= 14 for t in ft))
