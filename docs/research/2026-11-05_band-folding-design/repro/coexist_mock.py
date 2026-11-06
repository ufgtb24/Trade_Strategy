"""compare 共存方案草图(第三版):CRNC 真实 new_step 结果,折叠按 fold-rules(同 node、同起点;先按档位筛再折),
族行画法按 fold-interaction(细公共线 + 每个成员在终点那天一格,格高 + 深浅分档;当前日竖线在格子下层),
加上标注层(bracket 的 user 行、框轨插在它 map 到的 band 正上方、unmapped 轨)与「聚焦样本 a」。
只示意,不是界面实现;in_hit 一律画中蓝(真实界面是各 node 本色,且建议本色改中等深度)。
数据:coexist_CRNC.json、annotation_state_readonly.json;收盘价只读地取后端 /ohlc。输出 ../images/c10_mock_compare_CRNC.png。"""
import json, urllib.request
from collections import defaultdict
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.patches import Rectangle, Polygon

D = Path(__file__).parent
fm.fontManager.addfont('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
plt.rcParams['font.family'] = ['Noto Sans CJK JP']
MONO = 'DejaVu Sans Mono'
INK, AMBER, CHIP, LINE = '#111111', '#F2C25C', '#f4f4f5', '#e4e4e7'
HIT, QUAL, DET, SEL_C = '#1a80ba', '#9ca3af', '#d1d5db', '#1e293b'
H = {'in_hit': 0.8, 'qualified': 0.52, 'detected': 0.32}      # fold-interaction:1.0 / 0.65 / 0.4 (×行高 0.8)

d = json.loads((D / 'coexist_CRNC.json').read_text())
raw = (D / 'annotation_state_readonly.json').read_text()
ann = json.loads(json.loads(raw) if raw.startswith('"') else raw)
chart = next(c for c in ann['charts'] if c['symbol'] == 'CRNC')
dates = d['dates']; idx = {x: i for i, x in enumerate(dates)}
bars = json.load(urllib.request.urlopen('http://localhost:8001/ohlc?symbol=CRNC'))['bars']
close = [b['c'] for b in bars]
ev = {e['instance_id']: e for e in d['events']}
hitpl = {h['plateau'] for h in d['hits']}
X0, X1 = idx['2024-09-03'], idx['2025-01-31']
SEL = idx['2024-11-29']                     # 聚焦样本 a
# 每个 event 的档位:plateau 进 hit = in_hit;子结构 event 被某个进 hit 的 plateau 引用 = in_hit;其余 detected
inhit = set(hitpl)
for pid in hitpl:
    for ids in ev[pid]['child_refs'].values():
        inhit.update(ids)
tier = lambda e: 'in_hit' if e['instance_id'] in inhit else 'detected'
# 聚焦:样本日那天 plateau 成员里最深的、同档起点最晚的 → 配对的那一格;它和它的子事件联动亮
day_pl = [e for e in d['events'] if e['node_id'] == 'plateau' and e['end_idx'] == SEL]
pair = max(day_pl, key=lambda e: (tier(e) == 'in_hit', e['start_idx'], -ev[e['child_refs']['step'][0]]['end_idx']))
linked = {pair['instance_id']} | {i for ids in pair['child_refs'].values() for i in ids}
present = {e['instance_id'] for e in day_pl}


def pack(spans):
    ends, rows = [], []
    for s, e in spans:
        for i, x in enumerate(ends):
            if x < s:
                ends[i] = e; rows.append(i); break
        else:
            ends.append(e); rows.append(len(ends) - 1)
    return rows


def families(node):
    fam = defaultdict(list)
    for e in d['events']:
        if e['node_id'] == node and e['end_idx'] >= X0 and e['start_idx'] <= X1:
            fam[e['start_idx']].append(e)
    fams = sorted(fam.items())
    return fams, pack([(s, max(x['end_idx'] for x in v)) for s, v in fams])


fig = plt.figure(figsize=(22, 13), dpi=110)
ax = fig.add_axes([0.12, 0.03, 0.86, 0.94])
ax.set_xlim(X0 - 0.5, X1 + 0.5); ax.axis('off')
y = 0.0
vline_spans = []                       # 当前日竖线只画在 bracket 与副图里


def title(yc, text, mono=False, chip=False, color=INK, size=11):
    kw = dict(fontsize=size, va='center', ha='right', color=color)
    if mono: kw['family'] = MONO
    if chip: kw['bbox'] = dict(boxstyle='round,pad=0.25', fc=CHIP, ec='none')
    ax.text(X0 - 1.6, yc, text, **kw)


def sep():
    ax.plot([X0 - 0.5, X1 + 0.5], [y, y], color=LINE, lw=1)


# —— 主图:收盘价示意 + ▲
top_h = 8
cl = close[X0:X1 + 1]; lo, hi = min(cl), max(cl)
ys = [y + top_h - (c - lo) / (hi - lo) * (top_h - 1) - 0.5 for c in cl]
ax.plot(range(X0, X1 + 1), ys, color='#555555', lw=1.2)
title(y + top_h / 2, 'K 线(示意)')
for s in chart['samples']:
    t = idx[s['date']]; yy = ys[t - X0] + 0.9
    ax.add_patch(Polygon([[t - 0.6, yy + 0.5], [t + 0.6, yy + 0.5], [t, yy - 0.3]], closed=True, fc=INK, ec=INK,
                         lw=2.5 if t == SEL else 1))
ax.add_patch(Rectangle((SEL + 0.5, 0), X1 - SEL, top_h, fc='black', alpha=0.06, lw=0))   # annotate 现有:K 线区样本日之后暗一档
ax.text(X1 - 0.5, 0.4, 'after sample date', fontsize=8, family=MONO, ha='right', va='top', color=INK,
        bbox=dict(boxstyle='square,pad=0.2', fc='white', ec='#9ca3af', lw=0.8))
ax.text(X1 - 0.5, 1.15, '(悬停才出现)', fontsize=8, ha='right', va='top', color=INK)
ax.plot([SEL, SEL], [0, top_h], color=SEL_C, lw=1.0, zorder=0)
y += top_h + 0.5; sep(); v0 = y

# —— bracket 轨
y += 0.3
title(y + 0.4, 'bracket', mono=True)
yu = y + 1.1
title(yu, 'user', mono=True, size=9)
span0 = min(idx[b['start']] for b in chart['boxes'])
ax.plot([max(span0, X0), idx['2024-12-13']], [yu + 0.25, yu + 0.25], ls=(0, (5, 3)), color=INK, lw=2.4)
ax.text(X0 + 0.1, yu + 0.25, '<', fontsize=10, family=MONO, va='center')
for s, letter in zip(chart['samples'], 'abc'):
    t = idx[s['date']]
    ax.add_patch(Polygon([[t - 0.8, yu + 0.5], [t + 0.8, yu + 0.5], [t, yu - 0.45]], closed=True, fc=INK, ec=INK,
                         lw=2.5 if t == SEL else 1))
    ax.text(t + 1.0, yu - 0.1, letter + ' ✓', fontsize=10, family=MONO, fontweight='bold' if t == SEL else 'normal')
y = yu + 0.8
hfams = []
for s, v in families('plateau')[0]:
    hd = sorted({x['end_idx'] for x in v if x['instance_id'] in hitpl})
    if hd: hfams.append((s, hd))
hrows = pack([(s, hd[-1]) for s, hd in hfams])
title(y + 0.5 * (max(hrows) + 1), 'app', mono=True, size=9)
for (s, hd), r in zip(hfams, hrows):
    yy = y + 0.2 + r * 0.95
    if len(hd) == 1:
        ax.add_patch(Rectangle((s - 0.5, yy), hd[0] - s + 1, 0.7, fc=AMBER, ec=INK, lw=0.8))
    else:
        ax.plot([s - 0.5, hd[-1] + 0.5], [yy + 0.7, yy + 0.7], color='#6b7280', lw=0.8)
    for t in hd:
        if len(hd) > 1:
            ax.add_patch(Rectangle((t - 0.45, yy), 0.9, 0.7, fc=AMBER, ec=INK, lw=0.5))
        ax.add_patch(Polygon([[t - 0.4, yy + 0.1], [t + 0.4, yy + 0.1], [t, yy + 0.6]], closed=True, fc=INK,
                             ec=INK, lw=0.5))
        if t == SEL:
            ax.add_patch(Rectangle((t - 0.7, yy - 0.08), 1.4, 0.86, fc='none', ec=SEL_C, lw=2.4))
y += 0.2 + (max(hrows) + 1) * 0.95 + 0.2; sep()

# —— 用户独有:底部平稳(按 annotate 的轨序在上)
y += 0.3
b2 = next(b for b in chart['boxes'] if b['feature'] == 'w-pc-8')
title(y + 0.45, '底部平稳', chip=True)
ax.text(X0 + 0.4, y + 0.45, 'unmapped', fontsize=9, family=MONO, va='center', ha='left', color=INK,
        bbox=dict(boxstyle='square,pad=0.2', fc='white', ec='#1a80ba', lw=1.2))
xs = max(idx[b2['start']], X0)
ax.add_patch(Rectangle((xs - 0.5, y + 0.1), idx[b2['end']] - xs + 1, 0.7, fc='none', ec=INK, lw=1.4, ls=(0, (5, 3))))
ax.text(idx[b2['end']] + 1, y + 0.45, '触底放量 false', fontsize=9, va='center',
        bbox=dict(boxstyle='round,pad=0.2', fc=CHIP, ec='none'))
y += 1.1; sep()

# —— 组:站上新平台 ⇣ plateau,及 plateau 的子 band
g0 = y
y += 0.3
box = next(b for b in chart['boxes'] if b['feature'] == 'w-pc-11')
bs, be = idx[box['start']], idx[box['end']]
title(y + 0.4, '站上新平台', chip=True)
title(y + 1.05, '⇣ plateau', mono=True, size=9)
ax.text(bs - 0.5, y + 1.15, 'start not compared', fontsize=8, family=MONO, va='center', ha='left', color=INK, bbox=dict(boxstyle='square,pad=0.15', fc='white', ec='#9ca3af', lw=0.8))
ax.text(bs + 17, y + 1.15, '(悬停框左端才出现)', fontsize=8, va='center', ha='left', color=INK)
ax.add_patch(Rectangle((bs - 0.5, y + 0.05), be - bs + 1, 0.7, fc='none', ec=INK, lw=2.2, ls=(0, (7, 2))))
ax.text(bs - 1.0, y + 0.4, 'a b c', fontsize=9, family=MONO, va='center', ha='right')
ax.text(be + 1.2, y + 0.4, '平台交界放量 true', fontsize=9, va='center', bbox=dict(boxstyle='round,pad=0.2', fc=CHIP, ec='none'))
ax.text(be + 9.8, y + 0.4, '⇢ step_vol ✓', fontsize=9, family=MONO, va='center')
y += 1.4
for node, label in [('plateau', 'plateau'), ('old_plat', '  old_plat'), ('step', '  step'), ('new_plat', '  new_plat'),
                    ('today', '  today')]:
    fams, rows = families(node)
    nr = max(rows) + 1 if rows else 1
    rh = 1.05
    title(y + nr * rh / 2, label, mono=True)
    for (s, v), r in zip(fams, rows):
        yb = y + 0.1 + r * rh + 0.85           # 行底
        last = max(x['end_idx'] for x in v)
        byday = defaultdict(list)
        for x in v: byday[x['end_idx']].append(x)
        if node == 'today':                     # 点事件:小 ▼,档位靠大小与深浅
            for t, xsm in byday.items():
                if t < X0 or t > X1: continue
                tr = 'in_hit' if any(tier(x) == 'in_hit' for x in xsm) else 'detected'
                h = H[tr]
                ax.add_patch(Polygon([[t - 0.45, yb - h], [t + 0.45, yb - h], [t, yb]], closed=True,
                                     fc=HIT if tr == 'in_hit' else DET, ec='none'))
                if {x['instance_id'] for x in xsm} & linked:
                    ax.add_patch(Rectangle((t - 0.6, yb - 0.9), 1.2, 0.95, fc='none', ec=SEL_C, lw=2.6))
            continue
        multi = len(byday) > 1
        if multi:
            ax.plot([max(s, X0) - 0.5, min(last, X1) + 0.5], [yb, yb], color='#6b7280', lw=0.8)
        for t, xsm in byday.items():
            if t < X0 or t > X1: continue
            tr = 'in_hit' if any(tier(x) == 'in_hit' for x in xsm) else 'detected'
            h = H[tr]
            x0 = (t - 0.42) if multi else (max(s, X0) - 0.5)
            w = 0.84 if multi else (t + 0.5 - x0)
            ax.add_patch(Rectangle((x0, yb - h), w, h, fc=HIT if tr == 'in_hit' else DET, ec='none'))
            if {x['instance_id'] for x in xsm} & linked:     # 和样本配上的那次 hit 用到的格:粗框 + 跨度细框
                ax.add_patch(Rectangle((t - 0.6, yb - 0.9), 1.2, 0.95, fc='none', ec=SEL_C, lw=2.6))
                if s < t:
                    ax.add_patch(Rectangle((s - 0.5, yb - 0.92), t - s + 1, 0.99, fc='none', ec=SEL_C, lw=1.0))
    y += nr * rh + 0.3
ax.plot([X0 - 1.0, X0 - 1.0], [g0 + 0.3, y - 0.2], color=INK, lw=2.2, clip_on=False)
sep()
# 当前日竖线:副图最上层,1px 深色加两侧白边(fold-interaction 定稿)
ax.plot([SEL, SEL], [v0, y], color='white', lw=3.4, zorder=50)
ax.plot([SEL, SEL], [v0, y], color=SEL_C, lw=1.0, zorder=51)
for t in range(X0, X1 + 1):
    if t == X0 or dates[t - 1][5:7] != dates[t][5:7]:
        ax.text(t, y + 0.5, dates[t][:7], fontsize=9, family=MONO, ha='left', va='top')
ax.set_ylim(y + 1.2, -0.5)
out = D.parent / 'images' / 'c10_mock_compare_CRNC.png'
fig.savefig(out); print(out, 'paired:', pair['instance_id'])
