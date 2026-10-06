#!/usr/bin/env python3
"""Read-only local implementation ticket board (Python standard library only).

    python3 scripts/implementation_board.py .scratch/<effort>-implementation --serve
    python3 scripts/implementation_board.py .scratch/<effort>-implementation -o board.html

Only issues/*.md supplies ticket state; questions/*.md supplies the user questions that explain
why tickets wait on a decision. No map or manifest is required.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import re
from urllib.parse import unquote, urlsplit

ROLES = ('needs-triage', 'needs-info', 'ready-for-agent', 'ready-for-human', 'wontfix')
PROGRESS = ('not-started', 'in-progress', 'done')
READY = ('ready-for-agent', 'ready-for-human')
GROUPS = ('active', 'pending', 'needs-triage', 'needs-info', 'done', 'wontfix', 'invalid')
FIELD = re.compile(r'^(Status|Progress|Blocked by|Claimed|Assignee|Completed):\s*(.*)$', re.I)
QUESTION_FIELD = re.compile(r'^(Status|Blocks|Raised|Recommended):\s*(.*)$', re.I)
QUESTION_STATUSES = ('drafting', 'open', 'applying', 'resolved', 'withdrawn')
UNRESOLVED = ('drafting', 'open', 'applying')


def outside_examples(raw):
    """Keep line boundaries while excluding fenced and quoted examples."""
    fence = None
    result = []
    for line in raw.splitlines():
        marker = re.match(r'^\s{0,3}(`{3,}|~{3,})', line)
        if marker:
            value = marker[1]
            if fence is None:
                fence = value
            elif value[0] == fence[0] and len(value) >= len(fence):
                fence = None
            result.append('')
        elif fence or line.lstrip().startswith('>') or line.startswith(('    ', '\t')):
            result.append('')
        else:
            result.append(line)
    return '\n'.join(result)


def section(raw, names):
    for match in re.finditer(r'^#{2,6}\s+(.+)\n', raw, re.M):
        if match[1].strip().lower() in names:
            rest = raw[match.end():]
            return re.split(r'^#{1,6}\s+', rest, maxsplit=1, flags=re.M)[0].strip()
    return ''


def parse_ticket(path, raw, aliases):
    clean = outside_examples(raw)
    preamble = re.split(r'^##\s+', clean, maxsplit=1, flags=re.M)[0]
    fields, errors, warnings = {}, [], []
    for line in preamble.splitlines():
        match = FIELD.match(line.replace('**', '').strip())
        if match:
            name, value = match[1].lower(), match[2].strip()
            if name in fields:
                errors.append('重复字段：' + name)
            else:
                fields[name] = value
    heading = re.search(r'^#\s+(.+)$', clean, re.M)
    title = heading[1].strip() if heading else path.name
    number = re.match(r'^(\d+)-.+\.md$', path.name)
    num = str(int(number[1])).zfill(2) if number else ''
    if not num:
        errors.append('文件名须为编号-名称.md')
    title_number = re.match(r'^(\d+)\s*[:：]\s*(.*)$', title)
    if title_number:
        if str(int(title_number[1])).zfill(2) != num:
            errors.append('标题编号与文件编号不一致')
        title = title_number[2]
    if not heading:
        errors.append('缺少票标题')
    status = fields.get('status', '')
    role = aliases.get(status, '')
    if not role:
        errors.append('缺少或无法识别分流标签：' + status)
    if 'blocked by' not in fields or not fields['blocked by']:
        errors.append('缺少Blocked by；无前置请写none')
    completion = section(clean, {'completion', '完成记录', '完成说明', '完成结果'})
    claimed = fields.get('claimed', '') or fields.get('assignee', '')
    progress = fields.get('progress', 'not-started')
    if progress not in PROGRESS:
        errors.append('无法识别执行阶段：' + progress)
    if 'progress' not in fields and (claimed or completion or fields.get('completed')):
        errors.append('有认领/完成记录但缺少Progress')
    if progress != 'done' and (completion or fields.get('completed')):
        errors.append('完成记录与未完成阶段冲突')
    if progress == 'done' and (role not in READY or not completion):
        errors.append('完成说明缺失或与分流标签冲突')
    if progress == 'not-started' and claimed:
        errors.append('认领记录与未开始阶段冲突')
    if progress == 'in-progress' and not claimed:
        warnings.append('进行中但未记录认领者')
    group = ('wontfix' if role == 'wontfix' else role if role in ('needs-info', 'needs-triage')
             else {'not-started': 'pending', 'in-progress': 'active', 'done': 'done'}.get(progress, 'invalid')
             if role in READY else 'invalid')
    purpose = section(clean, {'purpose', '产品贡献', '目的'})
    direction = section(clean, {'direction', 'inherited direction', '继承方向', '已批准方向'})
    return dict(key=path.name, num=num, title=title, status=status, role=role, progress=progress,
                claimed=claimed, group=group, blocked_by=fields.get('blocked by', ''), raw=raw,
                purpose=purpose, direction=direction, errors=errors, warnings=warnings,
                deps=[], dependents=[], waiting=[], frontier='', complete=False, questions=[])


def parse_question(path, raw):
    """A user question: why some tickets wait on the user, which routes exist, what is recommended."""
    clean = outside_examples(raw)
    preamble = re.split(r'^##\s+', clean, maxsplit=1, flags=re.M)[0]
    fields, errors, warnings = {}, [], []
    for line in preamble.splitlines():
        match = QUESTION_FIELD.match(line.replace('**', '').strip())
        if match:
            name, value = match[1].lower(), match[2].strip()
            if name in fields:
                errors.append('重复字段：' + name)
            else:
                fields[name] = value
    heading = re.search(r'^#\s+(.+)$', clean, re.M)
    title = heading[1].strip() if heading else path.name
    number = re.match(r'^Q(\d+)-.+\.md$', path.name)
    num = 'Q' + str(int(number[1])).zfill(2) if number else ''
    if not num:
        errors.append('文件名须为Q编号-名称.md')
    title_number = re.match(r'^Q?(\d+)\s*[:：]\s*(.*)$', title)
    if title_number:
        if 'Q' + str(int(title_number[1])).zfill(2) != num:
            errors.append('标题编号与文件编号不一致')
        title = title_number[2]
    if not heading:
        errors.append('缺少问题标题')
    status = fields.get('status', '').lower()
    if status not in QUESTION_STATUSES:
        errors.append('无法识别问题状态：' + fields.get('status', ''))
    if not fields.get('blocks'):
        errors.append('缺少Blocks；不挡票请写none')
    recommended = fields.get('recommended', '')
    routes = [re.sub(r'\s*[（(]推荐[)）]\s*$', '', m[1]).strip()
              for m in re.finditer(r'^###\s+[A-Za-z]\s*[.、．]\s*(.+?)\s*$', clean, re.M)]
    if status == 'open' and not recommended:
        warnings.append('待答问题缺少Recommended')
    elif recommended and routes and recommended not in routes:
        warnings.append('Recommended不等于任何路线短名：' + recommended)
    return dict(key=path.name, num=num, title=title, status=status, blocks_text=fields.get('blocks', ''),
                blocks=[], raised=fields.get('raised', ''), recommended=recommended, routes=routes, raw=raw,
                errors=errors, warnings=warnings, unresolved=False)


def label_file(effort):
    for parent in (effort, *effort.parents):
        if (parent / '.git').exists():
            return parent / 'docs/agents/triage-labels.md'
    return None


def read_aliases(path):
    if path is None or not path.exists():
        return {r: r for r in ROLES}, [], ''
    raw = path.read_text(encoding='utf-8')
    roles, aliases, errors = {}, {}, []
    for line in raw.splitlines():
        cells = [c.strip().strip('`').strip() for c in line.strip().strip('|').split('|')]
        if len(cells) < 2 or cells[0] not in ROLES:
            continue
        role, name = cells[:2]
        if role in roles or not name or name in aliases:
            errors.append('标签映射重复、空值或歧义：' + role)
        roles[role] = name
        aliases[name] = role
    if set(roles) != set(ROLES):
        errors.append('标签映射未完整声明五种官方角色')
    return aliases, errors, raw


def listing(effort):
    if not effort.is_dir():
        raise ValueError('实施目录不存在')
    folder = effort / 'issues'
    if not folder.exists():
        return []
    if not folder.is_dir():
        raise ValueError('issues不是目录')
    return sorted(folder.glob('*.md'))


def question_listing(effort):
    """questions/*.md; writers use a hidden temporary name and rename, so half-written files are never read."""
    folder = effort / 'questions'
    if not folder.exists():
        return []
    if not folder.is_dir():
        raise ValueError('questions不是目录')
    return sorted(p for p in folder.glob('*.md') if not p.name.startswith('.'))


def stamp(paths):
    return [(str(p), p.stat().st_mtime_ns, p.stat().st_size, p.stat().st_ino) for p in paths]


def resolve_reference(text, by_num, by_title, by_file):
    text = text.strip().strip('`')
    linked = re.fullmatch(r'\[.*?\]\(([^)]+)\)', text)
    if linked:
        target = unquote(linked[1].split('#')[0])
        # Dependency links name siblings, not other decision stores.
        if '/' in target.removeprefix('./') or re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:', target):
            return []
        return by_file.get(target.removeprefix('./'), [])
    if re.fullmatch(r'#?\d+', text):
        return by_num.get(str(int(text.lstrip('#'))).zfill(2), [])
    if text in by_title:
        return by_title[text]
    prefixed = re.match(r'^#?(\d+)(?:\s*[:：]\s*|\s+)', text)
    if prefixed:
        candidates = by_num.get(str(int(prefixed[1])).zfill(2), [])
        suffix = text[prefixed.end():].strip()
        return [t for t in candidates if t['title'] == suffix]
    return []


def ticket_index(tickets):
    by_num, by_title, by_file = defaultdict(list), defaultdict(list), defaultdict(list)
    for t in tickets:
        by_num[t['num']].append(t)
        by_title[t['title']].append(t)
        by_file[t['key']].append(t)
    return by_num, by_title, by_file


def derive(tickets):
    by_num, by_title, by_file = ticket_index(tickets)
    by_key = {t['key']: t for t in tickets}
    for group in by_num.values():
        if len(group) > 1:
            for t in group:
                t['errors'].append('编号重复，不能唯一引用')
    for t in tickets:
        text = t['blocked_by']
        if re.fullmatch(r'none(?:\s*\(can start immediately\))?', text, re.I):
            continue
        refs = [text] if text in by_title else re.split(r'[,，;；]\s*', text)
        for ref in filter(None, refs):
            matches = resolve_reference(ref, by_num, by_title, by_file)
            if len(matches) != 1:
                t['errors'].append('前置不存在或有歧义：' + ref)
                continue
            p = matches[0]
            if p['key'] not in t['deps']:
                t['deps'].append(p['key'])
                p['dependents'].append(t['key'])
    # Iterative DFS detects cycles without assuming ticket count fits recursion depth.
    color, stack, active = {}, [], {}
    for start in by_key:
        if color.get(start):
            continue
        todo = [(start, False)]
        while todo:
            key, leave = todo.pop()
            if leave:
                color[key] = 2
                active.pop(key, None)
                stack.pop()
                continue
            if color.get(key) == 1:
                for cyclic in stack[active[key]:]:
                    if '循环依赖' not in by_key[cyclic]['errors']:
                        by_key[cyclic]['errors'].append('循环依赖')
                continue
            if color.get(key) == 2:
                continue
            color[key] = 1
            active[key] = len(stack)
            stack.append(key)
            todo.append((key, True))
            todo.extend((d, False) for d in reversed(by_key[key]['deps']))
    # Resolve valid completion from leaves upwards; invalid/cyclic tickets cannot unlock others.
    remaining = {t['key']: len(t['deps']) for t in tickets}
    queue = [key for key, n in remaining.items() if n == 0]
    for key in queue:
        t = by_key[key]
        t['complete'] = t['progress'] == 'done' and not t['errors'] and all(by_key[d]['complete'] for d in t['deps'])
        for successor in t['dependents']:
            remaining[successor] -= 1
            if remaining[successor] == 0:
                queue.append(successor)
    for t in tickets:
        t['waiting'] = [d for d in t['deps'] if not by_key[d]['complete']]
        if t['waiting'] and t['progress'] in ('in-progress', 'done') and t['role'] in READY:
            t['warnings'].append('已开工/声明完成，但前置尚未有效完成')
        if t['role'] in READY and t['progress'] == 'not-started' and not t['waiting'] and not t['errors'] and not t['claimed']:
            t['frontier'] = 'agent' if t['role'] == 'ready-for-agent' else 'human'


def link_questions(tickets, questions):
    """Resolve Blocks, attach unresolved questions to tickets, and cross-check against ticket state.

    needs-info on the ticket is what blocks it; the question explains why. A question that cannot be
    parsed counts as unresolved (fail closed), and a not-started ticket still listed by an unresolved
    question is kept off the frontier with a warning."""
    by_num, _, _ = ticket_index(tickets)
    by_key = {t['key']: t for t in tickets}
    seen = defaultdict(list)
    for q in questions:
        if q['num']:
            seen[q['num']].append(q)
        text = q['blocks_text']
        if text and not re.fullmatch(r'none', text, re.I):
            for token in filter(None, re.split(r'[,，;；、\s]+', text)):
                token = token.lstrip('#')
                matches = by_num.get(str(int(token)).zfill(2), []) if token.isdigit() else []
                if len(matches) != 1:
                    q['errors'].append('Blocks里的票不存在或有歧义：' + token)
                elif matches[0]['key'] not in q['blocks']:
                    q['blocks'].append(matches[0]['key'])
    for group in seen.values():
        if len(group) > 1:
            for q in group:
                q['errors'].append('问题编号重复')
    for q in questions:
        q['unresolved'] = q['status'] in UNRESOLVED or bool(q['errors'])
        if q['unresolved']:
            for key in q['blocks']:
                by_key[key]['questions'].append(q['key'])
    names = {q['key']: q['num'] or q['key'] for q in questions}
    for t in tickets:
        if t['questions'] and t['role'] in READY and t['progress'] == 'not-started':
            t['warnings'].append('列入未结问题却仍可开工：' + '、'.join(names[k] for k in t['questions']))
            t['frontier'] = ''
        closed = [q['num'] for q in questions if not q['unresolved'] and t['key'] in q['blocks']]
        if t['role'] == 'needs-info' and closed and not t['questions']:
            t['warnings'].append('问题已结，仍needs-info：' + '、'.join(closed))


def load(effort, labels_path=None):
    effort = Path(effort).resolve()
    mapping = Path(labels_path).resolve() if labels_path is not None else label_file(effort)
    paths = listing(effort)
    question_paths = question_listing(effort)
    sources = paths + question_paths + ([mapping] if mapping and mapping.exists() else [])
    before = stamp(sources)
    aliases, errors, labels_raw = read_aliases(mapping)
    tickets, raw_files = [], []
    for path in paths:
        data = path.read_bytes()
        raw = data.decode('utf-8', errors='replace')
        ticket = parse_ticket(path, raw, aliases)
        try:
            data.decode('utf-8')
        except UnicodeDecodeError:
            ticket['errors'].append('文件不是有效UTF-8')
        if errors:
            ticket['errors'].append('项目标签映射异常，暂不判定执行资格')
        tickets.append(ticket)
        raw_files.append((path.name, hashlib.sha256(data).hexdigest()))
    questions = []
    for path in question_paths:
        data = path.read_bytes()
        question = parse_question(path, data.decode('utf-8', errors='replace'))
        try:
            data.decode('utf-8')
        except UnicodeDecodeError:
            question['errors'].append('文件不是有效UTF-8')
        questions.append(question)
        raw_files.append(('questions/' + path.name, hashlib.sha256(data).hexdigest()))
    after_sources = listing(effort) + question_listing(effort) + ([mapping] if mapping and mapping.exists() else [])
    if before != stamp(after_sources):
        raise OSError('读取期间文件发生变化，等待下一次完整快照')
    derive(tickets)
    link_questions(tickets, questions)
    revision = hashlib.sha256(json.dumps([raw_files, str(mapping), labels_raw], ensure_ascii=False).encode()).hexdigest()
    return dict(title=effort.name, directory=str(effort), tickets=tickets, questions=questions, errors=errors,
                revision=revision, generated_at=datetime.now(timezone.utc).isoformat(),
                counts={**{g: sum(t['group'] == g for t in tickets) for g in GROUPS},
                        'total': len(tickets), 'complete': sum(t['complete'] for t in tickets),
                        'frontier': sum(bool(t['frontier']) for t in tickets),
                        'anomalies': sum(bool(t['errors'] or t['warnings']) for t in tickets),
                        'questions_open': sum(q['status'] == 'open' and not q['errors'] for q in questions),
                        'questions_unresolved': sum(q['unresolved'] for q in questions)})


# Markdown is intentionally limited: raw HTML never executes and local links never read files.
def inline(text, path, ticket_paths):
    import html
    parts = re.split(r'(`[^`]+`|\[[^\]]+\]\([^)]+\)|\*\*[^*]+\*\*)', text)
    out = []
    for part in parts:
        link = re.fullmatch(r'\[([^\]]+)\]\(([^)]+)\)', part)
        if part.startswith('`') and part.endswith('`'):
            out.append('<code>' + html.escape(part[1:-1]) + '</code>')
        elif part.startswith('**') and part.endswith('**'):
            out.append('<strong>' + html.escape(part[2:-2]) + '</strong>')
        elif link:
            label, url = link.groups()
            try:
                scheme = urlsplit(url).scheme
            except ValueError:
                out.append(html.escape(part))
                continue
            if scheme in ('http', 'https'):
                out.append('<a target="_blank" rel="noopener noreferrer" href="' + html.escape(url, quote=True) + '">' + html.escape(label) + '</a>')
            else:
                target = (path.parent / unquote(url.split('#')[0])).resolve()
                if target in ticket_paths:
                    key = ticket_paths[target]
                    out.append('<a href="#" data-select="' + html.escape(key, quote=True) + '">' + html.escape(label) + '</a>')
                else:
                    # Copy-only reference: exposing a link is not permission to serve its contents.
                    display = str(target) if not scheme else url
                    out.append('<button class="ref" data-copy="' + html.escape(display, quote=True) + '" title="复制路径或引用">' + html.escape(label) + '</button>')
        else:
            out.append(html.escape(part))
    return ''.join(out)


def markdown(raw, path, ticket_paths):
    import html
    lines, out, i = raw.splitlines(), [], 0
    occurrences = Counter()
    def emit(body, source):
        token = hashlib.sha256(source.encode()).hexdigest()[:16]
        occurrences[token] += 1
        out.append(f'<div class="md-block" data-anchor="{token}-{occurrences[token]}">{body}</div>')
    fmt = lambda text: inline(text, path, ticket_paths)
    while i < len(lines):
        text = lines[i].strip()
        if not text:
            i += 1
            continue
        start = i
        fence = re.match(r'^(`{3,}|~{3,})(.*)$', text)
        if fence:
            i += 1
            code = []
            while i < len(lines) and not re.fullmatch(re.escape(fence[1][0]) + '{' + str(len(fence[1])) + r',}\s*', lines[i].strip()):
                code.append(lines[i]); i += 1
            if i < len(lines):
                i += 1
            body = '<pre><code>' + html.escape('\n'.join(code)) + '</code></pre>'
        elif text.startswith('|') and i + 1 < len(lines) and re.fullmatch(r'\|[\s:|\-]+\|', lines[i + 1].strip()):
            cells = lambda line: [fmt(c.strip()) for c in line.strip().strip('|').split('|')]
            body = '<div class="table-scroll"><table><thead><tr>' + ''.join('<th>' + c + '</th>' for c in cells(lines[i])) + '</tr></thead><tbody>'
            i += 2
            while i < len(lines) and lines[i].strip().startswith('|'):
                body += '<tr>' + ''.join('<td>' + c + '</td>' for c in cells(lines[i])) + '</tr>'
                i += 1
            body += '</tbody></table></div>'
        else:
            heading = re.match(r'^(#{1,6})\s+(.+)', text)
            check = re.match(r'^[-*]\s+\[([ xX])\]\s*(.*)', text)
            item = re.match(r'^(?:[-*]|\d+\.)\s+(.*)', text)
            if heading:
                level = min(len(heading[1]) + 1, 6)
                body = f'<h{level}>' + fmt(heading[2]) + f'</h{level}>'
            elif check:
                body = '<p class="check"><input type="checkbox" disabled' + (' checked' if check[1].lower() == 'x' else '') + ' aria-label="只读验收项"> ' + fmt(check[2]) + '</p>'
            elif item:
                body = '<p class="item">• ' + fmt(item[1]) + '</p>'
            elif text.startswith('>'):
                body = '<blockquote>' + fmt(text.lstrip('> ')) + '</blockquote>'
            else:
                body = '<p>' + fmt(text) + '</p>'
            i += 1
        emit(body, '\n'.join(lines[start:i]))
    return '\n'.join(out)


def presentation(snapshot):
    data = dict(snapshot)
    base = Path(snapshot['directory'])
    # Map every linkable file to its full selection key so tickets and questions link to each other.
    paths = {(base / 'issues' / t['key']).resolve(): 'ticket:' + t['key'] for t in snapshot['tickets']}
    paths.update({(base / 'questions' / q['key']).resolve(): 'question:' + q['key'] for q in snapshot.get('questions', [])})
    data['tickets'] = [dict(t, body_html=markdown(t['raw'], base / 'issues' / t['key'], paths)) for t in snapshot['tickets']]
    data['questions'] = [dict(q, body_html=markdown(q['raw'], base / 'questions' / q['key'], paths)) for q in snapshot.get('questions', [])]
    return data


CSS = r'''
:root{--bg:#faf9f5;--paper:#fff;--ink:#292c2b;--muted:#72776e;--line:#e4e3db;--red:#b54443;--blue:#337ab8;--yellow:#fff1a0}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.65 system-ui,-apple-system,"Noto Sans CJK SC",sans-serif}
a{color:var(--blue)}button,input{font:inherit}button{cursor:pointer}button:focus-visible,a:focus-visible,summary:focus-visible{outline:2px solid var(--blue);outline-offset:2px}
.wrap{max-width:1500px;margin:auto;padding:26px 32px}.eyebrow{font-size:12px;color:var(--muted);letter-spacing:.08em}h1{font-size:28px;margin:3px 0 8px}h2{font-size:21px}h3{font-size:18px}.summary{color:var(--muted);margin-bottom:14px}
.toolbar{display:flex;gap:15px;align-items:center;flex-wrap:wrap;margin-bottom:18px}.toolbar input[type=search]{padding:7px 12px;border:1px solid var(--line);border-radius:6px;min-width:260px;background:white}.toolbar label{font-size:13px}.refresh{font-size:12px;color:var(--muted)}.error-banner{border:1px solid #d99;background:#fff0ec;padding:10px 16px;border-radius:6px;margin:12px 0}.error-banner[hidden]{display:none}.notice{color:#8d5708;background:#fff4d4;padding:8px 12px;border-radius:5px}
.cols{display:grid;grid-template-columns:320px minmax(0,1fr);gap:28px;align-items:start}.tree{position:sticky;top:12px;max-height:calc(100vh - 24px);overflow:auto;border-right:1px solid var(--line);padding-right:16px}.tree details{margin:6px 0}.tree summary{cursor:pointer;font-weight:600;padding:7px 5px}.tree summary span{float:right;font-size:12px;color:var(--muted)}.tree details details{margin-left:12px}.row{position:relative;padding:8px 10px 8px 16px;margin:3px 0;border-radius:5px;cursor:pointer;overflow-wrap:anywhere}.row:hover{background:#efeee6}.row.frontier{background:var(--yellow)}.row.frontier:hover{background:#ffe66c}.row.selected{background:#e8e3cb;box-shadow:inset 0 0 0 1px #b7ad83}.row.rel-before::before,.row.rel-after::before{content:"";position:absolute;left:4px;top:4px;bottom:4px;width:8px;border-radius:3px}.row.rel-before::before{background:var(--red)}.row.rel-after::before{background:var(--blue)}.row.resolved::before{opacity:.5}.row.selected::before{display:none}.row a.title{color:inherit;text-decoration:none}.num{font-size:12px;color:#666c61;font-weight:650;margin-right:6px}.subrow{margin-top:3px;font-size:11px;color:var(--muted)}
.badge{display:inline-block;border:0;border-radius:4px;padding:0 5px;margin:1px;color:white!important;text-decoration:none;font-size:11px;font-weight:650;line-height:20px}.badge.r{background:var(--red)}.badge.b{background:var(--blue)}.badge.done.r{background:color-mix(in srgb,var(--red) 50%,transparent)}.badge.done.b{background:color-mix(in srgb,var(--blue) 50%,transparent)}.tag{display:inline-block;font-size:11px;padding:1px 7px;border-radius:20px;border:1px solid var(--line);color:#62665e;margin:2px 4px 2px 0;background:#f7f7f0}.tag.warn{color:#a4432a;border-color:#dcb8a9}.tag.good{background:#fff5be;border-color:#dbcd79}.link-button{border:0;background:none;color:var(--blue);padding:0;text-align:left}.overview-link{display:block;padding:8px;font-weight:600}.count-grid{display:flex;flex-wrap:wrap;gap:12px;margin:20px 0}.count-grid button{background:white;border:1px solid var(--line);border-radius:7px;padding:12px 18px;min-width:130px;text-align:left}.count-grid strong{font-size:25px;display:block}.index{width:100%;border-collapse:collapse}.index th,.index td{padding:10px 8px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}.index th{font-size:12px;color:var(--muted)}.index tr[data-select]{cursor:pointer}.index tr[data-select]:hover{background:#f0eee4}.index tr.frontier{background:#fff8d5}.ticket-head{border-bottom:1px solid var(--line);padding-bottom:18px;margin-bottom:20px}.ticket-head h2{margin:0 0 12px}.brief{padding:10px 14px;background:#f0f0e9;border-radius:6px;margin-top:9px}.brief strong{display:block;font-size:12px;color:var(--muted)}.warnings{color:#a13b2e;margin:10px 0}.metadata{font-size:12px;color:var(--muted);overflow-wrap:anywhere}#main{min-width:0}.body h2,.body h3,.body h4{margin:22px 0 8px}.body p{margin:6px 0;overflow-wrap:anywhere}.body pre{background:#efefe9;border:1px solid var(--line);padding:14px;overflow:auto;border-radius:6px}.body code{font:12px/1.6 ui-monospace,monospace}.body table{border-collapse:collapse;min-width:100%;font-size:13px}.body td,.body th{border:1px solid var(--line);padding:8px;text-align:left;vertical-align:top}.table-scroll{overflow:auto}.body blockquote{border-left:3px solid #bcbeb1;padding-left:14px;color:var(--muted);margin-left:0}.ref{border:0;border-bottom:1px dotted #929b8a;color:#526c52;background:none;padding:0;text-align:left}.check input{accent-color:#817b4e}.item{padding-left:12px}.empty{padding:32px;color:var(--muted)}.qbanner{border:1px solid #e0b96a;background:#fff6dc;padding:12px 16px;border-radius:7px;margin:14px 0}.qbanner strong{display:block;margin-bottom:6px}.row.q-open{background:#fff1d6}.row.q-open:hover{background:#ffe7b8}.tag.qtag{background:#fff1d6;border-color:#e0b96a;color:#8d5708;text-decoration:none}.warning-link{color:#a4432a}.footer{font-size:12px;color:var(--muted);margin:30px 0}.message{position:fixed;bottom:18px;right:20px;background:#34392f;color:white;padding:8px 14px;border-radius:6px;max-width:70vw;overflow-wrap:anywhere;z-index:5}[hidden]{display:none!important}
@media(max-width:850px){.wrap{padding:18px}.cols{grid-template-columns:240px minmax(0,1fr);gap:14px}.index th:nth-child(4),.index td:nth-child(4){display:none}}@media(max-width:580px){.cols{display:block}.tree{position:static;max-height:260px;border-bottom:1px solid var(--line);margin-bottom:20px}.toolbar input[type=search]{min-width:180px;width:100%}}
'''

JS = r'''
(()=>{'use strict';
const cfg=JSON.parse(document.getElementById('bootstrap').textContent);
const $=s=>document.querySelector(s), esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const labels={active:'进行中',pending:'未开始','needs-triage':'待评估','needs-info':'待补充信息',done:'已完成',wontfix:'不处理',invalid:'无法分类',overview:'总览',unfinished:'未完成',clarify:'待澄清',anomalies:'数据异常',search:'搜索结果',questions:'待决问题',closedq:'已结问题'};
const qstates={drafting:'简报撰写中',open:'待答',applying:'落实中',resolved:'已结',withdrawn:'已撤回'};
const stages={'not-started':'未开始','in-progress':'进行中',done:'已完成'};
const roles={'needs-triage':'待评估','needs-info':'待补充信息','ready-for-agent':'Agent执行','ready-for-human':'人类执行',wontfix:'不处理'};
const key='implementation-board:'+cfg.directory;
let preferences={open:{},before:true,after:true};
try{const p=JSON.parse(localStorage.getItem(key));if(p&&typeof p==='object'){if(p.open&&typeof p.open==='object'&&!Array.isArray(p.open))for(const [k,v]of Object.entries(p.open))if(typeof v==='boolean')preferences.open[k]=v;if(typeof p.before==='boolean')preferences.before=p.before;if(typeof p.after==='boolean')preferences.after=p.after;}}catch(_){}
let data=null,selected=readHash(),query='',deleted='',notice='',timer=null;
function readHash(){try{return decodeURIComponent(location.hash.slice(1))||'overview';}catch(_){return 'overview';}}
function save(){try{localStorage.setItem(key,JSON.stringify(preferences));}catch(_){}}
function byKey(k){return data?.tickets.find(t=>t.key===k);}
function qByKey(k){return (data?.questions||[]).find(q=>q.key===k);}
function qnum(k){const q=qByKey(k);return q?q.num:k;}
function qlink(k){return selectLink('question:'+k,'待决 '+qnum(k),'tag qtag');}
function current(){return selected.startsWith('ticket:')?byKey(selected.slice(7)):null;}
function target(k){return 'ticket:'+k;}
function selectLink(k,text,cls=''){return `<a class="${cls}" href="#${encodeURIComponent(k)}" data-select="${esc(k)}">${esc(text)}</a>`;}
function badge(k,color){const t=byKey(k);return t?selectLink(target(k),t.num||'?',`badge ${color}${t.complete?' done':''}`):'';}
function deps(t){return t.deps.map(k=>badge(k,'r')).join('');}
function flags(t){return `<span class="tag">${esc(roles[t.role]||t.status||'未知标签')}</span>`+(t.role==='wontfix'?'':`<span class="tag">${esc(stages[t.progress]||t.progress)}</span>`)+(t.frontier?'<span class="tag good">可开工</span>':'')+(t.errors.length||t.warnings.length?'<span class="tag warn">⚠ 数据提示</span>':'')+(t.questions||[]).map(qlink).join('');}
function relation(t){const c=current();return `${c&&preferences.before&&c.deps.includes(t.key)?' rel-before':''}${c&&preferences.after&&c.dependents.includes(t.key)?' rel-after':''}`;}
function row(t){return `<div class="row${t.frontier?' frontier':''}${t.complete?' resolved':''}${selected===target(t.key)?' selected':''}${relation(t)}" data-select="${esc(target(t.key))}" data-ticket="${esc(t.key)}"><span class="num">${esc(t.num||'?')}</span>${selectLink(target(t.key),t.title,'title')}<div class="subrow">${(t.questions||[]).length?'待决 '+t.questions.map(qnum).join('、')+' · ':''}${t.role==='ready-for-human'?'人类执行 · ':''}${t.claimed?esc(t.claimed)+' · ':''}${t.errors.length||t.warnings.length?'⚠ ':''}${deps(t)} ${t.dependents.map(k=>badge(k,'b')).join('')}</div></div>`;}
function sorted(ts){return [...ts].sort((a,b)=>Number(Boolean(b.frontier))-Number(Boolean(a.frontier))||a.num.localeCompare(b.num,undefined,{numeric:true})||a.key.localeCompare(b.key));}
function groupRows(g){if(!data)return [];if(g==='unfinished')return data.tickets.filter(t=>!['done','wontfix','invalid'].includes(t.group));if(g==='clarify')return data.tickets.filter(t=>['needs-info','needs-triage'].includes(t.group));if(g==='anomalies')return data.tickets.filter(t=>t.errors.length||t.warnings.length);if(g==='search'){const q=query.toLocaleLowerCase();return data.tickets.filter(t=>`${t.num} ${t.title} ${t.raw}`.toLocaleLowerCase().includes(q));}return data.tickets.filter(t=>t.group===g);}
function branch(g,content,defaultOpen=true){const n=groupRows(g).length;const open=preferences.open[g]??defaultOpen;return `<details data-group="${g}"${open?' open':''}><summary>${selectLink(g,labels[g])}<span>${n}</span></summary>${content}</details>`;}
function qorder(q){return {open:0,drafting:1,applying:2}[q.status]??3;}
function qrows(unresolved){return (data?.questions||[]).filter(q=>Boolean(q.unresolved)===unresolved).sort((a,b)=>qorder(a)-qorder(b)||String(a.num).localeCompare(String(b.num),undefined,{numeric:true}));}
function qrow(q){const k='question:'+q.key;return `<div class="row q-${esc(q.status)}${selected===k?' selected':''}" data-select="${esc(k)}" data-question="${esc(q.key)}"><span class="num">${esc(q.num||'?')}</span>${selectLink(k,q.title,'title')}<div class="subrow">${esc(qstates[q.status]||'状态异常')}${q.blocks.length?' · 挡住 '+q.blocks.map(b=>badge(b,'r')).join(''):''}${q.errors.length||q.warnings.length?' · ⚠':''}</div></div>`;}
function qbranch(g,unresolved,defaultOpen){const qs=qrows(unresolved);if(!qs.length)return '';const open=preferences.open[g]??defaultOpen;return `<details data-group="${g}"${open?' open':''}><summary>${selectLink(g,labels[g])}<span>${qs.length}</span></summary>${qs.map(qrow).join('')}</details>`;}
function qtable(qs){if(!qs.length)return '<p class="empty">当前没有这类问题。</p>';return `<table class="index"><thead><tr><th>编号</th><th>问题</th><th>状态与挡住的票</th><th>推荐</th></tr></thead><tbody>${qs.map(q=>`<tr data-select="${esc('question:'+q.key)}"><td>${esc(q.num||'?')}</td><td>${selectLink('question:'+q.key,q.title)}</td><td><span class="tag">${esc(qstates[q.status]||'状态异常')}</span><div>${q.blocks.map(b=>badge(b,'r')).join('')}</div></td><td>${esc(q.recommended||'—')}</td></tr>`).join('')}</tbody></table>`;}
function qbanner(){const qs=qrows(true);if(!qs.length)return '';const n=data.counts.questions_open||0;return `<div class="qbanner"><strong>${n?n+' 个问题等你答复':'有未结问题'}</strong>${qs.map(q=>`<div>${selectLink('question:'+q.key,q.num+' '+q.title)} · ${esc(qstates[q.status]||'状态异常')}${q.blocks.length?' · 挡住 '+q.blocks.map(b=>esc(byKey(b)?.num||'?')).join('、'):''}${q.recommended?' · 推荐：'+esc(q.recommended):''}</div>`).join('')}</div>`;}
function renderTree(){const child=g=>branch(g,sorted(groupRows(g)).map(row).join(''));const clarify=groupRows('clarify').length?branch('clarify',['needs-triage','needs-info'].filter(g=>groupRows(g).length).map(child).join(''),false):'';$('#tree').innerHTML=selectLink('overview','总览','overview-link')+qbranch('questions',true,true)+branch('unfinished',child('active')+child('pending')+clarify)+branch('done',sorted(groupRows('done')).map(row).join(''),false)+branch('wontfix',sorted(groupRows('wontfix')).map(row).join(''),false)+qbranch('closedq',false,false);}
function table(ts){if(!ts.length)return '<p class="empty">当前没有这类票。</p>';return `<table class="index"><thead><tr><th>编号</th><th>实施票</th><th>状态与前置</th><th>认领 / 产品贡献</th></tr></thead><tbody>${sorted(ts).map(t=>`<tr data-select="${esc(target(t.key))}" class="${t.frontier?'frontier':''}"><td>${esc(t.num||'?')}</td><td>${selectLink(target(t.key),t.title)}</td><td>${flags(t)}<div>${deps(t)}</div></td><td>${esc(t.claimed||t.purpose.split('\n')[0]||'未记录认领')}</td></tr>`).join('')}</tbody></table>`;}
function renderMain(){const t=current();if(selected.startsWith('question:')){const q=qByKey(selected.slice(9));if(!q){$('#main').innerHTML=`<h2>问题已删除或无法定位</h2><p>${esc(selected.slice(9))}</p><p>可从目录或总览选择。</p>`;return;}$('#main').innerHTML=`<header class="ticket-head"><div class="metadata">questions/${esc(q.key)}</div><h2>${esc(q.num)} · ${esc(q.title)}</h2><div><span class="tag${q.status==='open'?' good':''}">${esc(qstates[q.status]||q.status||'状态异常')}</span></div><div class="metadata">提出：${esc(q.raised||'未记录')}</div><div>挡住 ${q.blocks.map(b=>badge(b,'r')).join('')||'无'}</div>${q.recommended?`<div class="brief"><strong>推荐</strong>${esc(q.recommended)}</div>`:''}${[...q.errors,...q.warnings].map(e=>`<div class="warnings">⚠ ${esc(e)}</div>`).join('')}</header><article class="body">${q.body_html}</article>`;return;}
if(selected==='questions'||selected==='closedq'){$('#main').innerHTML=`<h2>${esc(labels[selected])}</h2>${qtable(qrows(selected==='questions'))}`;return;}
if(selected.startsWith('ticket:')){if(!t){$('#main').innerHTML=`<h2>票已删除或无法定位</h2><p>${esc(deleted||selected.slice(7))}</p><p>未自动切换到其他票。可从目录或总览选择。</p>`;return;}$('#main').innerHTML=`${notice?`<p class="notice">${esc(notice)}</p>`:''}<header class="ticket-head"><div class="metadata">${esc(t.key)}</div><h2>${esc(t.num)} · ${esc(t.title)}</h2><div>${flags(t)}</div><div class="metadata">原标签：${esc(t.status)} · 认领：${esc(t.claimed||'未记录')}</div><div>前置 ${deps(t)||'无'}　后续 ${t.dependents.map(k=>badge(k,'b')).join('')||'无'}</div>${t.waiting.length?`<div class="metadata">等待前置：${t.waiting.map(k=>badge(k,'r')).join('')}</div>`:''}${t.purpose?`<div class="brief"><strong>产品贡献 · Purpose</strong>${esc(t.purpose)}</div>`:''}${t.direction?`<div class="brief"><strong>继承方向 · Direction</strong>${esc(t.direction)}</div>`:''}${[...t.errors,...t.warnings].map(e=>`<div class="warnings">⚠ ${esc(e)}</div>`).join('')}</header><article class="body">${t.body_html}</article>`;return;}
if(selected==='overview'){const c=data.counts;$('#main').innerHTML=`<h2>总览</h2>${qbanner()}<p>数据来自正式实施票。前沿仅表示声明的依赖已满足，并不保证文件或计算资源没有冲突。</p><div class="count-grid"><button data-select="pending"><strong>${c.frontier}</strong>可开工候选</button><button data-select="active"><strong>${c.active}</strong>进行中</button><button data-select="done"><strong>${c.complete}</strong>有效完成</button><button data-select="anomalies"><strong>${c.anomalies}</strong>有数据提示</button></div>${data.errors.map(e=>`<p class="warnings">${esc(e)}</p>`).join('')}${c.total===0?'<p class="empty">还没有正式实施票。看板不自动发布或执行草案。</p>':`<h3>当前前沿</h3>${table(data.tickets.filter(t=>t.frontier))}`}${c.anomalies?`<h3>数据提示</h3>${table(groupRows('anomalies'))}`:''}`;
}else{$('#main').innerHTML=`<h2>${esc(labels[selected]||'总览')}</h2>${selected==='pending'?'<p class="metadata">可开工票在前，依赖阻塞票在后；黄色背景标识前沿。</p>':''}${table(groupRows(selected))}`;}}
function render(){if(!data)return;$('#title').textContent=data.title;$('#summary').textContent=`${data.counts.total} 张正式票 · 有效完成 ${data.counts.complete} · 进行中 ${data.counts.active} · 不处理 ${data.counts.wontfix} · 无法分类 ${data.counts.invalid}${data.counts.questions_open?' · 待答问题 '+data.counts.questions_open:''}`;renderTree();renderMain();}
function readingPosition(){const nodes=[...$('#main').querySelectorAll('[data-anchor]')];const first=nodes.find(n=>n.getBoundingClientRect().bottom>80);return {x:scrollX,y:scrollY,anchor:first?.dataset.anchor,offset:first?.getBoundingClientRect().top,tree:$('#tree').scrollTop};}
function restorePosition(p){$('#tree').scrollTop=p.tree;const node=[...$('#main').querySelectorAll('[data-anchor]')].find(n=>n.dataset.anchor===p.anchor);if(node)scrollTo(p.x,scrollY+node.getBoundingClientRect().top-p.offset);else{scrollTo(p.x,p.y);if(p.anchor){const n=document.createElement('p');n.className='notice';n.textContent='正在阅读的内容已变化，已保留邻近阅读位置。';$('#main').prepend(n);}}}
function install(next){const p=readingPosition(),old=current();document.querySelectorAll('details[data-group]').forEach(d=>preferences.open[d.dataset.group]=d.open);if(old&&!next.tickets.some(t=>t.key===old.key)){const renamed=next.tickets.filter(t=>t.num&&t.num===old.num);const oldUnique=data.tickets.filter(t=>t.num===old.num).length===1;if(oldUnique&&renamed.length===1){selected=target(renamed[0].key);history.replaceState(null,'','#'+encodeURIComponent(selected));notice='票文件已重命名，仍保持选中同一张票。';}else{deleted=old.title;notice='';}}
data=next;render();restorePosition(p);save();}
function select(value){selected=value;deleted='';notice='';if(value.startsWith('ticket:')){const t=byKey(value.slice(7));if(t){preferences.open[t.group]=true;if(['active','pending','needs-info','needs-triage'].includes(t.group))preferences.open.unfinished=true;if(t.group.startsWith('needs-'))preferences.open.clarify=true;}}if(value.startsWith('question:')){const q=qByKey(value.slice(9));if(q)preferences.open[q.unresolved?'questions':'closedq']=true;}history.replaceState(null,'','#'+encodeURIComponent(value));render();save();scrollTo(0,0);}
function toast(text){const n=$('#message');n.textContent=text;n.hidden=false;clearTimeout(timer);timer=setTimeout(()=>n.hidden=true,5000);}
document.addEventListener('click',event=>{const copy=event.target.closest('[data-copy]');if(copy){event.preventDefault();const value=copy.dataset.copy;if(navigator.clipboard)navigator.clipboard.writeText(value).then(()=>toast('已复制：'+value),()=>toast('路径或引用：'+value));else toast('路径或引用：'+value);return;}const node=event.target.closest('[data-select]');if(node){event.preventDefault();select(node.dataset.select);}});
document.addEventListener('toggle',event=>{const d=event.target;if(d.matches?.('details[data-group]')){preferences.open[d.dataset.group]=d.open;save();}},true);
window.addEventListener('hashchange',()=>{selected=readHash();render();});
$('#search').addEventListener('input',event=>{query=event.target.value;if(query){selected='search';renderMain();}else select('overview');});
for(const [id,name]of [['before','before'],['after','after']]){const n=$('#'+id);n.checked=preferences[name];n.addEventListener('change',()=>{preferences[name]=n.checked;const p=$('#tree').scrollTop;renderTree();$('#tree').scrollTop=p;save();});}
function failure(message){$('#error').hidden=false;$('#error').textContent='更新失败，保留上次画面（数据可能过期）：'+message;}
function refreshed(stamp){$('#error').hidden=true;$('#refresh').textContent=(cfg.live?'最后成功读取：':'静态快照：')+new Date(stamp).toLocaleString('zh-CN',{hour12:false});}
async function poll(){try{const response=await fetch('api/board',{cache:'no-store'});const next=await response.json();if(!response.ok)throw Error(next.error||'无法读取文件');if(!data||next.revision!==data.revision)install(next);refreshed(next.generated_at);}catch(e){failure(e.message);}finally{setTimeout(poll,2000);}}
if(cfg.snapshot){data=cfg.snapshot;render();refreshed(data.generated_at);}else{failure(cfg.error||'暂无有效快照');$('#main').innerHTML='<h2>暂时无法读取实施票</h2><p>修复文件后可重试，未将读取失败解释为空票集合。</p>';}
if(cfg.live)setTimeout(poll,2000);
})();
'''


def build(effort, live=False, labels_path=None):
    import html
    try:
        snapshot, error = presentation(load(effort, labels_path)), ''
    except (OSError, ValueError) as exc:
        if not live:
            raise
        snapshot, error = None, str(exc)
    config = json.dumps(dict(snapshot=snapshot, error=error, live=live, directory=str(Path(effort).resolve())), ensure_ascii=False).replace('<', '\\u003c')
    return ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>实施票看板</title><style>' + CSS + '</style><body><div class="wrap">'
            '<header><div class="eyebrow">实施票看板 · 只读</div><h1 id="title">' + html.escape(Path(effort).name) + '</h1><p id="summary" class="summary"></p></header>'
            '<div class="toolbar"><input id="search" type="search" placeholder="搜索编号、标题或正文" aria-label="搜索实施票">'
            '<label><input id="before" type="checkbox">前置高亮</label><label><input id="after" type="checkbox">后续高亮</label><span id="refresh" class="refresh"></span></div>'
            '<div id="error" class="error-banner" role="status" hidden></div><div class="cols"><nav id="tree" class="tree" aria-label="实施票目录"></nav>'
            '<main id="main"></main></div><footer class="footer">数据来源：issues/*.md 与 questions/*.md · 不以总览或manifest判定状态</footer></div>'
            '<div id="message" class="message" role="status" hidden></div><script id="bootstrap" type="application/json">' + config + '</script><script>' + JS + '</script></body></html>')


def make_server(effort, port=8766, labels_path=None):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    class Handler(BaseHTTPRequestHandler):
        def reply(self, code, body, content_type):
            data = body.encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', content_type + '; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path in ('/', '/index.html'):
                self.reply(200, build(effort, live=True, labels_path=labels_path), 'text/html')
            elif path == '/api/board':
                try:
                    data = presentation(load(effort, labels_path))
                    self.reply(200, json.dumps(data, ensure_ascii=False), 'application/json')
                except (OSError, ValueError) as exc:
                    self.reply(503, json.dumps({'error': str(exc)}, ensure_ascii=False), 'application/json')
            else:
                self.reply(404, '页面不存在', 'text/plain')

        def do_POST(self):
            self.reply(405, '只读看板不接受写入请求', 'text/plain')

        do_PUT = do_DELETE = do_PATCH = do_POST

        def log_message(self, *args):
            pass
    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description='实施票只读看板：读取正式issues目录，自动推导前沿；不需要map或manifest。', add_help=False)
    parser.add_argument('-h', '--help', action='help', help='显示使用说明')
    parser._positionals.title = '位置参数'
    parser._optionals.title = '选项'
    parser.add_argument('directory', type=Path, help='实施目录（包含issues/*.md）')
    parser.add_argument('--serve', action='store_true', help='本机只读服务，自动刷新')
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--labels', type=Path, help='显式指定项目标签映射文件')
    parser.add_argument('-o', '--output', type=Path, default=Path('implementation-board.html'))
    args = parser.parse_args(argv)
    try:
        if args.serve:
            server = make_server(args.directory, args.port, args.labels)
            print(f'实施票看板 http://127.0.0.1:{server.server_port} · 只读，Ctrl-C停止', flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
        else:
            # Export may write an artifact, never overwrite source tickets or mapping.
            output = args.output.resolve()
            protected = [args.directory.resolve() / 'issues', args.directory.resolve() / 'questions']
            mapping = args.labels.resolve() if args.labels else label_file(args.directory.resolve())
            if any(output == p or p in output.parents for p in protected) or output == mapping:
                raise ValueError('导出路径不能覆盖实施票、问题或标签映射')
            args.output.write_text(build(args.directory, labels_path=args.labels), encoding='utf-8')
            print('已导出只读快照：' + str(args.output))
    except (OSError, ValueError) as exc:
        parser.exit(1, str(exc) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
