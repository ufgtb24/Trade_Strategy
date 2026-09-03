// peakState.spec.ts — pk 三态合成(契约 C4)+ pk_id 反查索引(契约 C5 消费者)的纯函数单测。
import { describe, it, expect } from 'vitest'
import { derivePeakStates, peakIdIndex } from '../src/render/peakState'
import type { EventDict } from '../src/types'

const mkPk = (instance_id: string, pk_id: number, ref_ids?: Record<string, string[]>): EventDict =>
  ({ instance_id, node_id: 'pk', instance_idx: 0, start_idx: 0, end_idx: 0,
     peak_idx: 0, pk_id, ...(ref_ids ? { ref_ids } : {}) } as any)

const mkBo = (instance_id: string, ref_ids: Record<string, string[]>): EventDict =>
  ({ instance_id, node_id: 'bo', instance_idx: 0, start_idx: 1, end_idx: 1, ref_ids } as any)

describe('derivePeakStates(契约 C4)', () => {
  it('bo ref_ids.broken=[pkA] → pkA=broken;pk ref_ids.superseded=[pkC] → pkC=eaten;其余 alive', () => {
    const pkA = mkPk('pkA#0', 1)
    const pkB = mkPk('pkB#0', 2)
    const pkC = mkPk('pkC#0', 3)
    const pkElevated = mkPk('pkElevated#0', 4, { superseded: ['pkC#0'] })
    const bo = mkBo('bo#0', { broken: ['pkA#0'] })
    const states = derivePeakStates([pkA, pkB, pkC, pkElevated, bo])
    expect(states.get('pkA#0')).toBe('broken')
    expect(states.get('pkC#0')).toBe('eaten')
    expect(states.get('pkB#0')).toBe('alive')
  })

  it('elevation 后被吃:同一 pk 同时出现在 broken 与 superseded 里 → broken(优先于 eaten)', () => {
    const pkA = mkPk('pkA#0', 1)
    const boBroken = mkBo('bo1#0', { broken: ['pkA#0'] })
    const pkSupersede = mkPk('pkSup#0', 2, { superseded: ['pkA#0'] })
    const states = derivePeakStates([pkA, boBroken, pkSupersede])
    expect(states.get('pkA#0')).toBe('broken')
  })

  it('多 bo 反复突破同一 pk → 仍是 broken(集合语义,非计数)', () => {
    const pkA = mkPk('pkA#0', 1)
    const bo1 = mkBo('bo1#0', { broken: ['pkA#0'] })
    const bo2 = mkBo('bo2#0', { broken: ['pkA#0'] })
    const bo3 = mkBo('bo3#0', { broken: ['pkA#0'] })
    const states = derivePeakStates([pkA, bo1, bo2, bo3])
    expect(states.get('pkA#0')).toBe('broken')
  })

  it('非 pk 事件(无 peak_idx)不进结果,即便自身带 ref_ids 或被别的事件引用', () => {
    const bo = mkBo('bo#0', { broken: ['ghost#0'] })
    const states = derivePeakStates([bo])
    expect(states.has('bo#0')).toBe(false)
    expect(states.has('ghost#0')).toBe(false)
  })
})

describe('peakIdIndex(契约 C5 消费者):instance_id → pk_id', () => {
  it('只收 pk 事件(带 peak_idx),bo 等其他事件不进索引', () => {
    const pkA = mkPk('pkA#0', 7)
    const bo = mkBo('bo#0', {})
    const idx = peakIdIndex([pkA, bo])
    expect(idx.get('pkA#0')).toBe(7)
    expect(idx.has('bo#0')).toBe(false)
  })

  it('多个 pk 各自的 pk_id 都能查到', () => {
    const idx = peakIdIndex([mkPk('a#0', 1), mkPk('b#0', 2), mkPk('c#0', 3)])
    expect(idx.get('a#0')).toBe(1)
    expect(idx.get('b#0')).toBe(2)
    expect(idx.get('c#0')).toBe(3)
  })
})
