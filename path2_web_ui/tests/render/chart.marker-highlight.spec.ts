import { describe, it, expect } from 'vitest'
import { computeEventData } from '../../src/render/chart'
import type { BandRenderInput } from '../../src/render/chart'
import type { EventDict, MatchDict, Bar } from '../../src/types'

// 最小 fixture — 只覆盖 marker 装配路径。
function makeBars(n = 10): Bar[] {
  return Array.from({ length: n }, (_, i) => ({
    date: `2026-01-${String(i + 1).padStart(2, '0')}`,
    o: 100, h: 105, l: 95, c: 102, v: 1000, rv: 1000,
  }))
}

function makeInput(overrides: Partial<BandRenderInput> = {}): BandRenderInput {
  return {
    topology: { nodes: [{ node_id: 'bo', source_tag: 'BO' }], edges: [] } as any,
    tagList: ['BO'],
    level: 'detected',
    nodeColors: { bo: { detected: '#111', qualified: '#222', matched: '#333' } } as any,
    eventTier: () => 'detected',
    nodeOfEventByBand: () => 'bo',
    bandKeyOf: () => 'BO',
    nodeVisible: {},
    tagToNodes: { BO: ['bo'] },
    selectedEventId: null,
    ...overrides,
  } as BandRenderInput
}

const eBo: EventDict = {
  event_id: 'e_bo_1', event_type: 'BO', class_id: 'BO',
  start_idx: 3, end_idx: 3,
} as any

describe('computeEventData · shiftSelectedEventIds marker 高亮通道', () => {
  it('shiftSelectedEventIds undefined → 各 series itemStyle 不带 borderColor', () => {
    const bundle = computeEventData(makeBars(), [eBo], [], makeInput())
    const all = [...bundle.pointData, ...bundle.intervalData, ...bundle.pricePointData, ...bundle.satelliteData]
    for (const d of all) {
      expect(d.itemStyle?.borderColor).toBeUndefined()
    }
  })

  it('shiftSelectedEventIds 空集 → 同上,零副作用', () => {
    const bundle = computeEventData(makeBars(), [eBo], [],
      makeInput({ shiftSelectedEventIds: new Set() }))
    const all = [...bundle.pointData, ...bundle.intervalData, ...bundle.pricePointData, ...bundle.satelliteData]
    for (const d of all) {
      expect(d.itemStyle?.borderColor).toBeUndefined()
    }
  })

  it('shiftSelectedEventIds undefined → veilData / veilPriceData 为空', () => {
    const bundle = computeEventData(makeBars(), [eBo], [], makeInput())
    expect(bundle.veilData).toEqual([])
    expect(bundle.veilPriceData).toEqual([])
  })

  it('shiftSelectedEventIds 空集 → veilData / veilPriceData 为空', () => {
    const bundle = computeEventData(makeBars(), [eBo], [],
      makeInput({ shiftSelectedEventIds: new Set() }))
    expect(bundle.veilData).toEqual([])
    expect(bundle.veilPriceData).toEqual([])
  })

  it('shiftSelectedEventIds 含 e_bo_1 → veil* 里含 event_id + kind 正确', () => {
    const bundle = computeEventData(makeBars(), [eBo], [],
      makeInput({ shiftSelectedEventIds: new Set(['e_bo_1']) }))
    const all = [...bundle.veilData, ...bundle.veilPriceData]
    const hit = all.find(d => d.event_id === 'e_bo_1')
    expect(hit).toBeDefined()
    expect(['point', 'interval', 'pricePoint', 'satellite']).toContain(hit!.kind)
  })

  it('shiftSelectedEventIds 命中的 event 未命中的 event 不进 veil', () => {
    const eOther: EventDict = { ...eBo, event_id: 'e_other', start_idx: 5, end_idx: 5 } as any
    const bundle = computeEventData(makeBars(), [eBo, eOther], [],
      makeInput({ shiftSelectedEventIds: new Set(['e_bo_1']) }))
    const all = [...bundle.veilData, ...bundle.veilPriceData]
    expect(all.find(d => d.event_id === 'e_other')).toBeUndefined()
  })

})
