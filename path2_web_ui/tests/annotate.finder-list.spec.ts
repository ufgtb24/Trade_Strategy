// 找图清单每一行标过什么(annotate/finderList.ts):
// - rally / random 的一行按图窗算:样本日在图窗里才计 pattern 名(没归 pattern 的记作 unsorted),
//   框和图窗有重叠就计进框数;只画了框的行有框数、没有 pattern 名;
// - charts 页列出全部标过的股票,只画了框的也在;只有反馈的不列;
// - PageUp / PageDown 的落点:当前不在这一页从第一行起,到头停住。
import { describe, it, expect } from 'vitest'
import { chartsBySymbol, chartsRows, marksInWindow, NO_MARKS, stepIndex } from '../src/annotate/finderList'
import type { AnnChart, AnnFeedback, AnnState } from '../src/annotate/model'

const box = (id: string, start: string, end: string) => ({ id, feature: null, start, end })
const sample = (id: string, date: string, pattern: string | null, judgment: 'pos' | 'neg' = 'pos') =>
  ({ id, date, pattern, judgment, members: [] })
const FEEDBACK: AnnFeedback = {
  id: 'f-pc-1', pattern: 'W底', app_id: 'bo_only', app_ver: 'v', start: '2024-03-01', end: '2024-03-01',
  target: 'point', source: 'picked', note: 'x',
}

// AAPL:图窗 2024-01-02..2024-06-28 里有 W底 的正样本与负样本、一个 unsorted 样本;窗外有一个 平台 样本
const AAPL: AnnChart = {
  symbol: 'AAPL',
  boxes: [box('b-pc-1', '2023-12-01', '2024-01-05'),     // 跨进图窗左端:算
          box('b-pc-2', '2024-03-01', '2024-03-20'),     // 图窗里:算
          box('b-pc-3', '2024-07-01', '2024-07-20')],    // 图窗外:不算
  samples: [sample('s-pc-1', '2024-03-20', 'W底'),
            sample('s-pc-2', '2024-02-01', 'W底', 'neg'),
            sample('s-pc-3', '2024-05-10', null),
            sample('s-pc-4', '2024-08-01', '平台')],     // 样本日在图窗外:不计 pattern 名
}
// MSFT:只画了框
const MSFT: AnnChart = { symbol: 'MSFT', boxes: [box('b-pc-4', '2024-02-01', '2024-02-10')], samples: [] }
// TSLA:只有反馈
const TSLA: AnnChart = { symbol: 'TSLA', boxes: [], samples: [], feedback: [FEEDBACK] }
// AMD:负样本,不在窗口算法里用
const AMD: AnnChart = { symbol: 'AMD', boxes: [], samples: [sample('s-pc-5', '2022-01-03', '平台', 'neg')] }

const STATE: AnnState = {
  machine: 'pc', data_fingerprint: null, features: [], patterns: [{ name: 'W底' }, { name: '平台' }],
  charts: [MSFT, TSLA, AAPL, AMD],
}
const WIN = { start: '2024-01-02', end: '2024-06-28' }

describe('marksInWindow:rally / random 的一行按图窗算', () => {
  it('样本日在图窗里才计 pattern 名;名字去重、按名字排,unsorted 排最后;悬停列的样本按日期', () => {
    const m = marksInWindow(AAPL, WIN)
    expect(m.patterns).toEqual(['W底', null])
    expect(m.samples.map(s => [s.date, s.pattern, s.judgment])).toEqual([
      ['2024-02-01', 'W底', 'neg'], ['2024-03-20', 'W底', 'pos'], ['2024-05-10', null, 'pos']])
  })

  it('框和图窗有重叠就算:跨进图窗一端的算,完全在窗外的不算', () => {
    expect(marksInWindow(AAPL, WIN).boxes).toBe(2)
  })

  it('图窗两端都含:样本日正好在端点上也算', () => {
    const m = marksInWindow(AAPL, { start: '2024-03-20', end: '2024-05-10' })
    expect(m.samples.map(s => s.id)).toEqual(['s-pc-1', 's-pc-3'])
    expect(m.boxes).toBe(1)                                  // b-pc-2 止于 2024-03-20,碰到左端
  })

  it('只画了框的行:有框数,没有 pattern 名', () => {
    const m = marksInWindow(MSFT, WIN)
    expect(m).toEqual({ patterns: [], samples: [], boxes: 1 })
  })

  it('这只股票没标过,或图窗里什么都没有:空', () => {
    expect(marksInWindow(undefined, WIN)).toBe(NO_MARKS)
    expect(marksInWindow(AAPL, { start: '2021-01-04', end: '2021-06-30' })).toEqual({ patterns: [], samples: [], boxes: 0 })
  })

  it('chartsBySymbol:按代码找到那张图;状态还没读到时为空', () => {
    expect(chartsBySymbol(STATE).get('AAPL')).toBe(AAPL)
    expect(chartsBySymbol(null).size).toBe(0)
  })
})

describe('chartsRows:全部标过的股票', () => {
  it('有框或有样本就列,只画了框的也在;只有反馈的不列;按代码排', () => {
    expect(chartsRows(STATE).map(r => r.symbol)).toEqual(['AAPL', 'AMD', 'MSFT'])
  })

  it('一只一行:全部样本的 pattern 名、正负样本数、框数', () => {
    const [aapl, amd, msft] = chartsRows(STATE)
    expect(aapl).toMatchObject({ patterns: ['W底', '平台', null], pos: 3, neg: 1, boxes: 3 })
    expect(amd).toMatchObject({ patterns: ['平台'], pos: 0, neg: 1, boxes: 0 })
    expect(msft).toMatchObject({ patterns: [], pos: 0, neg: 0, boxes: 1 })
  })

  it('状态还没读到:没有行', () => {
    expect(chartsRows(null)).toEqual([])
  })
})

describe('stepIndex:PageUp / PageDown 换到哪一行', () => {
  it('往下、往上各一行', () => {
    expect(stepIndex(3, 1, 'PageDown')).toBe(2)
    expect(stepIndex(3, 1, 'PageUp')).toBe(0)
  })
  it('到头停住(不用换)', () => {
    expect(stepIndex(3, 2, 'PageDown')).toBeNull()
    expect(stepIndex(3, 0, 'PageUp')).toBeNull()
  })
  it('当前图不在这一页:从第一行起;没有行:不换', () => {
    expect(stepIndex(3, -1, 'PageDown')).toBe(0)
    expect(stepIndex(3, -1, 'PageUp')).toBe(0)
    expect(stepIndex(0, -1, 'PageDown')).toBeNull()
  })
})
