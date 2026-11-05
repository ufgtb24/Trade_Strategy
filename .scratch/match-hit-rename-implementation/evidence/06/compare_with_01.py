"""票 06：拿终检的 e2e 结果和票 01 开工时的基线逐条比。在仓库根目录运行。
基线里的 spec 文件名和用例名是改名前的，这里按改名对照换成新名再比；行号不比（改名后个别用例挪了行）。
miss-detection-walkthrough 这个文件数据墙不跑，只列出基线里它的结果，不算进比较。
用法：python compare_with_01.py <基线结果> <终检结果>；只输出差异和计数。"""
import re
import sys

RENAME = [("match-event-disambig", "hit-event-disambig"), ("setCandidateMatches", "setCandidateHits"),
          ("multi-match", "multi-hit"), ("Detected → Qualified → Matched", "detected → qualified → in_hit")]
LINE = re.compile(r"^([✓✘-]) (e2e/[^:]+):\d+:\d+ › (.*)$")


def load(path):
    out = {}
    for raw in open(path, encoding="utf-8").read().splitlines():
        m = LINE.match(raw)
        status, spec, title = m.groups()
        key = f"{spec} › {title}"
        for a, b in RENAME:
            key = key.replace(a, b)
        out[key] = status
    return out


base, after = load(sys.argv[1]), load(sys.argv[2])
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
