import { describe, it, expect, vi } from 'vitest'
import { buildMarkerTooltipFormatter } from '../src/render/chart'
import type { EventDict, HitDict } from '../src/types'

describe('buildMarkerTooltipFormatter:被几次 hit 用到(hits ×n)', () => {
  // h1、h2 的 node_index 都引用 plateau P;step S 只挂在 P 的 child_refs 下(子 node 的 event 不在 node_index 里)
  const hits = [
    { hit_id: 'h1', children: [], node_index: { plateau: 'P#0' } },
    { hit_id: 'h2', children: [], node_index: { plateau: 'P#0' } },
    { hit_id: 'h3', children: [], node_index: { plateau: 'Q#0' } },
  ] as unknown as HitDict[]
  const events = [
    { instance_id: 'P#0', child_refs: { steps: ['S#0'] } },
    { instance_id: 'Q#0', child_refs: { steps: ['S#1'] } },
    { instance_id: 'S#0', child_refs: {} },
  ] as unknown as EventDict[]

  // 写法和显示栏、选中卡一致:个数一律 ×n
  it('node_index 直接引用:hits ×n 是引用它的 hit 数', () => {
    const f = buildMarkerTooltipFormatter(undefined, undefined, { hits, events })
    expect(f({ data: { instance_id: 'P#0' } } as never)).toContain('hits ×2')
  })

  it('子 node 的 event 沿 child_refs 找父容器(和选中它时牵出的 hit 同一口径)', () => {
    const f = buildMarkerTooltipFormatter(undefined, undefined, { hits, events })
    expect(f({ data: { instance_id: 'S#0' } } as never)).toContain('hits ×2')
    expect(f({ data: { instance_id: 'S#1' } } as never)).toContain('hits ×1')
  })

  it('一格几个成员:合起来的 hit 数;没有 hit 用到时不写', () => {
    const f = buildMarkerTooltipFormatter(undefined, undefined, { hits, events })
    expect(f({ data: { instance_id: 'P#0', member_ids: ['P#0', 'Q#0'] } } as never)).toContain('hits ×3')
    expect(f({ data: { instance_id: 'Z#0' } } as never)).not.toContain('hits ×')
  })
})

describe('buildMarkerTooltipFormatter:band 格写并在这一格里的几个 event', () => {
  it('两个成员的格逐行写 events j/m 与区别;不写它是这一族的第几个位置', () => {
    const f = buildMarkerTooltipFormatter(undefined, undefined)
    const html = f({ data: { instance_id: 'S#0', member_ids: ['S#0', 'S#1'],
                             stack: ['events 1/2 step→2024-11-21', 'events 2/2 step→2024-11-22'] } } as never)
    expect(html).toContain('events 1/2 step→2024-11-21')
    expect(html).toContain('events 2/2 step→2024-11-22')
    expect(html).not.toContain('day ')
    expect(html).not.toMatch(/members?:/)
  })

  it('只有一个成员的格:不写 events', () => {
    const f = buildMarkerTooltipFormatter(undefined, undefined)
    const html = f({ data: { instance_id: 'S#0', member_ids: ['S#0'] } } as never)
    expect(html).not.toContain('events ')
    expect(html).not.toContain('day ')
  })
})

describe('buildMarkerTooltipFormatter:hits 格写这一格的几次,组成只写当前那次', () => {
  const hits = [
    { hit_id: 'a', children: ['x#0'], node_index: { plateau: 'x#0' } },
    { hit_id: 'b', children: ['y#0', 'z#0'], node_index: { plateau: 'y#0', step: 'z#0' } },
  ] as unknown as HitDict[]
  const cell = { hit_id: 'a', hit_ids: ['a', 'b'], hit_labels: ['step→11-21', 'step→11-22'], kind: 'buy', buy_date: '2024-11-27' }

  it('两次:hits ×2,逐次写 hits j/m 与区别;没选中这格里的哪次时组成写第一次', () => {
    const f = buildMarkerTooltipFormatter(undefined, undefined, { hits, selectedHitId: null })
    const html = f({ data: cell } as never)
    expect(html).toContain('buy: 2024-11-27')
    expect(html).toContain('hits ×2')
    expect(html).toContain('hits 1/2 step→11-21')
    expect(html).toContain('hits 2/2 step→11-22')
    expect(html).not.toContain('candidate')
    expect(html).toContain('hits 1/2</span> (1 events):')
    expect(html).toContain('plateau: x#0')
  })

  it('当前选中的是第二次:组成写它', () => {
    const f = buildMarkerTooltipFormatter(undefined, undefined, { hits, selectedHitId: 'b' })
    const html = f({ data: cell } as never)
    expect(html).toContain('hits 2/2</span> (2 events):')
    expect(html).toContain('step: z#0')
    expect(html).not.toContain('plateau: x#0')
  })

  it('只有一次的格:不写 hits ×n 与第几次,组成照写', () => {
    const f = buildMarkerTooltipFormatter(undefined, undefined, { hits })
    const html = f({ data: { hit_id: 'a' } } as never)
    expect(html).not.toContain('hits ×')
    expect(html).not.toContain('hits 1/')
    expect(html).toContain('组成 (1 events):')
  })
})

// ─── Task 9 · tooltip 实例级:formatter 直接把 data.instance_id 传给 tooltipResolver ──
// marker series data 恒带 instance_id(不再有 event_key/#idx 解析),resolver 按
// instance_id 展示【所悬停实例】的判定(多实例各判各的)。
describe('buildMarkerTooltipFormatter 实例级传递 (Task 9)', () => {
  const payloadOf = (instanceId: string) => ({
    identity: { nodes: [], dateStart: 'd', dateEnd: null, eventId: instanceId },
    clauses: [], raw: {}, refs: [],
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

  it('bracket data(hit_id)走 hitLabel + 组成段 · 不触发 resolver', () => {
    const resolver = vi.fn(() => payloadOf('x'))
    const hitLabel = vi.fn(() => 'ret_20: +5.0%')
    const hit = { hit_id: 'm9', children: ['a#0', 'b#0'],
                    node_index: { a: 'a#0', b: 'b#0' } } as unknown as HitDict
    const f = buildMarkerTooltipFormatter(resolver, hitLabel, { hits: [hit] })
    const html = f({ data: { hit_id: 'm9' } } as never)
    expect(html).toContain('ret_20: +5.0%')
    expect(html).toContain('a: a#0')
    expect(html).toContain('b: b#0')
    expect(resolver).not.toHaveBeenCalled()
  })
})
