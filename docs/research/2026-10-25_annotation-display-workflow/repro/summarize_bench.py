"""汇总 out_bench.json:每项取 200 只股票的中位数 / 95 分位 / 最慢。"""
import json
import statistics
from pathlib import Path

d = json.loads((Path(__file__).resolve().parent / "out_bench.json").read_text())
rows = d["rows"]


def q(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))]


def line(name, xs, unit="ms"):
    print(f"  {name:28s} 中位 {statistics.median(xs):8.1f}  p95 {q(xs, .95):8.1f}  最慢 {max(xs):8.1f} {unit}")


print(f"样本 {d['n']} 只")
line("读一只股票的 K 线", [r["load_ms"] for r in rows])
for w in ("view1y", "train4y"):
    print(f"== {w}  根数中位 {statistics.median(r[w]['bars'] for r in rows)}")
    for app in ("bb_v1", "bottom_burst"):
        line(f"{app} analyze", [r[w][app]["analyze_ms"] for r in rows])
        line(f"{app} node 诊断", [r[w][app]["diagnose_ms"] for r in rows])
        line(f"{app} 序列化", [r[w][app]["serialize_ms"] for r in rows])
        line(f"{app} 事件数", [r[w][app]["n_events"] for r in rows], "个")
        line(f"{app} JSON", [r[w][app]["json_bytes"] / 1024 for r in rows], "KB")
    for k in rows[0][w]["atoms"]:
        line(f"atom {k}", [r[w]["atoms"][k]["ms"] for r in rows])
    for k in rows[0][w]["atoms"]:
        line(f"atom {k} 事件数", [r[w]["atoms"][k]["n"] for r in rows], "个")
    line("全家桶 引擎", [r[w]["all_atoms"]["engine_ms"] for r in rows])
    line("全家桶 序列化", [r[w]["all_atoms"]["serialize_ms"] for r in rows])
    line("全家桶 引擎+序列化", [r[w]["all_atoms"]["engine_ms"] + r[w]["all_atoms"]["serialize_ms"] for r in rows])
    line("全家桶 事件数", [r[w]["all_atoms"]["n_events"] for r in rows], "个")
    line("全家桶 JSON", [r[w]["all_atoms"]["json_bytes"] / 1024 for r in rows], "KB")
    line("全家桶 JSON gzip", [r[w]["all_atoms"]["json_gz"] / 1024 for r in rows], "KB")
    # 显示所有 detector 比只显示 bb_v1 多花多少(同一只股票的比值)
    ratio = [(r[w]["all_atoms"]["engine_ms"] + r[w]["all_atoms"]["serialize_ms"]) /
             (r[w]["bb_v1"]["analyze_ms"] + r[w]["bb_v1"]["serialize_ms"]) for r in rows]
    line("全家桶 / bb_v1 倍数", ratio, "倍")
    extra = [(r[w]["all_atoms"]["engine_ms"] + r[w]["all_atoms"]["serialize_ms"]) -
             (r[w]["bb_v1"]["analyze_ms"] + r[w]["bb_v1"]["serialize_ms"]) for r in rows]
    line("全家桶 比 bb_v1 多花", extra)
tot = [r["train4y"]["all_atoms"]["engine_ms"] + r["train4y"]["all_atoms"]["serialize_ms"] + r["load_ms"] for r in rows]
mean = statistics.mean(tot)
print(f"全池 5778 只 × 4 年全家桶:单核 {mean * 5778 / 1000 / 60:.1f} 分钟;按 26 进程理想并行 {mean * 5778 / 1000 / 26:.0f} 秒")
gz = statistics.mean(r["train4y"]["all_atoms"]["json_gz"] for r in rows)
raw = statistics.mean(r["train4y"]["all_atoms"]["json_bytes"] for r in rows)
print(f"全池存储(4 年全家桶 JSON):原始 {raw * 5778 / 2**20:.0f} MB,gzip {gz * 5778 / 2**20:.0f} MB")
