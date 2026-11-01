"""读 scratchpad 里的 turns.jsonl + labels.py，出分类计数、按日分布、选择题作答统计、在场时长估计。"""
import json, sys, collections, re
from datetime import datetime, timedelta
sys.path.insert(0, '/home/yu/PycharmProjects/Trade_Strategy/docs/research/2026-11-01_human-cc-collab-workflow/repro')
from labels import L, ASK_LEVEL
SP = sys.argv[1]
turns = [json.loads(l) for l in open(SP + '/turns.jsonl')] + [json.loads(l) for l in open(SP + '/turns_wt.jsonl')]
def local(ts): return datetime.fromisoformat(ts.replace('Z', '+00:00')) + timedelta(hours=8)
typed = [t for t in turns if t['kind'] not in ('ask_answer', 'ask_reject') and L[t['t']][0] != 'DUP']
asks = [t for t in turns if t['kind'] == 'ask_answer']
rej = [t for t in turns if t['kind'] == 'ask_reject']
cat = collections.Counter(L[t['t']][0] for t in typed)
chars = collections.Counter()
for t in typed: chars[L[t['t']][0]] += len(t['text'])
resend = collections.Counter()
for t in typed: resend[L[t['t']][0]] += t['n_versions'] - 1
print('typed turns (去重后)', len(typed), ' 重发次数合计', sum(t['n_versions'] - 1 for t in typed),
      ' DUP', sum(1 for t in turns if L.get(t['t'], ('',))[0] == 'DUP'))
for c, n in cat.most_common():
    print(f'  {c}: {n} 条  {chars[c]} 字  重发 {resend[c]}')
f = collections.Counter(fl for t in typed for fl in L[t['t']][1])
print('flags', dict(f))
# Q 的对象：粗分（关键词启发式，人工抽查过）
def qobj(t):
    x = t['text']
    if t['n_images'] or re.search(r'tab|标签|页|悬停|band|框|颜色|显示|面板|下拉|groups?|features? 节|缩略图|in [kmn]/|qualified|missing|签', x):
        return '原型界面上的东西'
    if re.search(r"[‘'「]|是啥|什么意思|啥意思|解释", x):
        return 'cc 回复或报告里的说法'
    return '机制 / 谁在什么时候做什么'
qo = collections.Counter(qobj(t) for t in typed if L[t['t']][0] == 'Q')
print('Q 的对象', dict(qo))
print('选择题作答', len(asks), ' 选推荐', sum(t['extra']['picked_recommended'] for t in asks),
      ' 选了别的选项', sum((not t['extra']['picked_recommended']) and (not t['extra']['custom']) for t in asks),
      ' 自己写', sum(t['extra']['custom'] for t in asks), ' 拒答要求先澄清', len(rej))
lv = collections.defaultdict(collections.Counter)
for t in asks:
    e = t['extra']; k = 'rec' if e['picked_recommended'] else ('custom' if e['custom'] else 'other')
    lv[ASK_LEVEL[t['t']]][k] += 1
print('选择题按层级', {k: dict(v) for k, v in lv.items()})
# 按日
byday = collections.defaultdict(collections.Counter)
for t in typed: byday[local(t['ts']).strftime('%m-%d')][L[t['t']][0]] += 1
for t in asks: byday[local(t['ts']).strftime('%m-%d')]['ask'] += 1
order = ['D', 'N', 'X', 'Q', 'T', 'C', 'P', 'A', 'M', 'E', 'O', 'ask']
print('day  ' + ' '.join(f'{c:>3}' for c in order))
for d in sorted(byday):
    print(d, ' '.join(f'{byday[d][c]:>3}' for c in order))
# 在场时长：相邻两条用户输入间隔 < 20 分钟算连续在场
allt = sorted([t for t in turns if L.get(t['t'], ('',))[0] != 'DUP'], key=lambda t: t['ts'])
pres = collections.Counter(); prev = None
for t in allt:
    now = local(t['ts'])
    if prev and (now - prev).total_seconds() < 1200:
        pres[now.strftime('%m-%d')] += (now - prev).total_seconds() / 3600
    prev = now
print('在场小时（间隔<20分）', {d: round(h, 1) for d, h in sorted(pres.items())}, '合计', round(sum(pres.values()), 1))
json.dump({'cat': cat, 'flags': f, 'qobj': qo}, open(SP + '/stats.json', 'w'), ensure_ascii=False)
