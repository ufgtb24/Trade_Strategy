import { describe, it, expect } from 'vitest'
import { packLanes } from '../src/render/geometry'

describe('geometry', () => {
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

  it('packLanes: inclusive spans sharing a bar take different lanes', () => {
    // 0-based inclusive:[0,3] 与 [3,7] 共享 bar 3 → 视为重叠 → strict < 应分到不同 lane
    const p = packLanes([
      { start_idx: 0, end_idx: 3 }, { start_idx: 3, end_idx: 7 },
    ] as any)
    expect(p.find(x => x.start_idx === 0)!.lane).toBe(0)
    expect(p.find(x => x.start_idx === 3)!.lane).toBe(1)
  })
})
