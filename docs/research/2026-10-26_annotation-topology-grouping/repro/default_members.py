"""放买点时默认收进哪些框：三种默认规则在几种情形上的对比。

框与买点用 K 线下标，不读任何行情数据。情形 s0 / s1 抄自原型种子
（.scratch/annotation-path2/prototypes/01-annotation/index.html 的 seed()），其余为手造。
每个情形写明「用户本意」的成员，规则的输出与之对比，分开报多收、少收。

规则：
  chain(G)：终点落在买点前 G 天以内或跨过买点的框起头，往左把「终点距成员串起点 ≤ G」的框接上
            （相接、交叠都算），再带上套在成员里的小框。G=2 是框边界画粗的容差，G=20 取自 bb_v1
            允许回踩在末根突破后最多 20 根内开始（tb.max_span），两者都待验证。
  prev_buy：critic 提的「往左收到同一 pattern 的上一个买点为止，没有就到图的左边」。
运行：uv run python docs/research/2026-10-26_annotation-topology-grouping/repro/default_members.py
"""

CASES = {
    # 名称, 起, 止；buys: (买点, 用户本意的成员名单)
    's0 种子（用户截图那张）': {
        'boxes': [('横盘', 135, 158), ('缩量', 140, 146), ('放量突破', 159, 164),
                  ('回踩', 164, 167), ('放量突破@80', 80, 82)],
        'buys': [(84, {'放量突破@80'}), (167, {'横盘', '缩量', '放量突破', '回踩'})],
    },
    's1 种子（左边横盘隔 53 根）': {
        'boxes': [('横盘', 98, 106), ('放量突破', 159, 165), ('回踩', 165, 167)],
        'buys': [(166, {'放量突破', '回踩'})],
    },
    '突破后先涨 6 天再回踩（中间没框）': {
        'boxes': [('横盘', 100, 130), ('放量突破', 131, 134), ('回踩', 141, 146)],
        'buys': [(146, {'横盘', '放量突破', '回踩'})],
    },
    '共用前段、各有后段（两次回踩各买一次）': {
        'boxes': [('横盘', 100, 130), ('放量突破', 131, 134), ('回踩1', 138, 142), ('回踩2', 150, 154)],
        'buys': [(142, {'横盘', '放量突破', '回踩1'}), (154, {'横盘', '放量突破', '回踩2'})],
    },
    '左边孤立框没有买点（截图里的说法）': {
        'boxes': [('放量突破@80', 80, 82), ('横盘', 135, 158), ('放量突破', 159, 164), ('回踩', 164, 167)],
        'buys': [(167, {'横盘', '放量突破', '回踩'})],
    },
    '下跌后隔 25 天才进底部': {
        'boxes': [('下跌', 60, 90), ('底部', 115, 140), ('放量突破', 141, 143), ('回踩', 146, 150)],
        'buys': [(150, {'下跌', '底部', '放量突破', '回踩'})],
    },
}


def nested_closure(boxes, members, tol=2):
    for i, (_, s, e) in enumerate(boxes):
        if i not in members and any(boxes[m][1] - tol <= s and e <= boxes[m][2] + tol
                                    and (boxes[m][2] - boxes[m][1]) > (e - s) for m in members):
            members.add(i)
    return members


def chain(boxes, buy, buys, G):
    members = {i for i, (_, s, e) in enumerate(boxes) if buy - G <= e and s <= buy}
    changed = True
    while changed and members:
        changed = False
        first = min(boxes[i][1] for i in members)
        for i, (_, s, e) in enumerate(boxes):
            if i not in members and s < first and e >= first - G:
                members.add(i)
                changed = True
    return nested_closure(boxes, members)


def prev_buy(boxes, buy, buys, G=None):
    left = max([b for b, _ in buys if b < buy], default=-1)
    return nested_closure(boxes, {i for i, (_, s, e) in enumerate(boxes) if e > left and s <= buy})


RULES = {'chain(G=2)': lambda b, y, ys: chain(b, y, ys, 2),
         'chain(G=10)': lambda b, y, ys: chain(b, y, ys, 10),
         'chain(G=20)': lambda b, y, ys: chain(b, y, ys, 20),
         'prev_buy': prev_buy}

tot = {r: [0, 0] for r in RULES}
for case, c in CASES.items():
    print(f'## {case}')
    for buy, want in c['buys']:
        for r, f in RULES.items():
            got = {c['boxes'][i][0] for i in f(c['boxes'], buy, c['buys'])}
            over, under = sorted(got - want), sorted(want - got)
            tot[r][0] += len(over)
            tot[r][1] += len(under)
            flag = '' if not over and not under else f'  多收{over} 少收{under}'
            print(f'  买点@{buy} {r:12s}{"对" if not flag else ""}{flag}')
print('## 合计（框数）')
for r, (o, u) in tot.items():
    print(f'  {r:12s} 多收 {o}  少收 {u}')
