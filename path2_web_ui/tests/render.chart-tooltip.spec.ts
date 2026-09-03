import { describe, it, expect, vi } from 'vitest'
import { buildMarkerTooltipFormatter } from '../src/render/chart'
import type { MatchDict } from '../src/types'

describe('buildMarkerTooltipFormatter multi-confirm', () => {
  const matches = [
    { match_id: 'm1', children: ['tb_6_7#0'], node_index: {}, leaf: 'tb_6_7#0' },
    { match_id: 'm2', children: ['tb_6_7#0'], node_index: {}, leaf: 'tb_6_7#0' },
  ] as unknown as MatchDict[]

  it('同 leaf 被 >=2 match 共享时输出确认行', () => {
    const f = buildMarkerTooltipFormatter(undefined, undefined,
      { matches, candidateMatchIds: new Set() })
    const html = f({ data: { instance_id: 'tb_6_7#0' } } as never)
    expect(html).toContain('2 个 match 共享')
  })

  it('独占 leaf 不输出确认行', () => {
    const f = buildMarkerTooltipFormatter(undefined, undefined,
      { matches: [matches[0]], candidateMatchIds: new Set() })
    const html = f({ data: { instance_id: 'tb_6_7#0' } } as never)
    expect(html).not.toContain('共享')
  })
})

// ─── Task 9 · tooltip 实例级:formatter 直接把 data.instance_id 传给 tooltipResolver ──
// marker series data 恒带 instance_id(不再有 event_key/#idx 解析),resolver 按
// instance_id 展示【所悬停实例】的判定(多实例各判各的)。
describe('buildMarkerTooltipFormatter 实例级传递 (Task 9)', () => {
  const payloadOf = (instanceId: string) => ({
    identity: { nodes: [], dateStart: 'd', dateEnd: null, eventId: instanceId },
    clauses: [], raw: {},
  })

  it('data.instance_id 原样传给 tooltipResolver(无 event_key 解析)', () => {
    const calls: string[] = []
    const resolver = (instanceId: string) => {
      calls.push(instanceId)
      return payloadOf(instanceId)
    }
    const f = buildMarkerTooltipFormatter(resolver, undefined)
    f({ data: { instance_id: 'tb_v1_293#1' } } as never)
    expect(calls).toEqual(['tb_v1_293#1'])   // 精确到实例 instance_id,无 # 解析
  })

  it('bracket data(match_id)走 matchLabel + 组成段 · 不触发 resolver', () => {
    const resolver = vi.fn(() => payloadOf('x'))
    const matchLabel = vi.fn(() => 'ret_20: +5.0%')
    const match = { match_id: 'm9', children: ['a#0', 'b#0'],
                    node_index: { a: 'a#0', b: 'b#0' } } as unknown as MatchDict
    const f = buildMarkerTooltipFormatter(resolver, matchLabel,
      { matches: [match], candidateMatchIds: new Set() })
    const html = f({ data: { match_id: 'm9' } } as never)
    expect(html).toContain('ret_20: +5.0%')
    expect(html).toContain('a: a#0')
    expect(html).toContain('b: b#0')
    expect(resolver).not.toHaveBeenCalled()
  })
})
