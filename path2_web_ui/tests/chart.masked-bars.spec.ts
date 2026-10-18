// 调试视图的看图下界:下界之前的 bar 只有日期、价格与量为 null(后端为让按序号定位的事件与 K 线对齐而占位)。
// 渲染一律不画这段:K 线 / 量为空,落在里面的事件、买点括号不画,跨进来的从第一根有价格的 bar 画起,
// 悬停只报日期,纵轴只按有价格的 bar 算。类型无关:只看 bar 有没有价格,不认任何事件类型。
import { describe, it, expect } from 'vitest'
import {
  computeEventData, buildVolumeSeriesAndYAxis, buildBarTooltipFormatter, firstPricedIdx, isPriced,
} from '../src/render/chart'
import type { BandRenderInput } from '../src/render/chart'
import { deriveTagMap, isolatedNodeIds, nodeOfEventByBand, bandKeyOf } from '../src/render/visible'
import type { Bar, EventDict, MatchDict, Topology, Tier } from '../src/types'

const LEAD = 5
const bars: Bar[] = Array.from({ length: 20 }, (_, i) => i < LEAD
  ? { date: `2024-12-${String(20 + i).padStart(2, '0')}`, o: null, h: null, l: null, c: null, v: null, rv: null }
  : { date: `2025-01-${String(i - LEAD + 2).padStart(2, '0')}`, o: 10 + i, h: 11 + i, l: 9 + i,
      c: 10.5 + i, v: 1000 + i, rv: 1 })

const topology: Topology = {
  nodes: [
    { node_id: 'down', where_rules: [] },
    { node_id: 'bo', render_grid: 'price', where_rules: [] },
    { node_id: 'tb', where_rules: [] },
  ],
  edges: [],
}
const events: EventDict[] = [
  { instance_id: 'down_in#0', node_id: 'down', start_idx: 0, end_idx: 3 },     // 整段在下界之前
  { instance_id: 'down_cross#0', node_id: 'down', start_idx: 2, end_idx: 9 },  // 跨进来
  { instance_id: 'down_after#0', node_id: 'down', start_idx: 10, end_idx: 14 },
  { instance_id: 'bo_in#0', node_id: 'bo', start_idx: 1, end_idx: 1 },
  { instance_id: 'bo_after#0', node_id: 'bo', start_idx: 12, end_idx: 12 },
  { instance_id: 'tb_in#0', node_id: 'tb', start_idx: 4, end_idx: 4 },
  { instance_id: 'tb_after#0', node_id: 'tb', start_idx: 16, end_idx: 16 },
] as any[]
const matches: MatchDict[] = [
  { match_id: 'm_in', start_idx: 0, end_idx: 4, node_index: {}, children: [] },
  { match_id: 'm_cross', start_idx: 2, end_idx: 16, node_index: {}, children: [] },
]

function input(): BandRenderInput {
  const { tagToNodes, tagList } = deriveTagMap(topology.nodes)
  return {
    topology, isolatedNodeIds: isolatedNodeIds(topology), tagList,
    level: 'detected', nodeColors: {},
    eventTier: () => 'detected' as Tier,
    nodeOfEventByBand: (e) => nodeOfEventByBand(e, tagToNodes, tagList),
    bandKeyOf: (e) => bandKeyOf(e),
    nodeVisible: {}, tagToNodes, selectedInstanceId: null,
  }
}

describe('看图下界之前的 bar 不画', () => {
  it('isPriced / firstPricedIdx 只看有没有价格', () => {
    expect(bars.filter(isPriced).length).toBe(20 - LEAD)
    expect(firstPricedIdx(bars)).toBe(LEAD)
    expect(firstPricedIdx(bars.slice(LEAD))).toBe(0)
    expect(firstPricedIdx(bars.slice(0, LEAD))).toBe(LEAD)
  })

  it('K 线与量:下界之前为空,之后照常', () => {
    const b = computeEventData(bars, events, matches, input())
    expect(b.dates).toEqual(bars.map(x => x.date))                  // 日期全留(序号对齐)
    expect(b.candle.slice(0, LEAD).every(x => x === '-')).toBe(true)
    expect(b.volume.slice(0, LEAD).every(x => x === '-')).toBe(true)
    expect(b.candle[LEAD]).toEqual([15, 15.5, 14, 16])
    expect(b.volume[LEAD]).toBe(1005)
  })

  it('事件:整段在下界之前的不画,跨进来的从第一根有价格的 bar 画起', () => {
    const b = computeEventData(bars, events, matches, input())
    const sub = [...b.intervalData, ...b.pointData]
    const ids = sub.map((d: any) => d.instance_id)
    expect(ids).not.toContain('down_in#0')
    expect(ids).not.toContain('tb_in#0')
    expect(ids).toEqual(expect.arrayContaining(['down_cross#0', 'down_after#0', 'tb_after#0']))
    const cross = sub.find((d: any) => d.instance_id === 'down_cross#0')!
    expect(cross.value.slice(0, 2)).toEqual([LEAD, 9])
    const price = b.pricePointData.map((d: any) => d.instance_id)
    expect(price).toEqual(['bo_after#0'])
  })

  it('买点括号:整段在下界之前的不画,跨进来的从第一根有价格的 bar 画起', () => {
    const b = computeEventData(bars, events, matches, input())
    expect(b.bracketData.map(d => d.match_id)).toEqual(['m_cross'])
    expect(b.bracketData[0].value.slice(0, 2)).toEqual([LEAD, 16])
  })

  it('量柱为空、纵轴只按有价格的 bar 算', () => {
    const { volSeries, yAxisOverride } = buildVolumeSeriesAndYAxis(bars, 0, bars.length - 1)
    expect(volSeries.data.slice(0, LEAD).every(d => d.value === null)).toBe(true)
    expect(volSeries.data.slice(LEAD).every(d => typeof d.value === 'number')).toBe(true)
    expect(Number.isFinite(yAxisOverride.min) && Number.isFinite(yAxisOverride.max)).toBe(true)
    const only = buildVolumeSeriesAndYAxis(bars, 0, LEAD - 1)        // 可见区一根有价格的都没有
    expect(Number.isFinite(only.yAxisOverride.min) && Number.isFinite(only.yAxisOverride.max)).toBe(true)
  })

  it('悬停在下界之前的 bar 只报日期', () => {
    const fmt = buildBarTooltipFormatter(bars)
    const masked = fmt({ seriesName: 'kline', dataIndex: 2 })
    expect(masked).toContain(bars[2].date)
    expect(masked).toContain('看图下界之前')
    expect(masked).not.toMatch(/Open|Close|Vol/)
    const first = fmt({ seriesName: 'kline', dataIndex: LEAD })      // 前一根没价格:涨跌幅 N/A
    expect(first).toContain('N/A')
  })
})
