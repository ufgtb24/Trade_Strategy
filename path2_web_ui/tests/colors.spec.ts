import { describe, it, expect } from 'vitest'
import { deriveNodeColors, colorOf } from '../src/render/colors'
import { PATTERN } from './fixtures'

describe('deriveNodeColors', () => {
  it('single-node node_id uses base color', () => {
    const c = deriveNodeColors(PATTERN.topology, PATTERN.event_styles)
    expect(c.bo).toBe('#2563eb')        // bo 仅 bo 一个 node → 原色
    expect(c.tb).toBe('#16a34a')        // tb 仅 tb
  })
  it('nodes sharing a color keep it (no lightness spreading)', () => {
    const c = deriveNodeColors(PATTERN.topology, PATTERN.event_styles)
    // down/side 的 event_styles 同色 → 照原色,不散开明度(两色交替的调色板隔一条轨本来就同色)
    expect(c.down).toBe(PATTERN.event_styles.down)
    expect(c.side).toBe(c.down)
  })
  it('is deterministic (order from topology.nodes)', () => {
    const a = deriveNodeColors(PATTERN.topology, PATTERN.event_styles)
    const b = deriveNodeColors(PATTERN.topology, PATTERN.event_styles)
    expect(a).toEqual(b)
  })
  it('missing event_style falls back to neutral', () => {
    const c = deriveNodeColors(
      { nodes: [{ node_id: 'x', where_rules: [] }], edges: [] },
      {})
    expect(c.x).toMatch(/^#/)
  })
})

describe('colorOf tier', () => {
  it('in_hit→nodeColor / qualified→深灰 / detected→浅灰', () => {
    const rc = { burst: '#ff0000' }
    expect(colorOf('in_hit', 'burst', rc)).toBe('#ff0000')
    expect(colorOf('qualified', 'burst', rc)).toBe('#9ca3af')
    expect(colorOf('detected', 'burst', rc)).toBe('#b4bac2')
  })
  it('in_hit + node 缺色 → NEUTRAL 兜底', () => {
    expect(colorOf('in_hit', 'unknown', {})).toBe('#888888')
    expect(colorOf('in_hit', null, {})).toBe('#888888')
  })
})

