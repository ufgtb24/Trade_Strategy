// 样本在界面上的派生量:字母、跨度、成员链(顶层结点与空槽、dup)、others 一排、member_of 一行、
// 改起止的上限、副图上框的标记。成员框一律取「存下的、还在图上、在样本日当天或之前结束的」。
import { describe, it, expect } from 'vitest'
import { weekdaysCovering, type AnnBox, type AnnChart, type AnnSample } from '../src/annotate/model'
import {
  boxMarks, memberChain, memberOfRows, othersOf, resizeLimit, sampleLetters, sampleRange, unsortedCount,
} from '../src/annotate/samples'
import { emptySlots } from '../src/annotate/membership'

// 2025 年 1~3 月的交易日(1-01、1-20、2-17 休市)
const DAYS = weekdaysCovering([{ start: '2025-01-02', end: '2025-03-31' }])
  .filter(d => !['2025-01-20', '2025-02-17'].includes(d))
const NEAR = 40

const box = (id: string, feature: string | null, start: string, end: string, extra: Partial<AnnBox> = {}): AnnBox =>
  ({ id, feature, start, end, ...extra })
const smp = (id: string, date: string, pattern: string | null, members: string[], judgment: 'pos' | 'neg' = 'pos'): AnnSample =>
  ({ id, date, pattern, judgment, members })

describe('字母与跨度', () => {
  it('同一张图、当前 pattern 的样本按日期标 a、b;别的 pattern 的不标;只有一个也标 a', () => {
    const c: AnnChart = { symbol: 'AAA', boxes: [], samples: [
      smp('s2', '2025-02-10', 'P', []), smp('s1', '2025-01-15', 'P', []), smp('s3', '2025-01-20', 'Q', [])] }
    expect([...sampleLetters(c, 'P')]).toEqual([['s1', 'a'], ['s2', 'b']])
    expect([...sampleLetters(c, 'Q')]).toEqual([['s3', 'a']])
    expect(sampleLetters(c, null).size).toBe(0)
  })

  it('跨度从最早的成员框起点到样本日;越过样本日的旧成员框不算', () => {
    const c: AnnChart = { symbol: 'AAA', samples: [smp('s1', '2025-02-10', 'P', ['b1', 'b2', 'b3'])],
      boxes: [box('b1', 'x', '2025-01-20', '2025-01-31'), box('b2', 'y', '2025-01-06', '2025-01-10'),
              box('b3', 'z', '2025-01-02', '2025-02-12')] }
    expect(sampleRange(c.samples[0], c)).toEqual({ start: '2025-01-06', end: '2025-02-10' })
  })

  it('unsorted 的样本数跨全部图', () => {
    expect(unsortedCount([{ symbol: 'A', boxes: [], samples: [smp('s1', '2025-01-02', null, []), smp('s2', '2025-01-03', 'P', [])] },
                          { symbol: 'B', boxes: [], samples: [smp('s3', '2025-01-02', null, [])] }])).toBe(2)
  })
})

describe('成员链与 others', () => {
  // s1(2025-02-28)的成员框:横盘(含子框缩量)、两段回踩(dup);同一 pattern 的 s2 在 BBB 用过「突破」
  const aaa: AnnChart = {
    symbol: 'AAA',
    boxes: [
      box('b1', '横盘', '2025-01-06', '2025-01-31'), box('b2', '缩量', '2025-01-13', '2025-01-17'),
      box('b3', '回踩', '2025-02-03', '2025-02-07'), box('b4', '回踩', '2025-02-18', '2025-02-21'),
      box('b5', '突破', '2025-02-10', '2025-02-12'),          // 画了没收
      box('b6', '突破', '2025-02-24', '2025-03-05'),          // 跨过样本日
      box('b7', '放量', '2025-03-10', '2025-03-12'),          // 整段在样本日之后
      box('b8', '底', '2025-01-02', '2025-01-03'),            // 特征没在这个 pattern 里用过
    ],
    samples: [smp('s1', '2025-02-28', 'P', ['b1', 'b2', 'b3', 'b4'])],
  }
  const bbb: AnnChart = { symbol: 'BBB', boxes: [box('c1', '突破', '2025-01-06', '2025-01-08')],
                          samples: [smp('s2', '2025-01-10', 'P', ['c1'])] }
  const charts = [aaa, bbb]

  it('成员链:顶层结点与空槽按框的先后排,子框挂在父结点下,顶层同一特征两段标 dup', () => {
    const chain = memberChain(aaa.samples[0], aaa, charts, DAYS, NEAR)
    expect(chain.map(x => (x.kind === 'node' ? `${x.node.box}${x.dup ? ':dup' : ''}` : `${x.slot.box}:${x.slot.reason}`)))
      .toEqual(['b1', 'b3:dup', 'b5:unclaimed', 'b4:dup', 'b6:crosses_sample_date'])
    expect(chain[0].kind === 'node' && chain[0].node.kids.map(k => k.box)).toEqual(['b2'])
  })

  it('others:起点不晚于样本日、不是成员框的框;画了没收的在前,跨过样本日的在后', () => {
    const slots = emptySlots(charts, 'AAA', 's1', DAYS, NEAR)
    expect(othersOf(aaa.samples[0], aaa, slots).map(o => `${o.box.id}${o.unclaimed ? ':unclaimed' : ''}${o.crosses ? ':crosses' : ''}`))
      .toEqual(['b5:unclaimed', 'b8', 'b6:crosses'])
  })
})

describe('选中框时', () => {
  const c: AnnChart = {
    symbol: 'AAA',
    boxes: [box('b1', 'x', '2025-01-06', '2025-01-17')],
    samples: [
      smp('s0', '2025-01-03', 'P', []),            // 样本日早于框起点:不列
      smp('s1', '2025-01-17', 'P', ['b1']),        // 收了它
      smp('s2', '2025-01-10', 'P', []),            // 框跨过它的样本日
      smp('s3', '2025-01-24', 'P', []),            // 能收它
      smp('s4', '2025-01-31', 'Q', ['b1']),        // 别的 pattern 收了它:只读
      smp('s5', '2025-02-07', 'Q', []),            // 别的 pattern、没收:不列
    ],
  }

  it('member_of 一行:收了它的全部样本(含别的 pattern,只读),加上当前 pattern 里能收它的;按样本日排', () => {
    expect(memberOfRows(c.boxes[0], c, 'P').map(r => `${r.sample.id}:${r.state}:${r.editable}`))
      .toEqual(['s2:crosses:false', 's1:member:true', 's3:open:true', 's4:member:false'])
  })

  it('改起止的上限:存下的成员框里有它的样本中最早的样本日', () => {
    expect(resizeLimit('b1', c)?.id).toBe('s1')
    expect(resizeLimit('b9', c)).toBeNull()
  })
})

describe('副图上框的标记', () => {
  const c: AnnChart = {
    symbol: 'AAA',
    boxes: [box('b1', '横盘', '2025-01-06', '2025-01-17'), box('b2', '横盘', '2025-01-21', '2025-01-24'),
            box('b3', '横盘', '2025-01-27', '2025-02-04'), box('b4', '放量', '2025-01-02', '2025-01-03')],
    samples: [smp('s1', '2025-01-31', 'P', ['b1']), smp('s2', '2025-02-07', 'P', ['b1']),
              smp('s3', '2025-02-10', 'Q', ['b4'])],
  }

  it('框旁的字母是收了它的当前 pattern 样本;只被别的 pattern 收进的画淡', () => {
    const m = boxMarks(c, 'P', null, [])
    expect(m.get('b1')).toEqual({ owners: ['a', 'b'], away: false, focus: null })
    expect(m.get('b4')).toEqual({ owners: [], away: true, focus: null })
    expect(m.get('b2')!.away).toBe(false)
  })

  it('选中样本时:成员框加粗、画了没收和跨过样本日的单独标出、其余画淡', () => {
    const slots = emptySlots([c], 'AAA', 's1', DAYS, NEAR)
    const m = boxMarks(c, 'P', c.samples[0], slots)
    expect([...m].map(([id, x]) => `${id}:${x.focus}`)).toEqual(['b1:member', 'b2:unclaimed', 'b3:crosses_sample_date', 'b4:dim'])
  })
})
