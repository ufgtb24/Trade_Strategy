"""流式提取 2026-10-20 以后主会话 jsonl 里用户亲手写的内容（不读子代理目录）。

输出 JSONL：每行一条，字段 session / ts / branch / kind / text / n_images / title / extra。
kind:
  typed            用户在输入框敲的（含粘贴、图片附带的文字）
  suggestion       接受了输入框里的建议补全
  queued           排队发送的消息
  command          斜杠命令及其参数（只保留带参数的或 skill 调用）
  ask_answer       AskUserQuestion 的作答（选项标签 + 是否选了推荐 + 自填文字）
  ask_reject       拒答选择题、要求先澄清
  tool_reject      拒绝工具调用并附了话
"""
import json, glob, os, re, sys, time

SRC = sys.argv[2] if len(sys.argv) > 2 else '/home/yu/.claude/projects/-home-yu-PycharmProjects-Trade-Strategy/'
OUT = sys.argv[1]
SINCE = time.mktime((2026, 10, 20, 0, 0, 0, 0, 0, -1))

files = sorted(f for f in glob.glob(SRC + '*.jsonl') if os.path.getmtime(f) > SINCE)
ask_ids = {}
rows = []
for fn in files:
    sid = os.path.basename(fn)[:8]
    title = ''
    srows = []
    with open(fn) as f:
        for line in f:
            if '"ai-title"' in line[:60] or '"type":"ai-title"' in line:
                try:
                    d = json.loads(line)
                    if d.get('type') == 'ai-title':
                        title = d.get('aiTitle') or d.get('title') or title
                except Exception:
                    pass
                continue
            if '"type":"user"' not in line and 'AskUserQuestion' not in line:
                continue
            d = json.loads(line)
            t = d.get('type')
            cont = (d.get('message') or {}).get('content')
            if t == 'assistant' and isinstance(cont, list):
                for x in cont:
                    if x.get('type') == 'tool_use' and x.get('name') == 'AskUserQuestion':
                        ask_ids[x['id']] = x.get('input', {})
                continue
            if t != 'user' or d.get('isSidechain'):
                continue
            ts = d.get('timestamp', '')
            br = d.get('gitBranch', '')
            o = d.get('origin') or {}
            ps = d.get('promptSource')
            base = dict(session=sid, ts=ts, branch=br)
            if d.get('isMeta') or d.get('isCompactSummary'):
                continue
            if o.get('kind') in ('peer', 'task-notification', 'auto-continuation'):
                continue
            if isinstance(cont, str):
                s = cont
                if s.startswith('<local-command') or s.startswith('<task-notification') or s.startswith('<teammate-message'):
                    continue
                m = re.search(r'<command-name>(.*?)</command-name>', s)
                if m:
                    a = re.search(r'<command-args>(.*?)</command-args>', s, re.S)
                    args = a.group(1).strip() if a else ''
                    name = m.group(1)
                    if name in ('/model', '/plugin', '/clear', '/output-style', '/reload-plugins', '/resume', '/exit', '/context', '/cost', '/status', '/config', '/mcp', '/permissions', '/hooks', '/ide', '/login', '/doctor', '/memory'):
                        continue
                    srows.append(dict(base, kind='command', text=(name + ' ' + args).strip(), n_images=0))
                    continue
                kind = {'typed': 'typed', 'suggestion_accepted': 'suggestion', 'queued': 'queued'}.get(ps, 'typed' if o.get('kind') == 'human' else None)
                if kind is None:
                    continue
                srows.append(dict(base, kind=kind, text=s, n_images=0))
                continue
            if not isinstance(cont, list):
                continue
            texts, nimg, tool_rows = [], 0, []
            for x in cont:
                ty = x.get('type')
                if ty == 'text':
                    tx = x.get('text', '')
                    if tx.startswith('[Request interrupted') or tx.startswith('[Image: source:'):
                        continue
                    texts.append(tx)
                elif ty == 'image':
                    nimg += 1
                elif ty == 'tool_result':
                    tid = x.get('tool_use_id')
                    s = x.get('content')
                    if isinstance(s, list):
                        s = ' '.join(y.get('text', '') for y in s if isinstance(y, dict))
                    s = s or ''
                    tur = d.get('toolUseResult')
                    if tid in ask_ids:
                        q = ask_ids[tid].get('questions', [])
                        if isinstance(tur, dict) and 'answers' in tur:
                            ans = tur.get('answers', {})
                            notes = tur.get('annotations') or {}
                            for qq in q:
                                qt = qq.get('question', '')
                                a = ans.get(qt, '')
                                labels = [op.get('label', '') for op in qq.get('options', [])]
                                rec = next((l for l in labels if '推荐' in l), labels[0] if labels else '')
                                chosen_known = any(a == l or a.startswith(l) for l in labels) or all(p.strip() in labels for p in a.split(','))
                                tool_rows.append(dict(base, kind='ask_answer', text=a, n_images=0, extra=dict(
                                    header=qq.get('header', ''), question=qt[:300], picked_recommended=(a == rec),
                                    custom=not chosen_known, n_options=len(labels), note=json.dumps(notes, ensure_ascii=False)[:500] if notes else '')))
                        else:
                            m = re.search(r'the user said:\s*(.*)', s, re.S)
                            tool_rows.append(dict(base, kind='ask_reject', text=(m.group(1)[:400] if m else s[:400]), n_images=0,
                                                  extra=dict(n_questions=len(q), headers=[qq.get('header', '') for qq in q])))
                    elif "doesn't want to proceed" in s:
                        m = re.search(r'the user said:\s*(.*)', s, re.S)
                        if m:
                            tool_rows.append(dict(base, kind='tool_reject', text=m.group(1).strip(), n_images=0))
            srows.extend(tool_rows)
            if texts or nimg:
                if o.get('kind') == 'human' or ps in ('typed', 'suggestion_accepted', 'queued'):
                    kind = {'suggestion_accepted': 'suggestion', 'queued': 'queued'}.get(ps, 'typed')
                    tx = '\n'.join(texts).strip()
                    if tx or nimg:
                        srows.append(dict(base, kind=kind, text=tx, n_images=nimg))
    for r in srows:
        r['title'] = title
    rows.extend(srows)

rows.sort(key=lambda r: (r['ts']))
with open(OUT, 'w') as f:
    for i, r in enumerate(rows):
        r['i'] = i
        f.write(json.dumps(r, ensure_ascii=False) + '\n')
print(len(rows), 'rows ->', OUT)
