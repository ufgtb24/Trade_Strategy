"""统计主会话里 cc 写给用户看的文字量（assistant 的 text 块 + AskUserQuestion 的题面与选项），按会话、按日（UTC+8）汇总。
分叉会话复制的历史按行 uuid 去重（同一条 message 会拆成多行，不能按 message.id 去重）。只读顶层 jsonl，不含子代理。"""
import json, glob, os, sys, time, collections
from datetime import datetime, timedelta
SRCS = sys.argv[1:] or ['/home/yu/.claude/projects/-home-yu-PycharmProjects-Trade-Strategy/']
SINCE = time.mktime((2026, 10, 20, 0, 0, 0, 0, 0, -1))
files = sorted(f for src in SRCS for f in glob.glob(src.rstrip('/') + '/*.jsonl') if os.path.getmtime(f) > SINCE)
seen = set()
by_sess = collections.defaultdict(lambda: collections.Counter())
by_day = collections.defaultdict(lambda: collections.Counter())
tools = collections.defaultdict(collections.Counter)
for fn in files:
    sid = os.path.basename(fn)[:8]
    with open(fn) as f:
        for line in f:
            if '"type":"assistant"' not in line:
                continue
            d = json.loads(line)
            if d.get('type') != 'assistant' or d.get('isSidechain'):
                continue
            m = d.get('message') or {}
            mid = d.get('uuid')
            ts = d.get('timestamp', '')
            day = (datetime.fromisoformat(ts.replace('Z', '+00:00')) + timedelta(hours=8)).strftime('%m-%d') if ts else '?'
            for k, x in enumerate(m.get('content') or []):
                key = (mid, k, x.get('type'))
                if key in seen:
                    continue
                seen.add(key)
                if x.get('type') == 'text':
                    n = len(x.get('text', ''))
                    by_sess[sid]['text_chars'] += n; by_sess[sid]['text_msgs'] += 1
                    by_day[day]['text_chars'] += n; by_day[day]['text_msgs'] += 1
                elif x.get('type') == 'tool_use':
                    name = x.get('name')
                    tools[sid][name] += 1
                    by_day[day]['tool_calls'] += 1
                    if name == 'AskUserQuestion':
                        n = len(json.dumps(x.get('input', {}), ensure_ascii=False))
                        nq = len(x.get('input', {}).get('questions', []))
                        by_sess[sid]['ask_chars'] += n; by_sess[sid]['ask_q'] += nq
                        by_day[day]['ask_chars'] += n; by_day[day]['ask_q'] += nq
                    if name == 'Agent':
                        by_sess[sid]['agents'] += 1; by_day[day]['agents'] += 1
print('== by session')
for s, c in by_sess.items():
    print(s, dict(c), 'top tools:', tools[s].most_common(6))
print('== by day (UTC+8)')
for dname in sorted(by_day):
    print(dname, dict(by_day[dname]))
tot = collections.Counter()
for c in by_sess.values(): tot.update(c)
print('TOTAL', dict(tot))
