// 副图族行:computeEventData 产的族底线 / 记号 / 高亮 / 当前日,以及族底线与当前日竖线的渲染。
import { describe, it, expect } from 'vitest'
import { buildMainOption, buildSubOption, computeEventData, makeRenderBracketLine, makeRenderFamilyLine, renderCursor } from '../src/render/chart'
import { computeSubGeometry, TIER_H } from '../src/render/subGeometry'
import type { EventDict, HitDict, Tier } from '../src/types'

const ev = (node: string, s: number, e: number, k = 0): EventDict =>
  ({ instance_id: `${node}@${s}-${e}#${k}`, node_id: node, instance_idx: k, start_idx: s, end_idx: e })
const bars = Array.from({ length: 12 }, (_, i) =>
  ({ date: `2025-01-${String(i + 2).padStart(2, '0')}`, o: 1, h: 1, l: 1, c: 1, v: 1, rv: 1 }))

function input(tiers: Record<string, Tier>, extra: any = {}): any {
  return {
    topology: { nodes: [{ node_id: 'p', where_rules: [] }], edges: [] },
    isolatedNodeIds: new Set(), tagList: ['p'], level: 'detected', nodeColors: { p: '#1a80ba' },
    eventTier: (e: EventDict) => tiers[e.instance_id] ?? 'detected', nodeOfEventByBand: (e: EventDict) => e.node_id,
    bandKeyOf: (e: EventDict) => e.node_id, tagToNodes: { p: ['p'] }, ...extra,
  }
}

const fam = [ev('p', 0, 3), ev('p', 0, 4), ev('p', 0, 4, 1), ev('p', 0, 7)]
const single = ev('p', 5, 6)
const TIERS: Record<string, Tier> = { 'p@0-4#1': 'in_hit', 'p@0-7#0': 'qualified' }

describe('computeEventData · 族行', () => {
  it('多成员族:一条底线 + 每个不同终点一格(高度按档位);单成员族:一根整条、底线不画', () => {
    const b = computeEventData(bars, [...fam, single], [], input(TIERS))
    const lines = b.familyLineData.map((d: any) => [d.family_key, d.value[0], d.value[1], d.multi])
    expect(lines).toEqual([['p@0', 0, 7, true], ['p@5', 5, 6, false]])
    const marks = b.intervalData.map((d: any) => [d.mark_kind, d.value[0], d.value[1], d.value[5], d.member_ids.length])
    expect(marks).toEqual([
      ['cell', 3, 3, TIER_H.detected, 1],
      ['cell', 4, 4, TIER_H.in_hit, 2],        // 同一格两个成员,取深的档
      ['cell', 7, 7, TIER_H.qualified, 1],
      ['bar', 5, 6, TIER_H.detected, 1],
    ])
    // 两个族起点不同、跨度重叠 → 不同 lane
    expect(b.familyLineData[0].value[2]).not.toBe(b.familyLineData[1].value[2])
    expect(b.intervalData[1].member_labels).toHaveLength(2)
    expect(b.intervalData[1].member_k).toEqual([2, 3])
    expect(b.intervalData[1].family_n).toBe(4)
  })

  it('档位开到 in_hit:族只剩一格,底线缩到剩下成员的终点,仍画成格不变回整条', () => {
    const b = computeEventData(bars, fam, [], input(TIERS, { level: 'in_hit' }))
    expect(b.familyLineData.map((d: any) => [d.value[0], d.value[1], d.multi])).toEqual([[0, 4, true]])
    expect(b.intervalData.map((d: any) => [d.mark_kind, d.value[0]])).toEqual([['cell', 4]])
  })

  it('扫描窗末拆段:底线拆成窗内 / 窗后两段;格整格判,窗后的格画成 detected 灰', () => {
    const b = computeEventData(bars, fam, [], input(TIERS, { strictWindow: { startIdx: 0, endIdx: 5 } }))
    expect(b.familyLineData.map((d: any) => [d.value[0], d.value[1], d.afterWindow])).toEqual([[0, 5, false], [6, 7, true]])
    const last = b.intervalData.find((d: any) => d.value[0] === 7)
    expect(last.itemStyle.color).toBe('#b4bac2')
  })

  it('当家行:族键对上的那一行 active;当前日在 K 线范围内才出竖线', () => {
    const b = computeEventData(bars, [...fam, single], [], input(TIERS, { activeFamily: 'p@5', currentDay: 6 }))
    expect(b.familyLineData.map((d: any) => d.active)).toEqual([false, true])
    expect(b.cursorData).toEqual([{ value: [6] }])
    expect(computeEventData(bars, fam, [], input(TIERS, { currentDay: 99 })).cursorData).toEqual([])
    expect(computeEventData(bars, fam, [], input(TIERS)).cursorData).toEqual([])
  })

  it('选中一个成员:族行上画空心跨度框 [族起点, 成员终点] + 它那一格的框', () => {
    const b = computeEventData(bars, fam, [], input(TIERS, { selectedInstanceId: 'p@0-4#1' }))
    expect(b.highlightData.map((d: any) => [d.shape, d.value[0], d.value[1], d.kind]))
      .toEqual([['extent', 0, 4, 'focus'], ['mark', 4, 4, 'focus']])
  })

  it('bracket:同起点的 hit 折成一族,每个终点一格;当家行对上 hits@起点', () => {
    const hits: HitDict[] = [
      { hit_id: 'h0', start_idx: 0, end_idx: 4, node_index: { p: 'p@0-4#1' }, children: ['p@0-4#1'] },
      { hit_id: 'h1', start_idx: 0, end_idx: 7, node_index: { p: 'p@0-7#0' }, children: ['p@0-7#0'] },
    ]
    const b = computeEventData(bars, fam, hits, input(TIERS, { activeFamily: 'hits@0', endNode: 'p' }))
    expect(b.bracketLineData.map((d: any) => [d.family_key, d.multi, d.active])).toEqual([['hits@0', true, true]])
    expect(b.bracketData.filter((d: any) => d.kind === 'mark').map((d: any) => [d.value[0], d.hit_ids]))
      .toEqual([[4, ['h0']], [7, ['h1']]])
    // 买点 node 是 p 本身:它跨度里的每一根都是买入日,每个 ▼ 带买在这天的 hit
    const buys = b.bracketData.filter((d: any) => d.kind === 'buy')
    expect(buys.map((d: any) => d.buy_day)).toEqual([0, 1, 2, 3, 4, 5, 6, 7])
    expect(buys[4].hit_ids).toEqual(['h0', 'h1'])
    expect(buys[7].hit_ids).toEqual(['h1'])
  })

  it('副图不再有 tier-tags 系列;族底线、当前日竖线挂上;当前日竖线画在最上层', () => {
    const inp = input(TIERS, { currentDay: 4 })
    const b = computeEventData(bars, [...fam, single], [], inp)
    const geom = computeSubGeometry({ bracketLaneCount: 0, bandLaneCounts: [2] })
    const sub: any = buildSubOption(bars, b, geom, inp, 800)
    const names = sub.series.map((s: any) => s.name)
    expect(names).not.toContain('tier-tags')
    expect(names).toEqual(expect.arrayContaining(['family-lines', 'intervals', 'current-day']))
    const zOf = (n: string) => sub.series.find((s: any) => s.name === n).z
    expect(zOf('current-day')).toBeGreaterThan(zOf('highlight'))
    expect(zOf('family-lines')).toBeLessThan(zOf('intervals'))
    // 界面固定文字一律黑色:band 表头
    const texts = (sub.graphic?.[0]?.elements ?? sub.graphic ?? []).filter((e: any) => e.type === 'text')
    expect(texts.length).toBeGreaterThan(0)
    expect(texts.every((e: any) => e.style.fill === '#000000')).toBe(true)
    const main: any = buildMainOption(bars, b, inp)
    expect(main.series.filter((s: any) => String(s.name).startsWith('current-day')).map((s: any) => s.data))
      .toEqual([[{ value: [4] }], [{ value: [4] }]])
  })
})

describe('族底线与当前日竖线的渲染', () => {
  const api = {
    value: (i: number) => [2, 6, 0, 0][i] ?? 0,
    coord: ([x]: number[]) => [x * 10, 0],
    size: () => [10, 0],
  }
  const geom = [{ top: 20, h: 40, laneCount: 1 }]

  it('多成员族画中性底线;当家行再加一根粗深线;单成员不当家时只有透明的悬停区', () => {
    const one = makeRenderFamilyLine([{ multi: true, active: true }], geom as any)({ dataIndex: 0 }, api) as any
    expect(one.children).toHaveLength(3)
    expect(one.children[1].style.fill).toBe('#6b7280')
    expect(one.children[2].shape.height).toBe(2.5)
    const lone = makeRenderFamilyLine([{ multi: false, active: false }], geom as any)({ dataIndex: 0 }, api) as any
    expect(lone.children).toHaveLength(1)
  })

  it('bracket 族底线:每一族都画中性底线(只有一次 hit 也画,bracket 一律梳子);当家行加粗;行尾不再写族序号', () => {
    const api = { value: (i: number) => [2, 6, 0, 2][i] ?? 0, coord: ([x]: number[]) => [x * 10, 0], size: () => [10, 0] }
    const g = makeRenderBracketLine([{ multi: true, active: true }])({ dataIndex: 0 }, api) as any
    expect(g.children.filter((c: any) => c.type === 'rect')).toHaveLength(2)
    expect(g.children.some((c: any) => c.type === 'text')).toBe(false)
    const lone = makeRenderBracketLine([{ multi: false, active: false }])({ dataIndex: 0 }, api) as any
    expect(lone.children).toHaveLength(1)
    expect(lone.children[0].style.fill).toBe('#6b7280')
  })

  it('当前日竖线:白边在下、深色细线在上,贯穿 grid 全高', () => {
    const cur = renderCursor({ coordSys: { x: 0, y: 5, width: 200, height: 90 } },
                             { value: () => 4, coord: ([x]: number[]) => [x * 10, 0] }) as any
    const [halo, core] = cur.children
    expect(halo.style.stroke).toBe('#ffffff')
    expect(core.style.stroke).toBe('#1e293b')
    expect(core.shape.y1).toBe(5)
    expect(core.shape.y2).toBe(95)
  })
})
