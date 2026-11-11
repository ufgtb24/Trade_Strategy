// 「复制指代」的纯逻辑:当前指的是哪样东西(resolveTarget)、各层写成什么行(copyLadder)。
import { describe, it, expect } from 'vitest'
import { copyLadder, resolveTarget, type CopyContext, type PickState } from '../src/annotate/copyRef'
import type { EventDict, HitDict } from '../src/types'

const none: PickState = { lastPick: null, feedbackId: null, node: null, candidateCount: 0, pendingInstanceId: null,
  familyKind: null, instanceId: null, hitId: null, boxId: null, sampleId: null }
const pick = (o: Partial<PickState>) => resolveTarget({ ...none, ...o })

describe('resolveTarget · 选框、选样本会顺带点亮配对的 hit,不能只看谁非空', () => {
  it('什么都没选中 → 当前日', () => {
    expect(pick({})).toEqual({ kind: 'day' })
  })
  it('选框(配对的 hit 也亮着、没有当家行)→ 框', () => {
    expect(pick({ boxId: 'b1', hitId: 'h1' })).toEqual({ kind: 'box', id: 'b1' })
  })
  it('选样本(当家行是样本行、配对的 hit 也亮着)→ 样本;compare 下只是聚焦的也算', () => {
    expect(pick({ sampleId: 's1', hitId: 'h1', familyKind: 'external' })).toEqual({ kind: 'sample', id: 's1' })
  })
  it('选过样本后点 ▼(样本还选中着,当家行换成 hits 行)→ hit', () => {
    expect(pick({ sampleId: 's1', hitId: 'h1', familyKind: 'bracket' })).toEqual({ kind: 'hit', hitId: 'h1' })
  })
  it('点 band 上一格(实例与它的 hit 都亮,当家行是 band)→ event', () => {
    expect(pick({ instanceId: 'e1', hitId: 'h1', familyKind: 'band' })).toEqual({ kind: 'event', instanceId: 'e1' })
  })
  it('待选(点了被几次 hit 共用的格,还没定是哪次)→ 点下去的那个 event,不退成当前日', () => {
    expect(pick({ candidateCount: 11, pendingInstanceId: 'step#0', familyKind: 'bracket' }))
      .toEqual({ kind: 'event', instanceId: 'step#0' })
  })
  it('反馈记号的选中一直留着:最后点的是它才算它,之后点了 ▼ 就是 hit', () => {
    expect(pick({ lastPick: 'feedback', feedbackId: 'f1', hitId: 'h1', familyKind: 'bracket' })).toEqual({ kind: 'feedback', id: 'f1' })
    expect(pick({ lastPick: null, feedbackId: 'f1', hitId: 'h1', familyKind: 'bracket' })).toEqual({ kind: 'hit', hitId: 'h1' })
    expect(pick({ lastPick: null, feedbackId: 'f1' })).toEqual({ kind: 'feedback', id: 'f1' })   // 别的都没有时仍是它
  })
  it('在 diagnose 里点卡片(当家行仍是样本行):hits 组的卡片 → 那次 hit,not_in_hit 组的 → 那个 event;只选样本仍是样本', () => {
    const base = { sampleId: 's1', familyKind: 'external' as const }
    expect(pick({ ...base, lastPick: 'card', instanceId: 'P1', hitId: 'h1' })).toEqual({ kind: 'hit', hitId: 'h1' })
    expect(pick({ ...base, lastPick: 'card', instanceId: 'P9' })).toEqual({ kind: 'event', instanceId: 'P9' })
    // 样本配对的 event 不在任何 hit 里时,选样本也会带出实例焦点:没点卡片就还是样本
    expect(pick({ ...base, instanceId: 'P9' })).toEqual({ kind: 'sample', id: 's1' })
  })
  it('点轨名 → node', () => {
    expect(pick({ lastPick: 'node', node: 'step' })).toEqual({ kind: 'node', node: 'step' })
  })
  it('annotate(没有当家行):样本 → 样本', () => {
    expect(pick({ sampleId: 's1' })).toEqual({ kind: 'sample', id: 's1' })
  })
})

// new_step 式:plateau 容器引用 step / today;h0、h1 买在同一天(只差阶跃切法),h2 晚一天
const ev = (node: string, s: number, e: number, idx = 0, child_refs: Record<string, string[]> = {}): EventDict =>
  ({ instance_id: `${node}_${s}_${e}#${idx}`, node_id: node, instance_idx: idx, start_idx: s, end_idx: e, child_refs } as EventDict)
const S1 = ev('step', 1, 1), S2 = ev('step', 1, 2)
const T3 = ev('today', 3, 3), T4 = ev('today', 4, 4)
const P0 = ev('plateau', 0, 3, 0, { step: [S1.instance_id], today: [T3.instance_id] })
const P1 = ev('plateau', 0, 3, 1, { step: [S2.instance_id], today: [T3.instance_id] })
const P2 = ev('plateau', 0, 4, 0, { step: [S1.instance_id], today: [T4.instance_id] })
const hit = (id: string, p: EventDict): HitDict => ({
  hit_id: id, start_idx: p.start_idx, end_idx: p.end_idx, node_index: { plateau: p.instance_id },
  children: [p.instance_id, ...Object.values(p.child_refs ?? {}).flat()],
} as HitDict)

const ctx: CopyContext = {
  symbol: 'AAA', pattern: 'p1', currentDay: 2,
  dates: ['2024-01-01', '2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05'],
  hits: [hit('h0', P0), hit('h1', P1), hit('h2', P2)],
  events: [S1, S2, T3, T4, P0, P1, P2],
  endNode: 'plateau.today', nodeOrder: ['plateau', 'step', 'today'], anchorFields: [],
  chart: { symbol: 'AAA',
    boxes: [{ id: 'b1', feature: 'w1', start: '2024-01-01', end: '2024-01-03' }],
    samples: [{ id: 's1', date: '2024-01-04', pattern: 'p1', judgment: 'pos', members: [] },
              { id: 's0', date: '2024-01-02', pattern: 'p1', judgment: 'neg', members: [] },
              { id: 's9', date: '2024-01-03', pattern: null, judgment: 'pos', members: [] }],
    feedback: [{ id: 'f1', pattern: 'p1', app_id: 'p1', app_ver: 'v', start: '2024-01-04', end: '2024-01-05',
                 target: 'range', source: 'picked', nodes: ['step', 'today'] },
               { id: 'f2', pattern: 'p1', app_id: 'p1', app_ver: 'v', start: '2024-01-04', end: '2024-01-04',
                 target: 'point', source: 'picked' }] },
  featureName: (f) => (f === 'w1' ? '站上新平台' : f),
}

describe('copyLadder · 一行自带上下文,连按逐层放大', () => {
  it('hit:这一次(同一天有几次才写 k/n 与区别)→ 这一天的几次 → 整族', () => {
    const [one, sameDay, family, ...rest] = copyLadder({ kind: 'hit', hitId: 'h1' }, ctx)
    expect(one).toMatch(/^AAA p1 hit 2024-01-01→2024-01-04 2\/2 step→2024-01-03 \[h1\]$/)
    expect(sameDay).toBe('AAA p1 hits buy 2024-01-04 ×2 start 2024-01-01')
    expect(family).toBe('AAA p1 hit_family start 2024-01-01 buys 2024-01-04…2024-01-05')
    expect(rest).toEqual([])
  })
  it('hit:那天只有一次 → 没有「这一天的几次」这一层,不写 k/n', () => {
    expect(copyLadder({ kind: 'hit', hitId: 'h2' }, ctx)).toEqual([
      'AAA p1 hit 2024-01-01→2024-01-05 [h2]',
      'AAA p1 hit_family start 2024-01-01 buys 2024-01-04…2024-01-05',
    ])
  })
  it('hit:族里只有同一天的这几次 → 没有整族这一层', () => {
    const c = { ...ctx, hits: [hit('h0', P0), hit('h1', P1)] }
    expect(copyLadder({ kind: 'hit', hitId: 'h0' }, c)).toHaveLength(2)
  })
  it('event:这一个 → 同 node 同起点的一族;独一个的没有族这一层;点事件只写一天', () => {
    expect(copyLadder({ kind: 'event', instanceId: P0.instance_id }, ctx)).toEqual([
      `AAA p1 event plateau 2024-01-01→2024-01-04 [${P0.instance_id}]`,
      'AAA p1 event_family plateau start 2024-01-01',
    ])
    expect(copyLadder({ kind: 'event', instanceId: T4.instance_id }, ctx))
      .toEqual([`AAA p1 event today 2024-01-05 [${T4.instance_id}]`])
  })
  it('node、框、样本(字母按日期,按它自己的 pattern)、反馈、当前日', () => {
    expect(copyLadder({ kind: 'node', node: 'step' }, ctx)).toEqual(['AAA p1 node step'])
    expect(copyLadder({ kind: 'box', id: 'b1' }, ctx)).toEqual(['AAA box 站上新平台 2024-01-01→2024-01-03 [b1]'])
    expect(copyLadder({ kind: 'sample', id: 's1' }, ctx)).toEqual(['AAA p1 sample b pos 2024-01-04 [s1]'])
    expect(copyLadder({ kind: 'sample', id: 's9' }, ctx)).toEqual(['AAA unsorted sample a pos 2024-01-03 [s9]'])
    expect(copyLadder({ kind: 'feedback', id: 'f1' }, ctx)).toEqual(['AAA p1 feedback 2024-01-04→2024-01-05 nodes step,today [f1]'])
    expect(copyLadder({ kind: 'feedback', id: 'f2' }, ctx)).toEqual(['AAA p1 feedback 2024-01-04 [f2]'])
    expect(copyLadder({ kind: 'day' }, ctx)).toEqual(['AAA p1 day 2024-01-03'])
  })
  it('没有当前日、没有 pattern、对象已不在:退成能写的那一段', () => {
    expect(copyLadder({ kind: 'day' }, { ...ctx, currentDay: null })).toEqual(['AAA p1'])
    expect(copyLadder({ kind: 'day' }, { ...ctx, pattern: null })).toEqual(['AAA day 2024-01-03'])
    expect(copyLadder({ kind: 'box', id: 'gone' }, ctx)).toEqual(['AAA p1 day 2024-01-03'])
  })
})
