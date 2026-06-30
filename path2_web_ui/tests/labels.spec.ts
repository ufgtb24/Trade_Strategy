// label(N 日前瞻收益)与缓冲窗:纯函数 + chart 选项。
import { describe, it, expect } from 'vitest'
import { windowOf, formatForwardReturn } from '../src/render/visible'

describe('windowOf', () => {
  it('缓冲扫描用 win_*', () => {
    expect(windowOf({ start_date: 'a', end_date: 'b', win_start: 'wa', win_end: 'wb' }))
      .toEqual({ start: 'wa', end: 'wb' })
  })
  it('win_start/win_end 存在时优先返回 win_*', () => {
    expect(windowOf({ start_date: 'a', end_date: 'b', win_start: 'wa2', win_end: 'wb2' }))
      .toEqual({ start: 'wa2', end: 'wb2' })
  })
})

describe('formatForwardReturn', () => {
  it('正值带 +,一位小数百分比', () => expect(formatForwardReturn(0.1234)).toBe('+12.3%'))
  it('负值', () => expect(formatForwardReturn(-0.05)).toBe('-5.0%'))
  it('null(尾部数据不足)→ —', () => expect(formatForwardReturn(null)).toBe('—'))
})

import { buildKlineOption, buildMarkerTooltipFormatter } from '../src/render/chart'
import type { Bar, MatchDict, Topology } from '../src/types'

const bars: Bar[] = [
  { date: '2025-01-01', o: 1, h: 1, l: 1, c: 1, v: 1, rv: 0 },
  { date: '2025-01-02', o: 1, h: 1, l: 1, c: 1, v: 1, rv: 0 },
  { date: '2025-01-03', o: 1, h: 1, l: 1, c: 1, v: 1, rv: 0 },
]
const baseInput = () => ({
  topology: { nodes: [], edges: [] } as Topology,
  isolatedNodeIds: new Set<string>(),
  tagList: [] as string[],
  level: 'detected' as const,
  roleColors: {},
  eventTier: () => 'detected' as const,
  roleOfEventByBand: () => null,
  bandKeyOf: () => '',
})

// Task 7: strictWindow 现用 markArea 阴影替代 markLine 标记线。
describe('strict window markArea (Task 7)', () => {
  it('strictWindow → kline 系列带 markArea 灰阴影(有左缓冲区)', () => {
    const opt: any = buildKlineOption(bars, [], [], { ...baseInput(), strictWindow: { startIdx: 1, endIdx: 2 } })
    const kline = opt.series.find((s: any) => s.name === 'kline')
    // startIdx=1 > 0 → 有左缓冲区,markArea 存在
    expect(kline.markArea).toBeDefined()
    expect(kline.markArea.data.length).toBeGreaterThanOrEqual(1)
  })
  it('无 strictWindow → kline 系列无 markArea(老行为)', () => {
    const opt: any = buildKlineOption(bars, [], [], baseInput())
    const kline = opt.series.find((s: any) => s.name === 'kline')
    expect(kline.markArea).toBeUndefined()
  })
})

// Task 7: matchLabel tooltip 现挂在 marker series 级别(brackets 系列),不再在全局 tooltip。
describe('match tooltip label', () => {
  const match: MatchDict = {
    event_id: 'm1', start_idx: 0, end_idx: 1, role_index: {}, children: [], predicate_trace: null,
  }
  it('matchLabel 提供时,brackets series tooltip 显示 label 行 + 组成段', () => {
    const opt: any = buildKlineOption(bars, [], [match], {
      ...baseInput(), matchLabel: (id: string) => (id === 'm1' ? 'ret_20: +12.3%' : null),
    })
    const brackets = opt.series.find((s: any) => s.name === 'brackets')
    expect(brackets.tooltip).toBeDefined()
    // 组成段 (M #15): matchLabel 行 + 组成 (0 events): (match.children=[])
    expect(brackets.tooltip.formatter({ data: { match_id: 'm1' } })).toBe('Match: ret_20: +12.3%<br/>组成 (0 events):')
  })
  it('matchLabel 返回 null(无 label 数据)→ 仅组成段', () => {
    const opt: any = buildKlineOption(bars, [], [match], { ...baseInput(), matchLabel: () => null })
    const brackets = opt.series.find((s: any) => s.name === 'brackets')
    // 无 label 行,但组成段仍在
    expect(brackets.tooltip.formatter({ data: { match_id: 'm1' } })).toBe('组成 (0 events):')
  })
})

describe('buildMarkerTooltipFormatter — ordinal consistency with packBrackets (Task 9 fix)', () => {
  it('marker 归属节 ordinal uses start_idx sort, not raw matches order', () => {
    const matches: MatchDict[] = [
      // 故意乱序(非 start_idx 升序):
      { event_id: 'm_late',  start_idx: 50, end_idx: 60, role_index: {}, children: ['eShared'], predicate_trace: null },
      { event_id: 'm_early', start_idx: 10, end_idx: 20, role_index: {}, children: ['eShared'], predicate_trace: null },
      { event_id: 'm_mid',   start_idx: 30, end_idx: 40, role_index: {}, children: ['eShared'], predicate_trace: null },
    ]
    const fmt = buildMarkerTooltipFormatter(undefined, undefined, { matches, candidateMatchIds: new Set() })
    const out = fmt({ data: { event_id: 'eShared' } })
    // start_idx 排序后: m_early=①, m_mid=②, m_late=③ → 三者都含 eShared
    expect(out).toContain('归属: match ① ② ③')
  })
})
