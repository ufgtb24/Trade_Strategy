"""compare 共存研究补充:折叠后 band 要几行、tier tag 的碰巧率、属性「平台交界放量」与 step_vol 的对照、match 的精确日与 ±3 天。
读 coexist_<SYM>.json 与 annotation_state_readonly.json(只读)。"""
import json
from collections import defaultdict
from pathlib import Path

D = Path(__file__).parent
raw = (D / 'annotation_state_readonly.json').read_text()
ann = json.loads(json.loads(raw) if raw.startswith('"') else raw)
FEAT = {f['id']: f['name'] for f in ann['features']}


def lanes_needed(spans):
    """区间按起点排序贪心分行(同主视图 packLanes 的思路),返回行数。"""
    ends = []
    for s, e in sorted(spans):
        for i, x in enumerate(ends):
            if x < s:
                ends[i] = e; break
        else:
            ends.append(e)
    return len(ends)


def lab_l(hexc):
    h = hexc.lstrip('#'); r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    lin = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    y = 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
    return round(116 * (y ** (1 / 3) if y > 0.008856 else 7.787 * y + 16 / 116) - 16)


print('L* 明度:', {c: lab_l(c) for c in ['#16f943', '#14b24e', '#FF1500', '#7c3aed', '#2563eb', '#F2C25C', '#d1d5db', '#9ca3af', '#1a80ba']})
tot = defaultdict(int)
for chart in ann['charts']:
    sym = chart['symbol']
    d = json.loads((D / f'coexist_{sym}.json').read_text())
    dates = d['dates']; idx = {x: i for i, x in enumerate(dates)}; n = len(dates)
    ev = {e['instance_id']: e for e in d['events']}
    pl = [e for e in d['events'] if e['node_id'] == 'plateau']
    hitpl = {h['plateau'] for h in d['hits']}
    step_of = lambda e: ev[e['child_refs']['step'][0]]
    fam_s = defaultdict(list); fam_ss = defaultdict(list)
    for e in pl:
        fam_s[e['start_idx']].append(e); fam_ss[(e['start_idx'], step_of(e)['instance_id'])].append(e)
    span = lambda v: (min(x['start_idx'] for x in v), max(x['end_idx'] for x in v))
    rows_raw = lanes_needed([(e['start_idx'], e['end_idx']) for e in pl])
    rows_s = lanes_needed([span(v) for v in fam_s.values()])
    rows_ss = lanes_needed([span(v) for v in fam_ss.values()])
    hit_fams = [v for v in fam_s.values() if any(x['instance_id'] in hitpl for x in v)]
    rows_s_hit = lanes_needed([span(v) for v in hit_fams])
    # 碰巧率:任一天有实例 / 有 in_hit 实例;在「有 hit 的族」跨过的天里有 in_hit 的比例
    day_any = {e['end_idx'] for e in pl}; day_hit = {e['end_idx'] for e in pl if e['instance_id'] in hitpl}
    fam_days = set()
    for v in hit_fams:
        fam_days |= {x['end_idx'] for x in v}
    print(f"== {sym}: 行数 不折={rows_raw} 同起点折={rows_s} 同起点+前缀折={rows_s_hit and rows_ss} 只留有hit的族={rows_s_hit};"
          f" 有实例的天 {len(day_any)}/{n}={len(day_any)/n:.0%}, 有in_hit的天 {len(day_hit)}/{n}={len(day_hit)/n:.0%},"
          f" 有hit的族的天里 in_hit {len(day_hit & fam_days)}/{len(fam_days)}={len(day_hit & fam_days)/max(1,len(fam_days)):.0%}")
    # 属性:框上的平台交界放量 vs 框终点那天成员的 step_vol(取档位最高者;同档取阶跃最晚的)
    for b in chart['boxes']:
        if FEAT.get(b['feature']) != '站上新平台': continue
        be = idx[b['end']]
        at = [e for e in pl if e['end_idx'] == be]
        at.sort(key=lambda e: (e['instance_id'] in hitpl, step_of(e)['start_idx']), reverse=True)
        top = at[0] if at else None
        sv = d['clauses'].get(top['instance_id'], {}).get('step_vol') if top else None
        allv = [d['clauses'].get(e['instance_id'], {}).get('step_vol') for e in at]
        print(f"   框 {b['id']} 平台交界放量={b.get('attrs', {}).get('w-pc-26')}  框终点成员(最高档) step_vol={sv}  当天全部成员 step_vol={allv}")
    # match:样本日当天有 in_hit 的实例 / ±3 天内有
    for s in chart['samples']:
        if s.get('pattern') != 'new_step': continue
        t = idx[s['date']]
        exact = t in day_hit
        near = sorted(x - t for x in day_hit if abs(x - t) <= 3)
        print(f"   样本 {s['date']}: 当天 in_hit={exact}; ±3 天内 in_hit 的偏移 {near}")
        tot['exact'] += exact; tot['near'] += bool(near); tot['n'] += 1
print('合计', dict(tot))
