"""把 cc 写在主会话里的文字按「被什么触发」分开：用户亲手输入 vs 队友/后台任务消息 vs 工具结果后的中途文字。
按行 uuid 去重分叉会话复制的历史。只算 2026-10-20 以后修改过的顶层 jsonl。"""
import sys, json, glob, os, time, collections
SRCS = sys.argv[1:] or ['/home/yu/.claude/projects/-home-yu-PycharmProjects-Trade-Strategy/']
SINCE = time.mktime((2026, 10, 20, 0, 0, 0, 0, 0, -1))
files = sorted(f for src in SRCS for f in glob.glob(src.rstrip('/') + '/*.jsonl') if os.path.getmtime(f) > SINCE)
seen = set(); agg = collections.Counter(); cnt = collections.Counter()
for fn in files:
    trig = 'other'
    with open(fn) as f:
        for line in f:
            if '"type":"user"' not in line and '"type":"assistant"' not in line:
                continue
            d = json.loads(line)
            if d.get('isSidechain') or d.get('timestamp', '') < '2026-10-20T09:38':
                continue
            t = d.get('type'); c = (d.get('message') or {}).get('content')
            if t == 'user':
                o = (d.get('origin') or {}).get('kind')
                if isinstance(c, list) and any(x.get('type') == 'tool_result' for x in c):
                    trig = 'after_tool'
                elif o in ('peer', 'task-notification') or (isinstance(c, str) and ('<teammate-message' in c or '<task-notification' in c or 'Another Claude session' in c)):
                    trig = 'teammate_or_task'
                elif o == 'human' or d.get('promptSource'):
                    trig = 'human'
                elif d.get('isMeta'):
                    pass
                else:
                    trig = 'other'
            elif t == 'assistant':
                mid = d.get('uuid')
                for k, x in enumerate(c or []):
                    if x.get('type') != 'text' or (mid, k) in seen:
                        continue
                    seen.add((mid, k))
                    agg[trig] += len(x['text']); cnt[trig] += 1
print({k: (cnt[k], agg[k]) for k in agg})
