#!/usr/bin/env python3
"""A local board for a wayfinder map: every ticket, its state, and the fog.

    python3 scripts/wayfinder_board.py .scratch/<effort> --serve
        Live view on http://127.0.0.1:8765 -- every refresh re-reads the
        files, so F5 is always current. Leave it running.

    python3 scripts/wayfinder_board.py .scratch/<effort> -o board.html
        One static snapshot instead.

Reads map.md and issues/*.md. Lanes are computed, not declared: a ticket is
on the frontier when it is open, unclaimed, and every ticket it lists under
`Blocked by` has resolved -- the same query the wayfinder skill defines.

Layout is a tree on the left and one view on the right. The tree is the only
navigation: click a group to get an index table of it, click a ticket to read
it. The selected node lives in the URL hash, the tree's open/closed state in
localStorage, so F5 lands you where you were.

Standard library only. Nothing leaves this machine.
"""
import sys, os, re, html, glob, datetime, json

# ---------------------------------------------------------------- markdown

_CODE = "\x00C%d\x00"

def _inline(s):
    codes = []
    def stash(m):
        codes.append(m.group(1))
        return _CODE % (len(codes) - 1)
    s = html.escape(s)
    s = re.sub(r'`([^`]+)`', stash, s)
    # links: local .md paths become inert refs, real urls stay links
    def link(m):
        text, url = m.group(1), m.group(2)
        if url.startswith(('http://', 'https://')):
            return '<a href="%s" target="_blank" rel="noopener">%s</a>' % (url, text)
        return '<span class="ref" title="%s">%s</span>' % (html.escape(url, quote=True), text)
    s = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', link, s)
    s = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', s)
    for i, c in enumerate(codes):
        s = s.replace(_CODE % i, '<code>%s</code>' % c)
    return s

def md(text):
    lines = text.split('\n')
    out, i, n = [], 0, len(lines)
    para = []
    def flush():
        if para:
            out.append('<p>' + '<br>'.join(_inline(x) for x in para) + '</p>')
            para.clear()
    while i < n:
        ln = lines[i]
        st = ln.strip()
        if not st:
            flush(); i += 1; continue
        if st.startswith('<!--'):
            i += 1; continue
        # table
        if st.startswith('|') and i + 1 < n and re.match(r'^\|[\s:|-]+\|$', lines[i+1].strip()):
            flush()
            head = [c.strip() for c in st.strip('|').split('|')]
            i += 2
            rows = []
            while i < n and lines[i].strip().startswith('|'):
                rows.append([c.strip() for c in lines[i].strip().strip('|').split('|')])
                i += 1
            t = ['<div class="tw"><table><thead><tr>']
            t += ['<th>%s</th>' % _inline(c) for c in head]
            t.append('</tr></thead><tbody>')
            for r in rows:
                t.append('<tr>' + ''.join('<td>%s</td>' % _inline(c) for c in r) + '</tr>')
            t.append('</tbody></table></div>')
            out.append(''.join(t)); continue
        # heading
        m = re.match(r'^(#{3,6})\s+(.*)$', st)
        if m:
            flush()
            lvl = min(len(m.group(1)) + 1, 6)
            out.append('<h%d>%s</h%d>' % (lvl, _inline(m.group(2)), lvl))
            i += 1; continue
        # list
        if re.match(r'^[-*]\s+', st) or re.match(r'^\d+\.\s+', st):
            flush()
            ordered = bool(re.match(r'^\d+\.\s+', st))
            tag = 'ol' if ordered else 'ul'
            items, cur, base = [], None, len(ln) - len(ln.lstrip())
            while i < n:
                raw = lines[i]
                s2 = raw.strip()
                if not s2:
                    if i + 1 < n and (re.match(r'^\s*[-*]\s+', lines[i+1]) or re.match(r'^\s*\d+\.\s+', lines[i+1])):
                        i += 1; continue
                    break
                ind = len(raw) - len(raw.lstrip())
                mi = re.match(r'^(?:[-*]|\d+\.)\s+(.*)$', s2)
                if mi and ind <= base:
                    if cur is not None:
                        items.append(cur)
                    cur = [mi.group(1)]
                elif cur is not None:
                    cur.append(s2)
                else:
                    break
                i += 1
            if cur is not None:
                items.append(cur)
            out.append('<%s>%s</%s>' % (tag, ''.join(
                '<li>%s</li>' % '<br>'.join(_inline(x) for x in it) for it in items), tag))
            continue
        if st.startswith('> '):
            flush()
            q = []
            while i < n and lines[i].strip().startswith('>'):
                q.append(lines[i].strip().lstrip('>').strip()); i += 1
            out.append('<blockquote>%s</blockquote>' % ' '.join(_inline(x) for x in q))
            continue
        para.append(st); i += 1
    flush()
    return '\n'.join(out)

# ---------------------------------------------------------------- parsing

def sections(text):
    """Split a markdown doc on '## ' headings -> (preamble, {name: body})."""
    parts = re.split(r'^##\s+(.+)$', text, flags=re.M)
    pre = parts[0]
    d = {}
    for j in range(1, len(parts), 2):
        d[parts[j].strip()] = parts[j + 1].strip()
    return pre, d

def parse_ticket(path):
    with open(path, encoding='utf-8') as f:
        raw = f.read()
    pre, sec = sections(raw)
    t = {'file': os.path.basename(path), 'path': path}
    t['num'] = t['file'].split('-')[0]
    m = re.search(r'^#\s+(.+)$', pre, re.M)
    t['title'] = m.group(1).strip() if m else t['file']
    def field(name, default=''):
        m = re.search(r'^%s:\s*(.+)$' % name, pre, re.M)
        return m.group(1).strip() if m else default
    t['type'] = field('Type', 'grilling')
    t['status'] = field('Status', 'open').lower()
    # `Claimed: YYYY-MM-DD <pointer>`; a legacy `Assignee:` line is read as a bare note
    c = field('Claimed') or field('Assignee')
    cm = re.match(r'^(\d{4}-\d{2}-\d{2})\s*(.*)$', c)
    t['claimed'] = c
    t['claimed_on'] = cm.group(1) if cm else ''
    t['claimed_note'] = (cm.group(2) if cm else c).strip()
    bb = field('Blocked by')
    t['blockedby'] = [x.strip() for x in re.split(r'[,\s]+', bb) if x.strip()] if bb else []
    t['question'] = sec.get('Question', '')
    t['answer'] = sec.get('Answer', '')
    tm = re.match(r'^(\w+)(?:\s*\((\w+)\))?', t['type'])
    t['kind'] = tm.group(1) if tm else t['type']
    t['loop'] = (tm.group(2) or '') if tm else ''
    return t

def parse_decisions(text):
    """Decisions-so-far bullets -> {ticket num: gist markdown}.

    Each bullet is `- [title](issues/NN-slug.md)：gist ...`; the gist is
    everything after the first link, with the leading colon stripped.
    """
    out = {}
    for m in re.finditer(r'^\s*-\s+\[[^\]]*\]\(issues/(\d+)-[^)]*\)\s*[:：]?\s*(.*)$', text, re.M):
        out[m.group(1)] = m.group(2).strip()
    return out

def repo_root(path):
    """Nearest ancestor holding .git, else the cwd."""
    p = os.path.abspath(path)
    while True:
        if os.path.exists(os.path.join(p, '.git')):
            return p
        q = os.path.dirname(p)
        if q == p:
            return os.getcwd()
        p = q

def load(effort):
    with open(os.path.join(effort, 'map.md'), encoding='utf-8') as f:
        raw = f.read()
    pre, ms = sections(raw)
    m = re.search(r'^#\s+(.+)$', pre, re.M)
    title = m.group(1).strip() if m else os.path.basename(os.path.abspath(effort))
    tickets = [parse_ticket(p) for p in sorted(glob.glob(os.path.join(effort, 'issues', '*.md')))]
    root = repo_root(effort)
    for t in tickets:
        t['relpath'] = os.path.relpath(t['path'], root).replace(os.sep, '/')
    done = {t['num'] for t in tickets if t['status'] == 'resolved'}
    decisions = parse_decisions(ms.get('Decisions so far', ''))
    for t in tickets:
        t['waiting'] = [b for b in t['blockedby'] if b not in done]
        # claimed wins over blocked: the tree groups by who holds the ticket,
        # and being blocked is a marker inside "unclaimed", not a lane of its own
        if t['status'] == 'resolved':
            t['lane'] = 'resolved'
        elif t['status'] == 'claimed':
            t['lane'] = 'claimed'
        elif t['waiting']:
            t['lane'] = 'blocked'
        else:
            t['lane'] = 'frontier'
        t['decision'] = decisions.get(t['num']) if t['status'] == 'resolved' else None
    # Reverse edges are part of the permanent map topology. The unresolved
    # subset controls badge emphasis; it does not remove resolved edges.
    for t in tickets:
        t['dependents'] = [u['num'] for u in tickets if t['num'] in u['blockedby']]
        t['pending_dependents'] = [u['num'] for u in tickets
                                   if u['num'] in t['dependents'] and u['status'] != 'resolved']
    return title, ms, tickets

# ---------------------------------------------------------------- rendering

CSS = r"""
:root{
  --paper:#f6f8f6; --surface:#ffffff; --sunk:#eef1ee;
  --ink:#151d1a; --body:#2c3833; --muted:#68756e; --faint:#94a09a;
  --line:#dde3de; --hair:#e8ece8;
  --accent:#1f5f5b; --accent-soft:#e3efed;
  --frontier:#a2600d; --frontier-soft:#fbf1e2; --frontier-line:#e6c894;
  --blocked:#586a89; --blocked-soft:#eef1f6;
  --resolved:#2f6f50; --resolved-soft:#e8f2ec;
  --red:#d6262b; --blue:#1f66e5; --badge-fg:#ffffff;
  --sel-bg:#b6dbd5;
  --fog:#8d9a93; --fog-ink:#3f4d47; --out-ink:#57645d; --fog-bg:#eef2f0;
  --shadow:0 1px 2px rgba(20,40,32,.05),0 4px 14px -6px rgba(20,40,32,.10);
  --mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
  --sans:"IBM Plex Sans","PingFang SC","Hiragino Sans GB","Noto Sans CJK SC","Source Han Sans SC","Microsoft YaHei",sans-serif;
  --label:"Archivo","IBM Plex Sans","PingFang SC","Noto Sans CJK SC",sans-serif;
}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--body);
  font-family:var(--sans);font-size:17px;line-height:1.72;
  -webkit-font-smoothing:antialiased}
a{color:var(--accent);text-underline-offset:2px}
code{font-family:var(--mono);font-size:.86em;background:var(--sunk);
  padding:.1em .34em;border-radius:3px;color:var(--ink);
  border:1px solid var(--hair);word-break:break-word}
.ref{font-family:var(--mono);font-size:.84em;color:var(--muted);
  border-bottom:1px dotted var(--line);cursor:help}
strong{color:var(--ink);font-weight:600}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:3px}
[hidden]{display:none!important}

.wrap{max-width:1240px;margin:0 auto;padding:0 28px 96px}

/* ---- masthead ---- */
.top{border-bottom:1px solid var(--line);margin-bottom:30px;padding:36px 0 22px}
.eyebrow{font-family:var(--mono);font-size:12.5px;letter-spacing:.16em;
  text-transform:uppercase;color:var(--faint);margin:0 0 10px}
h1{font-family:var(--label);font-size:clamp(28px,4vw,40px);line-height:1.14;
  font-weight:700;letter-spacing:-.015em;color:var(--ink);margin:0 0 6px;
  text-wrap:balance}
.sub{font-size:15px;color:var(--muted);margin:0;font-variant-numeric:tabular-nums}
.sub b{color:var(--ink);font-weight:600}

/* ---- layout ---- */
.cols{display:grid;grid-template-columns:300px minmax(0,1fr);gap:40px;
  align-items:start}
@media(max-width:900px){.cols{grid-template-columns:1fr;gap:26px}}

/* ---- tree ---- */
.tree{position:sticky;top:18px;max-height:calc(100vh - 36px);overflow-y:auto;
  padding-right:4px}
@media(max-width:900px){.tree{position:static;max-height:none;
  border:1px solid var(--line);border-radius:6px;padding:12px;background:var(--surface)}}
.tree ul{list-style:none;margin:0;padding:0}
.tree ul ul{padding-left:14px}
.tree li.closed > ul{display:none}
.row{display:flex;align-items:baseline;gap:6px;padding:4px 6px 4px 4px;
  border-radius:4px;position:relative}
.tk > .row{flex-wrap:wrap;cursor:pointer}
.row:hover{background:var(--sunk)}
.tk > .row:hover{background:color-mix(in srgb,var(--surface) 88%,black)}
.on > .row{background:var(--sel-bg)}
.on > .row .node{color:var(--ink)}
.on > .row .node i{color:var(--muted)}
.tk.is-frontier > .row{background:var(--frontier-soft)}
.tk.is-frontier > .row:hover{background:color-mix(in srgb,var(--frontier-soft) 88%,black)}
.tk.is-frontier.on > .row{background:var(--sel-bg)}
.on > .row:hover,.tk.is-frontier.on > .row:hover{background:color-mix(in srgb,var(--sel-bg) 88%,black)}
.tk.rel-dependent > .row::before,.tk.rel-predecessor > .row::before{
  content:"";position:absolute;left:0;top:4px;bottom:4px;width:8px;
  border-radius:4px;pointer-events:none}
.tk.rel-dependent > .row::before{background:var(--blue)}
.tk.rel-predecessor > .row::before{background:var(--red)}
.tk.is-resolved.rel-dependent > .row::before{background:color-mix(in srgb,var(--blue) 50%,transparent)}
.tk.is-resolved.rel-predecessor > .row::before{background:color-mix(in srgb,var(--red) 50%,transparent)}
.tg{flex:0 0 14px;width:14px;height:14px;padding:0;border:0;background:none;
  color:var(--faint);cursor:pointer;position:relative;top:1px;align-self:center}
button.tg::before{content:"";display:block;width:0;height:0;margin:auto;
  border:4.5px solid transparent;border-left:6px solid currentColor;border-right:0;
  transform:rotate(90deg);transition:transform .12s}
.closed > .row > .tg::before{transform:rotate(0)}
span.tg{cursor:default}
.node{flex:1 1 auto;min-width:0;text-decoration:none;color:var(--body);
  font-size:15px;line-height:1.42}
.tk > .row > .node{flex:1 0 calc(100% - 20px)}
.node:hover{color:var(--ink)}
.group > .row > .node{font-family:var(--label);font-weight:700;color:var(--ink)}
.node i{font-family:var(--mono);font-style:normal;font-size:13px;
  color:var(--muted);font-variant-numeric:tabular-nums;margin-left:7px;font-weight:400}
.tk .node i{margin:0 7px 0 0}
.tail{flex:0 0 auto;display:flex;gap:4px;align-items:baseline}
.tail:empty{display:none}
.tk > .row > .tail:not(:empty){flex:0 0 calc(100% - 20px);margin-left:20px;
  flex-wrap:wrap}
.who{font-family:var(--mono);font-style:normal;font-size:12px;color:var(--accent);
  white-space:nowrap;display:block;margin-left:2.35em;line-height:1.3;padding-bottom:2px}
.leaf-map > .row > .node{color:var(--fog);font-family:var(--label);font-weight:700}
.tree .sep{height:1px;background:var(--hair);margin:10px 0 8px}
.rel-controls{display:flex;align-items:center;gap:14px;margin:1px 6px 9px 20px;
  padding:3px 0 7px;border-bottom:1px solid var(--hair)}
.rel-controls label{display:inline-flex;align-items:center;gap:5px;font-size:12.5px;
  color:var(--muted);cursor:pointer}
.rel-controls input{margin:0;accent-color:var(--accent);cursor:pointer}

/* ---- dependency badges: hue = direction, fill = related ticket state ---- */
.badge{font-family:var(--mono);font-size:12px;padding:0 5px;border-radius:3px;
  text-decoration:none;font-variant-numeric:tabular-nums;line-height:1.55;
  display:inline-block;font-weight:600;letter-spacing:.02em;border:1px solid transparent}
.badge.r{background:var(--red);color:var(--badge-fg)}
.badge.b{background:var(--blue);color:var(--badge-fg)}
.badge.r.is-resolved{background:color-mix(in srgb,var(--red) 50%,transparent);color:var(--badge-fg)}
.badge.b.is-resolved{background:color-mix(in srgb,var(--blue) 50%,transparent);color:var(--badge-fg)}
.badge:hover{filter:brightness(1.12)}
.dep{white-space:nowrap;margin-right:10px;font-size:14px}
.dep-r,.dep-b{color:var(--muted)}
.dep .badge{margin-left:2px}

/* ---- views ---- */
.view{scroll-margin-top:20px}
.sechead{display:flex;align-items:baseline;gap:12px;margin-bottom:6px}
.sechead h2{font-family:var(--label);font-size:22px;font-weight:700;
  letter-spacing:-.01em;color:var(--ink);margin:0}
.sechead em{font-family:var(--mono);font-style:normal;font-size:13px;
  color:var(--faint);font-variant-numeric:tabular-nums}
.secnote{font-size:14.5px;color:var(--muted);margin:0 0 18px;max-width:66ch}
.block{margin-bottom:36px}

/* ---- index tables ---- */
.tw{overflow-x:auto;margin:1em 0;border:1px solid var(--hair);border-radius:5px}
table{border-collapse:collapse;width:100%;font-size:14.5px}
th,td{padding:6px 11px;text-align:left;border-bottom:1px solid var(--hair);
  vertical-align:top}
th{font-family:var(--label);font-size:12px;letter-spacing:.06em;
  text-transform:uppercase;color:var(--muted);background:var(--sunk);
  font-weight:700;white-space:nowrap}
td{font-variant-numeric:tabular-nums}
tbody tr:last-child td{border-bottom:0}
.idx{background:var(--surface)}
.idx td{padding:9px 11px;line-height:1.5}
.idx tr[data-go]{cursor:pointer}
.idx tr[data-go]:hover td{background:var(--sunk)}
.idx tr.is-frontier td{background:var(--frontier-soft)}
.idx tr.is-frontier:hover td{background:var(--frontier-soft);filter:brightness(.97)}
.idx td.n{font-family:var(--mono);color:var(--faint);white-space:nowrap;font-size:13px}
.idx td.t a{text-decoration:none;color:var(--ink);font-weight:600;font-family:var(--label)}
.idx td.t a:hover{text-decoration:underline}
.idx td.d{white-space:nowrap}
.idx td.q{color:var(--muted);font-size:14px;max-width:34ch}
.idx td.w{font-family:var(--mono);font-size:12.5px;color:var(--accent);white-space:nowrap}
.idx td.c{white-space:nowrap}
.nodec{color:var(--red);font-size:13px}

/* ---- ticket card ---- */
.card{background:var(--surface);border:1px solid var(--line);
  border-radius:7px;margin-bottom:14px;overflow:hidden;box-shadow:var(--shadow)}
.card.is-frontier{border-left:3px solid var(--frontier)}
.card.is-claimed{border-left:3px solid var(--accent)}
.card.is-blocked{border-left:3px solid var(--blocked)}
.card.is-resolved{border-left:3px solid var(--resolved)}
.chead{display:flex;flex-wrap:wrap;align-items:baseline;gap:10px;
  padding:16px 22px 0}
.cnum{font-family:var(--mono);font-size:13px;font-weight:600;
  color:var(--faint);font-variant-numeric:tabular-nums}
.ctitle{font-family:var(--label);font-size:21px;font-weight:600;
  color:var(--ink);margin:0;letter-spacing:-.005em;flex:1 1 260px;
  line-height:1.3}
.chips{display:flex;flex-wrap:wrap;gap:6px;padding:9px 22px 0}
.chip{font-family:var(--label);font-size:12px;letter-spacing:.07em;
  text-transform:uppercase;font-weight:700;padding:2.5px 8px;
  border-radius:3px;border:1px solid transparent;white-space:nowrap}
.chip-kind{background:var(--sunk);color:var(--muted);border-color:var(--hair)}
.chip-loop{background:transparent;color:var(--muted);border-color:var(--line)}
.chip-frontier{background:var(--frontier-soft);color:var(--frontier);
  border-color:var(--frontier-line)}
.chip-claimed{background:var(--accent-soft);color:var(--accent)}
.chip-blocked{background:var(--blocked-soft);color:var(--blocked)}
.chip-resolved{background:var(--resolved-soft);color:var(--resolved)}
.cpath{margin:10px 22px 0}
.copy{font-family:var(--mono);font-size:13px;color:var(--muted);background:var(--sunk);
  border:1px solid var(--hair);border-radius:4px;padding:3px 9px;cursor:pointer;
  display:inline-flex;gap:10px;align-items:baseline;max-width:100%;text-align:left}
.copy:hover{color:var(--ink);border-color:var(--line)}
.copy code{background:none;border:0;padding:0;font-size:inherit;color:inherit;word-break:break-all}
.copy .cp{font-family:var(--label);font-size:11px;letter-spacing:.06em;text-transform:uppercase;
  color:var(--accent);font-weight:700;white-space:nowrap}
.copy.ok .cp{color:var(--resolved)}
.copy.fail .cp{color:var(--red)}
.decision{margin:14px 22px 0;padding:10px 14px;border-radius:5px;
  background:var(--resolved-soft);color:var(--ink);font-size:15px;line-height:1.6;
  border-left:3px solid var(--resolved)}
.decision::before{content:"结论 ";font-family:var(--label);font-weight:700;
  font-size:12px;letter-spacing:.08em;color:var(--resolved);margin-right:4px}
.decision .nodec{font-size:inherit}
.waitfor{padding:10px 22px 0;margin:0;font-size:14.5px}
.cbody{padding:4px 22px 18px;max-width:72ch}
.cbody p{margin:.75em 0}
.cbody h4,.cbody h5{font-family:var(--label);color:var(--ink);
  margin:1.4em 0 .4em;font-size:15px;font-weight:700;letter-spacing:.01em}
.cbody ul,.cbody ol{margin:.7em 0;padding-left:1.35em}
.cbody li{margin:.34em 0}
.cbody blockquote{margin:.8em 0;padding-left:14px;
  border-left:2px solid var(--line);color:var(--muted)}
.assignee{font-family:var(--mono);font-size:13px;color:var(--faint);
  padding:0 22px 14px}
details.answer{border-top:1px solid var(--hair);margin-top:2px}
details.answer summary{cursor:pointer;padding:11px 22px;font-size:14.5px;
  color:var(--resolved);font-weight:600;list-style:none;
  font-family:var(--label);letter-spacing:.02em}
details.answer summary::-webkit-details-marker{display:none}
details.answer summary::before{content:"▸ ";font-size:11px}
details.answer[open] summary::before{content:"▾ "}
details.answer summary:hover{background:var(--resolved-soft)}
details.answer .cbody{padding-top:2px}

/* ---- fog: no cards, low contrast, soft ground ---- */
.fog{background:var(--fog-bg);border-radius:8px;padding:24px 26px;
  border:1px dashed var(--line)}
.fog ul{list-style:none;margin:0;padding:0}
.fog li{margin:0 0 15px;padding-left:20px;position:relative;
  color:var(--fog-ink);max-width:70ch}
.fog li:last-child{margin-bottom:0}
.fog li::before{content:"";position:absolute;left:0;top:.72em;
  width:9px;height:1px;background:var(--fog)}
.fog strong{color:var(--ink);font-weight:600}
.fog code{background:transparent;border-color:var(--line);color:var(--fog-ink)}
.out li{color:var(--out-ink)}
.out strong{color:var(--muted)}
.out{background:transparent;border-style:solid;border-color:var(--hair)}

/* ---- map: destination + notes ---- */
.notes{background:var(--surface);border:1px solid var(--line);
  border-radius:7px;padding:6px 24px 20px;max-width:74ch}
.notes ol,.notes ul{padding-left:1.3em}
.notes li{margin:.45em 0}
.notes p{margin:.8em 0}

footer{margin-top:60px;padding-top:20px;border-top:1px solid var(--line);
  font-size:13px;color:var(--faint);font-family:var(--mono);
  display:flex;flex-wrap:wrap;gap:6px 20px}
@media (prefers-reduced-motion:reduce){*{transition:none!important;
  animation:none!important}}
"""

JS = r"""
(function(){
  var tree=document.getElementById('tree'), main=document.getElementById('main');
  var cols=document.querySelector('.cols');
  var KEY='wayfinder-board:open:'+(document.body.dataset.effort||'');
  var REL_KEY='wayfinder-board:relations:'+(document.body.dataset.effort||'');
  var views={}, nodes={};
  main.querySelectorAll('[data-view]').forEach(function(s){views[s.dataset.view]=s;});
  tree.querySelectorAll('[data-node]').forEach(function(l){nodes[l.dataset.node]=l;});
  var groups=Object.keys(nodes).filter(function(k){return nodes[k].classList.contains('group');});

  function saveOpen(){
    try{localStorage.setItem(KEY,JSON.stringify(groups.filter(function(g){
      return !nodes[g].classList.contains('closed');})));}catch(e){}
  }
  var open=null;
  try{open=JSON.parse(localStorage.getItem(KEY));}catch(e){}
  if(!Array.isArray(open)) open=['unresolved','claimed','open'];
  groups.forEach(function(g){nodes[g].classList.toggle('closed',open.indexOf(g)<0);});

  var relationControls=[document.getElementById('toggle-predecessors'),
                        document.getElementById('toggle-dependents')];
  var relationPrefs={predecessors:true,dependents:true};
  try{
    var savedRelations=JSON.parse(localStorage.getItem(REL_KEY));
    if(savedRelations&&typeof savedRelations.predecessors==='boolean'&&
       typeof savedRelations.dependents==='boolean'){
      relationPrefs.predecessors=savedRelations.predecessors;
      relationPrefs.dependents=savedRelations.dependents;
    }
  }catch(e){}
  relationControls[0].checked=relationPrefs.predecessors;
  relationControls[1].checked=relationPrefs.dependents;

  function clearRelations(){
    tree.querySelectorAll('.rel-predecessor,.rel-dependent').forEach(function(t){
      t.classList.remove('rel-predecessor','rel-dependent');
    });
  }
  function markRelated(raw,cls,selected){
    (raw||'').split(',').filter(Boolean).forEach(function(n){
      var target=nodes['t'+n];
      if(target&&target!==selected) target.classList.add(cls);
    });
  }
  function markRelations(li){
    clearRelations();
    if(!li||!li.classList.contains('tk')) return;
    if(relationPrefs.dependents) markRelated(li.dataset.dependents,'rel-dependent',li);
    if(relationPrefs.predecessors) markRelated(li.dataset.predecessors,'rel-predecessor',li);
  }
  function select(name){
    if(!views[name]) name='unresolved';
    Object.keys(views).forEach(function(k){views[k].hidden=(k!==name);});
    tree.querySelectorAll('.on').forEach(function(e){e.classList.remove('on');});
    var li=nodes[name];
    markRelations(li);
    if(!li) return;
    li.classList.add('on');
    // only ever expand ancestors; never collapse what the user opened
    var p=li.parentElement;
    while(p&&p!==tree){
      if(p.classList&&p.classList.contains('group')) p.classList.remove('closed');
      p=p.parentElement;
    }
    saveOpen();
    var row=li.querySelector(':scope > .row');
    if(row&&row.scrollIntoView) row.scrollIntoView({block:'nearest'});
  }
  function current(){return decodeURIComponent(location.hash.slice(1))||'unresolved';}
  relationControls.forEach(function(input){
    input.addEventListener('change',function(){
      var key=input.id==='toggle-predecessors'?'predecessors':'dependents';
      relationPrefs[key]=input.checked;
      try{localStorage.setItem(REL_KEY,JSON.stringify(relationPrefs));}catch(e){}
      markRelations(nodes[current()]);
    });
  });
  function onHash(){
    select(current());
    var top=cols.getBoundingClientRect().top+window.pageYOffset-12;
    if(window.pageYOffset>top) window.scrollTo(0,top);
  }
  window.addEventListener('hashchange',onHash);
  tree.addEventListener('click',function(e){
    var tg=e.target.closest('button.tg');
    if(tg){
      tg.closest('[data-node]').classList.toggle('closed'); saveOpen();
      e.preventDefault(); return;
    }
    var badge=e.target.closest('a.badge');
    if(badge) return;
    if(e.button!==0||e.ctrlKey||e.metaKey||e.shiftKey||e.altKey) return;
    var ticketRow=e.target.closest('.tk > .row');
    if(ticketRow){
      e.preventDefault();
      location.hash=ticketRow.parentElement.dataset.node;
      return;
    }
    var a=e.target.closest('a.node');
    if(a){
      var li=a.closest('[data-node]');
      if(li.classList.contains('group')){li.classList.remove('closed'); saveOpen();}
    }
  });
  function copyText(text){
    if(navigator.clipboard&&navigator.clipboard.writeText) return navigator.clipboard.writeText(text);
    return new Promise(function(res,rej){
      var ta=document.createElement('textarea'); ta.value=text;
      ta.style.position='fixed'; ta.style.opacity='0';
      document.body.appendChild(ta); ta.select();
      var ok=false; try{ok=document.execCommand('copy');}catch(err){}
      document.body.removeChild(ta); ok?res():rej();
    });
  }
  main.addEventListener('click',function(e){
    var cp=e.target.closest('button.copy');
    if(cp){
      var lab=cp.querySelector('.cp');
      copyText(cp.dataset.copy).then(function(){cp.classList.add('ok'); lab.textContent='已复制';},
        function(){cp.classList.add('fail'); lab.textContent='复制失败，请手动选中';});
      setTimeout(function(){cp.classList.remove('ok','fail'); lab.textContent='复制';},1600);
      return;
    }
    var tr=e.target.closest('tr[data-go]');
    if(tr&&!e.target.closest('a')) location.hash=tr.dataset.go;
  });
  select(current());
})();
"""

LANE_LABEL = {'frontier': '可拿', 'claimed': '在解', 'blocked': '被挡', 'resolved': '已解'}

GROUPS = {
    'unresolved': ('未解决', '还没落地的票。上面是在解的，下面是没人认领的。'),
    'claimed':    ('认领', '已被某个 session 认领。答案未经确认前，结论不出这张票。'),
    'open':       ('未认领', '没人认领的票。没被挡的按编号排在前面，第一张就是 wayfinder 规则里该拿的那张；'
                            '被挡的沉在最后，红色编号是它在等的票。'),
    'resolved':   ('已解决', '走过的路。「结论」一列取自地图的 Decisions so far，细节点进票看。'),
}

def esc(s):
    return html.escape(s)

def chip(cls, txt):
    return '<span class="chip chip-%s">%s</span>' % (cls, esc(txt))

def claimed_short(t):
    """What the tree shows: the date if there is one, else the bare note."""
    return t['claimed_on'] or t['claimed_note']

def first_sentence(q, limit=64):
    for ln in q.split('\n'):
        st = ln.strip()
        if not st or st.startswith(('#', '<!--', '|', '>')):
            continue
        st = re.sub(r'^(?:[-*]|\d+\.)\s+', '', st)
        st = st.replace('**', '')
        st = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', st)
        m = re.search(r'[。？！?!]', st)
        if m:
            st = st[:m.end()]
        if len(st) > limit:
            st = st[:limit].rstrip() + '…'
        return _inline(st)
    return ''

def badges(kind, nums, unresolved, relation):
    out = []
    for n in nums:
        active = n in unresolved
        cls = kind if active else kind + ' is-resolved'
        state = '未解决' if active else '已解决'
        out.append('<a class="badge %s" href="#t%s" title="%s %s · %s">%s</a>'
                   % (cls, esc(n), relation, esc(n), state, esc(n)))
    return ''.join(out)

def deps(t):
    """Render every direct edge; saturation reflects the related ticket's status."""
    h = []
    if t['blockedby']:
        h.append('<span class="dep dep-r">前置 %s</span>'
                 % badges('r', t['blockedby'], t['waiting'], '前置票'))
    if t['dependents']:
        h.append('<span class="dep dep-b">后续 %s</span>'
                 % badges('b', t['dependents'], t['pending_dependents'], '后续票'))
    return ''.join(h)

# ---- tree

def tree_ticket(t):
    who = ('<em class="who" title="%s">%s</em>' % (esc(t['claimed']), esc(claimed_short(t)))
           if t['claimed'] else '')
    tail = []
    if t['blockedby']:
        tail.append(badges('r', t['blockedby'], t['waiting'], '前置票'))
    if t['dependents']:
        tail.append(badges('b', t['dependents'], t['pending_dependents'], '后续票'))
    return ('<li class="tk is-%s" data-node="t%s" data-predecessors="%s" data-dependents="%s">'
            '<div class="row"><span class="tg"></span>'
            '<a class="node" href="#t%s"><i>%s</i>%s%s</a><span class="tail">%s</span></div></li>'
            % (t['lane'], t['num'], esc(','.join(t['blockedby'])), esc(','.join(t['dependents'])),
               t['num'], t['num'], esc(t['title']), who, ''.join(tail)))

def tree_group(key, label, count, children):
    return ('<li class="group" data-node="%s"><div class="row">'
            '<button class="tg" type="button" aria-label="展开或折叠"></button>'
            '<a class="node" href="#%s">%s<i>%d</i></a></div><ul>%s</ul></li>'
            % (key, key, label, count, ''.join(children)))

def tree_leaf(key, label, count=None, cls=''):
    return ('<li class="%s" data-node="%s"><div class="row"><span class="tg"></span>'
            '<a class="node" href="#%s">%s%s</a></div></li>'
            % (cls, key, key, label, '<i>%d</i>' % count if count is not None else ''))

# ---- index tables

COL_NUM   = ('#',    lambda t: t['num'], 'n')
COL_TITLE = ('票',   lambda t: '<a href="#t%s">%s</a>' % (t['num'], esc(t['title'])), 't')
COL_STATE = ('状态', lambda t: chip(t['lane'], LANE_LABEL[t['lane']]), 'c')
COL_KIND  = ('类型', lambda t: chip('kind', t['kind']) + (chip('loop', t['loop']) if t['loop'] else ''), 'c')
COL_DEPS  = ('依赖', lambda t: deps(t), 'd')
COL_Q     = ('问题', lambda t: first_sentence(t['question']), 'q')
COL_WHO   = ('认领于', lambda t: esc(claimed_short(t)) if t['claimed'] else '', 'w')
COL_DEC   = ('结论', lambda t: _inline(t['decision']) if t['decision']
                     else '<span class="nodec">地图里还没记这条</span>', 'q')

def table(rows, cols):
    if not rows:
        return ''
    h = ['<div class="tw"><table class="idx"><thead><tr>']
    h += ['<th>%s</th>' % c[0] for c in cols]
    h.append('</tr></thead><tbody>')
    for t in rows:
        h.append('<tr data-go="t%s" class="is-%s">' % (t['num'], t['lane']))
        h += ['<td class="%s">%s</td>' % (c[2], c[1](t)) for c in cols]
        h.append('</tr>')
    h.append('</tbody></table></div>')
    return ''.join(h)

def view_group(key, rows, cols, count_note, empty=''):
    label, note = GROUPS[key]
    return ('<section class="view" data-view="%s" hidden><div class="sechead"><h2>%s</h2><em>%s</em></div>'
            '<p class="secnote">%s</p>%s</section>'
            % (key, label, count_note, md(note)[3:-4],
               table(rows, cols) if rows else '<p class="secnote">%s</p>' % empty))

# ---- ticket view

def view_ticket(t):
    B = ['<section class="view" data-view="t%s" hidden><article class="card is-%s">' % (t['num'], t['lane'])]
    B.append('<div class="chead"><span class="cnum">%s</span>'
             '<h3 class="ctitle">%s</h3></div>' % (t['num'], esc(t['title'])))
    B.append('<div class="chips">' + chip(t['lane'], LANE_LABEL[t['lane']]) + chip('kind', t['kind'])
             + (chip('loop', t['loop']) if t['loop'] else '') + '</div>')
    B.append('<p class="cpath"><button type="button" class="copy" data-copy="%s" title="点击复制路径">'
             '<code>%s</code><span class="cp">复制</span></button></p>'
             % (esc(t['relpath']), esc(t['relpath'])))
    if t['status'] == 'resolved':
        B.append('<p class="decision">%s</p>' % (
            _inline(t['decision']) if t['decision']
            else '<span class="nodec">地图 Decisions so far 里还没记这张票的结论</span>'))
    d = deps(t)
    if d:
        B.append('<p class="waitfor">%s</p>' % d)
    B.append('<div class="cbody">%s</div>' % md(t['question']))
    if t['claimed']:
        B.append('<p class="assignee">认领于 %s%s</p>' % (
            esc(t['claimed_on'] or '？'),
            (' · ' + esc(t['claimed_note'])) if t['claimed_note'] else ''))
    if t['answer']:
        B.append('<details class="answer"><summary>答案</summary>'
                 '<div class="cbody">%s</div></details>' % md(t['answer']))
    B.append('</article></section>')
    return ''.join(B)

def build(effort):
    title, ms, tickets = load(effort)
    by = {k: [t for t in tickets if t['lane'] == k] for k in LANE_LABEL}
    claimed = by['claimed']
    open_ = by['frontier'] + by['blocked']            # frontier first, blocked sink
    unresolved = claimed + open_
    resolved = by['resolved']
    fog = ms.get('Not yet specified', '')
    oos = ms.get('Out of scope', '')
    nfog = len(re.findall(r'^\s*-\s', fog, re.M))
    noos = len(re.findall(r'^\s*-\s', oos, re.M))
    effort_name = os.path.basename(os.path.abspath(effort))

    B = []
    B.append('<div class="wrap">')

    # masthead
    B.append('<header class="top">')
    B.append('<p class="eyebrow">wayfinder:map · %s</p>' % esc(effort_name))
    B.append('<h1>%s</h1>' % esc(title))
    B.append('<p class="sub">%d 张决策票 · 未解决 <b>%d</b>（认领 %d · 未认领 %d，其中 %d 张被挡）'
             '· 已解决 <b>%d</b> · 迷雾 %d · 出界 %d</p>'
             % (len(tickets), len(unresolved), len(claimed), len(open_), len(by['blocked']),
                len(resolved), nfog, noos))
    B.append('</header>')

    B.append('<div class="cols">')

    # tree
    B.append('<nav class="tree" id="tree" aria-label="地图目录"><ul>')
    B.append(tree_leaf('map', '地图', cls='leaf-map'))
    B.append('<li class="rel-controls" aria-label="关系条显示">'
             '<label><input type="checkbox" id="toggle-predecessors" checked>前置</label>'
             '<label><input type="checkbox" id="toggle-dependents" checked>后续</label></li>')
    B.append(tree_group('unresolved', '未解决', len(unresolved), [
        tree_group('claimed', '认领', len(claimed), [tree_ticket(t) for t in claimed]),
        tree_group('open', '未认领', len(open_), [tree_ticket(t) for t in open_]),
    ]))
    B.append(tree_group('resolved', '已解决', len(resolved), [tree_ticket(t) for t in resolved]))
    B.append(tree_leaf('fog', '迷雾', nfog, cls='leaf-map'))
    B.append(tree_leaf('out', '出界', noos, cls='leaf-map'))
    B.append('</ul></nav>')

    # views
    B.append('<main id="main">')
    B.append('<section class="view" data-view="map" hidden>'
             '<div class="block"><div class="sechead"><h2>Destination</h2></div>'
             '<p class="secnote">终点是一份可交付的 spec，不是实现。</p>'
             '<div class="notes">%s</div></div>'
             '<div class="block"><div class="sechead"><h2>贯穿约束</h2></div>'
             '<p class="secnote">地图 Notes 段：每个 session 开工前都要读的领域前提和 standing 约定。'
             '这些是画图时定死的，不重开。</p>'
             '<div class="notes">%s</div></div></section>'
             % (md(ms.get('Destination', '')), md(ms.get('Notes', ''))))

    B.append(view_group('unresolved', unresolved,
                        [COL_NUM, COL_TITLE, COL_STATE, COL_KIND, COL_DEPS, COL_Q],
                        '%d · 认领 %d · 未认领 %d' % (len(unresolved), len(claimed), len(open_)),
                        '一张都没有了。'))
    B.append(view_group('claimed', claimed,
                        [COL_NUM, COL_TITLE, COL_WHO, COL_KIND, COL_DEPS, COL_Q],
                        '%d' % len(claimed), '现在没人在解。'))
    B.append(view_group('open', open_,
                        [COL_NUM, COL_TITLE, COL_KIND, COL_DEPS, COL_Q],
                        '%d · 其中 %d 张被挡' % (len(open_), len(by['blocked'])) if by['blocked']
                        else '%d' % len(open_),
                        '没有待认领的票。'))
    B.append(view_group('resolved', resolved,
                        [COL_NUM, COL_TITLE, COL_WHO, COL_DEPS, COL_DEC],
                        '%d' % len(resolved), '还没有解决的票。'))
    for t in tickets:
        B.append(view_ticket(t))

    B.append('<section class="view" data-view="fog" hidden><div class="sechead"><h2>迷雾</h2><em>%d</em></div>' % nfog)
    B.append('<p class="secnote">在范围内、朝着终点，但还不能精确表述成一个问题，所以还开不了票。'
             '判据是「能不能把问题说清楚」，不是「能不能答上来」。前沿推进会让它逐块毕业成票。</p>')
    B.append('<div class="fog">%s</div></section>' % md(fog))

    B.append('<section class="view" data-view="out" hidden><div class="sechead"><h2>出界</h2><em>%d</em></div>' % noos)
    B.append('<p class="secnote">已经判定在终点之外的事。它不是雾：雾会毕业，出界不会。'
             '除非重画终点，那时是另起一个 effort，不是接着走。</p>')
    B.append('<div class="fog out">%s</div></section>' % md(oos))

    B.append('</main></div>')
    B.append('<footer><span>生成于 %s</span><span>%s</span>'
             '<span>数据源 map.md + issues/*.md</span></footer>'
             % (datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
                esc(os.path.abspath(effort))))
    B.append('</div>')
    B.append('<script>' + JS + '</script>')

    head = (
        '<!doctype html>\n<html lang="zh-CN">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        '<title>' + esc(title) + ' · 决策地图</title>\n'
        '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
        'family=Archivo:wght@400;600;700&family=IBM+Plex+Mono:wght@400;600&'
        'family=IBM+Plex+Sans:wght@400;500;600&display=swap">\n'
        '<style>' + CSS + '</style>\n</head>\n<body data-effort="' + esc(effort_name) + '">\n')
    page = head + '\n'.join(B) + '\n</body>\n</html>\n'
    return page, tickets, by


ERRPAGE = ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
           '<title>读不出地图</title><style>body{font:15px/1.7 ui-monospace,'
           'monospace;max-width:70ch;margin:12vh auto;padding:0 24px;'
           'color:#8a2f2f;background:#fdf7f6}h1{font-size:18px}'
           'pre{white-space:pre-wrap;color:#4a3a38;background:#f5eceb;'
           'padding:14px;border-radius:6px}</style></head><body>'
           '<h1>读不出这个 effort</h1><pre>%s</pre>'
           '<p>改好文件后按 F5。</p></body></html>')


def serve(effort, port):
    import http.server
    effort = os.path.abspath(effort)

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path not in ('/', '/index.html'):
                self.send_error(404); return
            try:
                body = build(effort)[0]
                code = 200
            except Exception as exc:
                import traceback
                body = ERRPAGE % html.escape(traceback.format_exc())
                code = 500
            raw = body.encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(('127.0.0.1', port), Handler)
    print('地图看板  http://127.0.0.1:%d' % port)
    print('  %s' % effort)
    print('  每次刷新都重读文件，Ctrl-C 停止')
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print()


def main(argv):
    if '-h' in argv or '--help' in argv:
        print(__doc__); return 0
    def opt(flag, default=None):
        return argv[argv.index(flag) + 1] if flag in argv else default
    positional = []
    skip = False
    for j, a in enumerate(argv):
        if skip:
            skip = False; continue
        if a in ('-o', '--port'):
            skip = True; continue
        if a.startswith('-'):
            continue
        positional.append(a)
    effort = positional[0] if positional else '.'
    if not os.path.isfile(os.path.join(effort, 'map.md')):
        sys.stderr.write('%s 下没有 map.md\n' % os.path.abspath(effort))
        return 1
    if '--serve' in argv:
        serve(effort, int(opt('--port', 8765)))
        return 0
    out = opt('-o', 'board.html')
    page, tk, by = build(effort)
    with open(out, 'w', encoding='utf-8') as f:
        f.write(page)
    print('%s  <-  %d 张票  (%s)' % (out, len(tk),
          ', '.join('%s %d' % (k, len(v)) for k, v in by.items() if v)))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
