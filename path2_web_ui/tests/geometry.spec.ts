import { describe, it, expect } from 'vitest'
import { splitGeometry, packLanes, packBrackets, packByBand } from '../src/render/geometry'
import type { EventDict } from '../src/types'

describe('geometry', () => {
  it('splitGeometry separates points and intervals', () => {
    const { points, intervals } = splitGeometry([
      { instance_id: 'p#0', node_id: 't', instance_idx: 0, start_idx: 5, end_idx: 5 },
      { instance_id: 'i#0', node_id: 't', instance_idx: 0, start_idx: 2, end_idx: 8 },
    ] as any)
    expect(points.map(p => p.instance_id)).toEqual(['p#0'])
    expect(intervals.map(i => i.instance_id)).toEqual(['i#0'])
  })

  it('packLanes assigns non-overlapping intervals to lane 0, overlaps stack', () => {
    const packed = packLanes([
      { start_idx: 0, end_idx: 3 }, { start_idx: 5, end_idx: 8 },   // 不重叠 → 同 lane
      { start_idx: 2, end_idx: 6 },                                  // 与前两个重叠 → lane 1
    ] as any)
    const lanes = packed.map(p => p.lane)
    expect(packed.find(p => p.start_idx === 0)!.lane).toBe(0)
    expect(packed.find(p => p.start_idx === 5)!.lane).toBe(0)        // 0-3 之后,复用 lane 0
    expect(packed.find(p => p.start_idx === 2)!.lane).toBe(1)        // 与 0-3 重叠 → 新 lane
    expect(Math.max(...lanes)).toBe(1)
  })

  it('packBrackets packs match spans by lane', () => {
    const b = packBrackets([
      { match_id: 'm1', start_idx: 0, end_idx: 10 },
      { match_id: 'm2', start_idx: 3, end_idx: 7 },   // 重叠 → lane 1
    ] as any)
    expect(b.find(x => x.match_id === 'm1')!.lane).toBe(0)
    expect(b.find(x => x.match_id === 'm2')!.lane).toBe(1)
    // 带序号(1-based)
    expect(b.find(x => x.match_id === 'm1')!.ordinal).toBe(1)
  })

  it('packLanes: inclusive spans sharing a bar take different lanes', () => {
    // 0-based inclusive:[0,3] 与 [3,7] 共享 bar 3 → 视为重叠 → strict < 应分到不同 lane
    const p = packLanes([
      { start_idx: 0, end_idx: 3 }, { start_idx: 3, end_idx: 7 },
    ] as any)
    expect(p.find(x => x.start_idx === 0)!.lane).toBe(0)
    expect(p.find(x => x.start_idx === 3)!.lane).toBe(1)
  })
})

const evB = (id: string, st: string, s: number, e: number): EventDict =>
  ({ instance_id: id + '#0', node_id: st, instance_idx: 0, start_idx: s, end_idx: e, child_refs: {} })

describe('packByBand', () => {
  it('每 band 独立 packLanes,band 内重叠才分 lane', () => {
    const items = [evB('a','trend0',0,5), evB('b','trend0',2,7), evB('c','trend1',0,5)]
    const out = packByBand(items, ['trend0','trend1'], (e) => e.node_id)
    const a = out.find(o => o.instance_id === 'a#0')!, b = out.find(o => o.instance_id === 'b#0')!, c = out.find(o => o.instance_id === 'c#0')!
    expect(a.band).toBe(0); expect(c.band).toBe(1)
    expect(a.nBands).toBe(2)
    expect(a.lane).not.toBe(b.lane)            // 同 band 重叠 → 不同 lane
    expect(c.lane).toBe(0)                     // 另一 band lane 重置
  })
  it('空 band 不产出;band 序即 bandOrder 序', () => {
    const out = packByBand([evB('x','bo',0,0)], ['trend0','bo'], (e) => e.node_id)
    expect(out.length).toBe(1)
    expect(out[0].band).toBe(1)                // bo 是 bandOrder[1]
  })

  it('同 band 内 spot (start=end) 与 span 同 start_idx 分到不同 lane', () => {
    // 混合输入:spot start=end=3, span start=3 end=8, 同 band=trend0
    // packLanes 的 strict < 语义应让二者一定分到不同 lane
    const items = [
      evB('spot', 'trend0', 3, 3),
      evB('span', 'trend0', 3, 8),
    ]
    const out = packByBand(items, ['trend0'], (e) => e.node_id)
    const spot = out.find(o => o.instance_id === 'spot#0')!
    const span = out.find(o => o.instance_id === 'span#0')!
    expect(spot.band).toBe(0)
    expect(span.band).toBe(0)
    expect(spot.lane).not.toBe(span.lane)
  })

  it('同 band 内多 spot 同 start_idx 分到不同 lane', () => {
    // 3 个 spot 同 bar (start=end=5), 同 band
    // packLanes strict < → 三个 lane 号必两两不同
    const items = [
      evB('s1', 'trend0', 5, 5),
      evB('s2', 'trend0', 5, 5),
      evB('s3', 'trend0', 5, 5),
    ]
    const out = packByBand(items, ['trend0'], (e) => e.node_id)
    const lanes = out.map(o => o.lane).sort()
    expect(lanes).toEqual([0, 1, 2])
  })
})
