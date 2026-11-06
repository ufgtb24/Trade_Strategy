"""compare 共存研究:只读地从运行中的后端(8001)取 new_step 在 6 只标注股票上的整段结果与诊断,存 JSON。
只发 GET(/ohlc、/preview、/diagnose),不写标注、不碰进程。输出 repro/coexist_<SYM>.json。"""
import json, sys, urllib.request, urllib.parse
from pathlib import Path

BASE = 'http://localhost:8001'
OUT = Path(__file__).parent
SYMS = ['CRNC', 'GEVO', 'INDO', 'QBTS', 'RGTI', 'SMX']
START, END = '1900-01-01', '2025-12-31'


def get(path, **q):
    url = f"{BASE}{path}?{urllib.parse.urlencode(q)}"
    with urllib.request.urlopen(url, timeout=600) as r:
        return json.load(r)


for sym in (sys.argv[1:] or SYMS):
    bars = get('/ohlc', symbol=sym)['bars']
    dates = [b['date'] for b in bars]
    pv = get('/preview', pattern_id='new_step', symbol=sym, start=START, end=END, label_horizon=20)
    dg = get('/diagnose', pattern_id='new_step', symbol=sym, start=START, end=END)
    an = pv['analysis']
    # 诊断:plateau 每个实例的 where 结果(只留 satisfied)
    clauses = {}
    for row in dg['nodes']['plateau']['attr']:
        clauses[row['instance_id']] = {k: v['satisfied'] for k, v in row['clauses'].items()}
    evs = [{k: e[k] for k in ('instance_id', 'node_id', 'start_idx', 'end_idx', 'child_refs') if k in e}
           for e in an['events']]
    hits = [{'hit_id': h['hit_id'], 'start_idx': h['start_idx'], 'end_idx': h['end_idx'],
             'plateau': h['node_index'].get('plateau'), 'buy_date': h.get('buy_date')} for h in an['hits']]
    (OUT / f'coexist_{sym}.json').write_text(json.dumps(
        {'symbol': sym, 'dates': dates, 'events': evs, 'hits': hits, 'clauses': clauses}, ensure_ascii=False))
    print(sym, len(dates), 'bars', len(evs), 'events', len(hits), 'hits')
