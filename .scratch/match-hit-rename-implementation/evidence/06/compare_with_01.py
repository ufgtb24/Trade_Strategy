"""票 06：拿终检的 e2e 结果和票 01 开工时的基线逐条比。在仓库根目录运行。
基线里的 spec 文件名和用例名是改名前的，这里按改名对照换成新名再比；行号不比（改名后个别用例挪了行）。
miss-detection-walkthrough 这个文件数据墙不跑，只列出基线里它的结果，不算进比较。
基线重跑结果里有的用例，以重跑为准：annotate-rally-random 第 145 行在检出里有 .venv 时报 ENOBUFS，基线首轮跑到它时还没有
.venv，票 01 在基线代码上、有 .venv 的条件下重跑过这个文件。终检的检出里有 .venv，要比就比同样的条件。
用法：python compare_with_01.py <基线结果> <基线重跑结果> <终检结果>；只输出差异和计数。"""
import re
import sys

RENAME = [("match-event-disambig", "hit-event-disambig"), ("setCandidateMatches", "setCandidateHits"),
          ("multi-match", "multi-hit"), ("Detected → Qualified → Matched", "detected → qualified → in_hit")]
LINE = re.compile(r"^([✓✘-]) (e2e/[^:]+):\d+:\d+ › (.*)$")


def load(path):
    """读 e2e_results.py 的输出，返回 {换成新名的 spec 与用例名: 状态}。"""
    out = {}
    for raw in open(path, encoding="utf-8").read().splitlines():
        m = LINE.match(raw)
        status, spec, title = m.groups()
        key = f"{spec} › {title}"
        for a, b in RENAME:
            key = key.replace(a, b)
        out[key] = status
    return out


base, rerun, after = load(sys.argv[1]), load(sys.argv[2]), load(sys.argv[3])
overridden = {k: (base[k], v) for k, v in rerun.items() if k in base and base[k] != v}
base.update(rerun)
print("基线里以重跑为准的：" + "；".join(f"{k}：首轮 {a}，重跑 {b}" for k, (a, b) in overridden.items()))
skipped = {k: v for k, v in base.items() if "miss-detection-walkthrough" in k}
base = {k: v for k, v in base.items() if k not in skipped}
print(f"基线 {len(base)} 条（另有 miss-detection-walkthrough {len(skipped)} 条不跑：" +
      "、".join(f"{s} {list(skipped.values()).count(s)}" for s in sorted(set(skipped.values()))) + "）；终检 " + str(len(after)) + " 条")
for name, d in (("基线", base), ("终检", after)):
    print(f"{name}：" + "、".join(f"{s} {list(d.values()).count(s)}" for s in "✓✘-"))
only_base = sorted(set(base) - set(after))
only_after = sorted(set(after) - set(base))
changed = sorted(k for k in set(base) & set(after) if base[k] != after[k])
print(f"只在基线：{only_base}\n只在终检：{only_after}")
print("状态不同：")
for k in changed:
    print(f"  {k}：{base[k]} → {after[k]}")
print(f"结论：状态不同 {len(changed)} 条")
