"""每一条用户亲手输入之后、下一条用户输入之前，cc 在主会话写了多少字（含 AskUserQuestion 题面）。按会话分别算，再汇总分布。"""
import sys, json, glob, os, time, statistics
SRCS = sys.argv[1:] or ['/home/yu/.claude/projects/-home-yu-PycharmProjects-Trade-Strategy/']
SINCE = time.mktime((2026, 10, 20, 0, 0, 0, 0, 0, -1))
files = sorted(f for src in SRCS for f in glob.glob(src.rstrip('/') + '/*.jsonl') if os.path.getmtime(f) > SINCE)
seen = set(); per = []
for fn in files:
    cur = None
    with open(fn) as f:
        for line in f:
            if '"type":"user"' not in line and '"type":"assistant"' not in line:
                continue
            d = json.loads(line)
            if d.get('isSidechain') or d.get('timestamp', '') < '2026-10-20T09:38':
                continue
            t = d.get('type'); c = (d.get('message') or {}).get('content')
            if t == 'user' and ((d.get('origin') or {}).get('kind') == 'human' or d.get('promptSource') in ('typed', 'suggestion_accepted', 'queued')):
                if cur is not None: per.append(cur)
                cur = 0
            elif t == 'assistant' and cur is not None:
                mid = d.get('uuid')
                for k, x in enumerate(c or []):
                    if (mid, k) in seen: continue
                    seen.add((mid, k))
                    if x.get('type') == 'text': cur += len(x['text'])
                    elif x.get('type') == 'tool_use' and x.get('name') == 'AskUserQuestion':
                        cur += len(json.dumps(x.get('input', {}), ensure_ascii=False))
    if cur is not None: per.append(cur)
per = [p for p in per if p > 0]
per.sort()
q = lambda p: per[int(p * (len(per) - 1))]
print('turns', len(per), 'total', sum(per), 'median', q(.5), 'p75', q(.75), 'p90', q(.9), 'max', per[-1])
