// 「复制指代」的纯逻辑:当前指的是哪样东西(resolveTarget)、写成哪一行(copyLine)。
// 按一下复制一行:图上选中了东西就是它(后半行由选中快照给,见 render.sel-snapshot.spec.ts);
// annotate 下没有 app 的东西,选中的框、样本照同一拼法在这里写。
import { describe, it, expect } from 'vitest'
import { copyLine, resolveTarget, type CopyContext, type PickState } from '../src/annotate/copyRef'

const none: PickState = { tail: null, boxId: null, sampleId: null, feedbackId: null }
const pick = (o: Partial<PickState>) => resolveTarget({ ...none, ...o })

describe('resolveTarget · 图上选中的那一个优先;没有时框 → 样本 → 反馈 → 当前日', () => {
  it('什么都没选中 → 当前日', () => {
    expect(pick({})).toEqual({ kind: 'day' })
  })
  it('图上选中了东西 → 就是它(框、样本、反馈还选中着也一样)', () => {
    const tail = 'hit 2024-01-01→2024-01-04 [h1]'
    expect(pick({ tail, sampleId: 's1' })).toEqual({ kind: 'selection', tail })
    expect(pick({ tail, boxId: 'b1', feedbackId: 'f1' })).toEqual({ kind: 'selection', tail })
  })
  it('图上没有选中(annotate 下,或清掉了图上的选中):框 → 样本', () => {
    expect(pick({ boxId: 'b1', sampleId: 's1' })).toEqual({ kind: 'box', id: 'b1' })
    expect(pick({ sampleId: 's1' })).toEqual({ kind: 'sample', id: 's1' })
  })
  it('反馈记号的选中:别的都没有时是它;有框或样本时让给它们', () => {
    expect(pick({ feedbackId: 'f1' })).toEqual({ kind: 'feedback', id: 'f1' })
    expect(pick({ feedbackId: 'f1', sampleId: 's1' })).toEqual({ kind: 'sample', id: 's1' })
    expect(pick({ feedbackId: 'f1', boxId: 'b1' })).toEqual({ kind: 'box', id: 'b1' })
  })
})

const ctx: CopyContext = {
  symbol: 'AAA', pattern: 'p1', currentDay: 2,
  dates: ['2024-01-01', '2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05'],
  chart: { symbol: 'AAA',
    boxes: [{ id: 'b1', feature: 'w1', start: '2024-01-01', end: '2024-01-03' },
            { id: 'b2', feature: null, start: '2024-01-02', end: '2024-01-02' }],
    samples: [{ id: 's1', date: '2024-01-04', pattern: 'p1', judgment: 'pos', members: [] },
              { id: 's0', date: '2024-01-02', pattern: 'p1', judgment: 'neg', members: [] },
              { id: 's9', date: '2024-01-03', pattern: null, judgment: 'pos', members: [] }],
    feedback: [{ id: 'f1', pattern: 'p1', app_id: 'p1', app_ver: 'v', start: '2024-01-04', end: '2024-01-05',
                 target: 'range', source: 'picked', nodes: ['step', 'today'] },
               { id: 'f2', pattern: 'p1', app_id: 'p1', app_ver: 'v', start: '2024-01-04', end: '2024-01-04',
                 target: 'point', source: 'picked' }] },
  featureName: (f) => (f === 'w1' ? '站上新平台' : null),
}

describe('copyLine · 一行:股票、pattern,接种类、node、日期、叫法,末尾方括号里是编号', () => {
  it('图上选中的那一个:股票、pattern 后面接选中快照给的后半行', () => {
    expect(copyLine({ kind: 'selection', tail: 'hit 2024-01-01→2024-01-04 step→2024-01-03 buys 2024-01-04 ×1 [h1]' }, ctx))
      .toBe('AAA p1 hit 2024-01-01→2024-01-04 step→2024-01-03 buys 2024-01-04 ×1 [h1]')
    expect(copyLine({ kind: 'selection', tail: 'node step 阶跃' }, ctx)).toBe('AAA p1 node step 阶跃')
    expect(copyLine({ kind: 'selection', tail: 'buy 2024-01-04 hits ×2' }, { ...ctx, pattern: null })).toBe('AAA buy 2024-01-04 hits ×2')
  })
  it('框:起止在前、特征名在后;没起名的写 unnamed;起止同一天只写一天', () => {
    expect(copyLine({ kind: 'box', id: 'b1' }, ctx)).toBe('AAA p1 box 2024-01-01→2024-01-03 站上新平台 [b1]')
    expect(copyLine({ kind: 'box', id: 'b2' }, ctx)).toBe('AAA p1 box 2024-01-02 unnamed [b2]')
  })
  it('样本:按它自己的 pattern 写(字母按日期排),没归 pattern 的写 unsorted', () => {
    expect(copyLine({ kind: 'sample', id: 's1' }, ctx)).toBe('AAA p1 sample 2024-01-04 b pos [s1]')
    expect(copyLine({ kind: 'sample', id: 's0' }, ctx)).toBe('AAA p1 sample 2024-01-02 a neg [s0]')
    expect(copyLine({ kind: 'sample', id: 's9' }, ctx)).toBe('AAA unsorted sample 2024-01-03 a pos [s9]')
  })
  it('反馈:它点的 node 在前、起止在后;没点 node 的不写', () => {
    expect(copyLine({ kind: 'feedback', id: 'f1' }, ctx)).toBe('AAA p1 feedback step,today 2024-01-04→2024-01-05 [f1]')
    expect(copyLine({ kind: 'feedback', id: 'f2' }, ctx)).toBe('AAA p1 feedback 2024-01-04 [f2]')
  })
  it('什么都没选中:当前日', () => {
    expect(copyLine({ kind: 'day' }, ctx)).toBe('AAA p1 day 2024-01-03')
  })
  it('没有当前日、没有 pattern、对象已不在:退成能写的那一段', () => {
    expect(copyLine({ kind: 'day' }, { ...ctx, currentDay: null })).toBe('AAA p1')
    expect(copyLine({ kind: 'day' }, { ...ctx, pattern: null })).toBe('AAA day 2024-01-03')
    expect(copyLine({ kind: 'box', id: 'gone' }, ctx)).toBe('AAA p1 day 2024-01-03')
    expect(copyLine({ kind: 'sample', id: 'gone' }, ctx)).toBe('AAA p1 day 2024-01-03')
    expect(copyLine({ kind: 'feedback', id: 'gone' }, ctx)).toBe('AAA p1 day 2024-01-03')
  })
})
