"""compare 共存研究:读 coexist_fetch.py 的产物和只读导出的标注(annotation_state_readonly.json),回答:
1. 一只股票上 plateau 实例按「同起点」「同起点+同阶跃」「同阶跃起点」各折成几族、每族几个实例、同一天最多几个;
2. 每个样本日:当天有几个 plateau 实例(截到当天的)、几个进 hit、属于几族、没进 hit 的卡在哪些 where;
3. 每个「站上新平台」框:框终点那天有几个实例、实例起点离框起点几根、实例的阶跃落不落在框里。"""
import json
from collections import defaultdict
from pathlib import Path

D = Path(__file__).parent
raw = (D / 'annotation_state_readonly.json').read_text()
ann = json.loads(json.loads(raw) if raw.startswith('"') else raw)
FEAT = {f['id']: f['name'] for f in ann['features']}

for chart in ann['charts']:
    sym = chart['symbol']
    d = json.loads((D / f'coexist_{sym}.json').read_text())
    dates = d['dates']; idx = {x: i for i, x in enumerate(dates)}
    ev = {e['instance_id']: e for e in d['events']}
    pl = [e for e in d['events'] if e['node_id'] == 'plateau']
    hitpl = {h['plateau'] for h in d['hits']}
    step_of = lambda e: ev[e['child_refs']['step'][0]]
    fam_s = defaultdict(list); fam_ss = defaultdict(list); fam_step0 = defaultdict(list)
    for e in pl:
        st = step_of(e)
        fam_s[e['start_idx']].append(e)
        fam_ss[(e['start_idx'], st['instance_id'])].append(e)
        fam_step0[st['start_idx']].append(e)
    per_day = defaultdict(int)
    for e in pl: per_day[e['end_idx']] += 1
    hit_fam_s = {k for k, v in fam_s.items() if any(x['instance_id'] in hitpl for x in v)}
    print(f"== {sym}: plateau {len(pl)} 个实例, hit {len(d['hits'])};"
          f" 族数 同起点={len(fam_s)} 同起点+同阶跃={len(fam_ss)} 同阶跃起点={len(fam_step0)};"
          f" 有 hit 的同起点族={len(hit_fam_s)}; 同一天最多 {max(per_day.values())} 个实例")
    big = sorted(fam_s.items(), key=lambda kv: -len(kv[1]))[:4]
    for s, v in big:
        steps = sorted({step_of(x)['instance_id'] for x in v})
        nh = sum(x['instance_id'] in hitpl for x in v)
        print(f"   同起点族 {dates[s]}: {len(v)} 实例, 终点 {dates[min(x['end_idx'] for x in v)]}..{dates[max(x['end_idx'] for x in v)]},"
              f" 阶跃前缀 {len(steps)} 个, 进 hit {nh}")
    for b in chart['boxes']:
        if FEAT.get(b['feature']) != '站上新平台': continue
        bs, be = idx.get(b['start']), idx.get(b['end'])
        at = [e for e in pl if e['end_idx'] == be]
        info = []
        for e in at:
            st = step_of(e)
            info.append(f"起点{dates[e['start_idx']]}(差{e['start_idx']-bs:+d}) 阶跃{dates[st['start_idx']]}..{dates[st['end_idx']]}"
                        f"{'在框内' if bs <= st['start_idx'] and st['end_idx'] <= be else '不在框内'}"
                        f" {'in_hit' if e['instance_id'] in hitpl else 'detected'}")
        print(f"   框 {b['id']} {b['start']}..{b['end']}: 终点当天 {len(at)} 个实例 {info}")
    for s in chart['samples']:
        if s.get('pattern') != 'new_step': continue
        t = idx[s['date']]
        at = [e for e in pl if e['end_idx'] == t]
        nh = [e for e in at if e['instance_id'] in hitpl]
        fails = defaultdict(int)
        for e in at:
            if e['instance_id'] in hitpl: continue
            for k, ok in d['clauses'].get(e['instance_id'], {}).items():
                if not ok: fails[k] += 1
        fams = {e['start_idx'] for e in at}
        steps = {step_of(e)['instance_id'] for e in at}
        print(f"   样本 {s['date']}: 当天实例 {len(at)} 个(同起点族 {len(fams)}、阶跃前缀 {len(steps)}),进 hit {len(nh)};"
              f" 没进 hit 的卡在 {dict(fails)}")
