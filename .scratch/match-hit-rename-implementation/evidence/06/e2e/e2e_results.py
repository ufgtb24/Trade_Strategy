"""从 playwright list 报告日志里取每条测试的结果（✓/✘/-），去掉耗时，按 spec:行号 排。用法：python e2e_results.py <日志>... > 结果"""
import re, sys
out = {}
for p in sys.argv[1:]:
    for l in open(p, encoding="utf-8", errors="replace").read().splitlines():
        m = re.match(r"^\s+([✓✘-])\s+\d+\s+(e2e/\S+:\d+:\d+)\s+›\s+(.*?)(?:\s+\([\d.]+m?s\))?$", l)
        if m:
            out[m.group(2)] = (m.group(1), m.group(3))
for k in sorted(out):
    print(f"{out[k][0]} {k} › {out[k][1]}")
