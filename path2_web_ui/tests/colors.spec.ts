import { describe, it, expect } from 'vitest'
import { deriveRoleColors, colorOf } from '../src/render/colors'
import { PATTERN } from './fixtures'

describe('deriveRoleColors', () => {
  it('single-role class_id uses base color', () => {
    const c = deriveRoleColors(PATTERN.topology, PATTERN.event_styles)
    expect(c.bo).toBe('#2563eb')        // bo 仅 bo 一个 role → 原色
    expect(c.tb).toBe('#16a34a')        // tb 仅 tb
  })
  it('same class_id multi-role get distinct lightness variants', () => {
    const c = deriveRoleColors(PATTERN.topology, PATTERN.event_styles)
    // down/side 同 trend → 两个不同色(都非空、互异)
    expect(c.down).toBeTruthy()
    expect(c.side).toBeTruthy()
    expect(c.down).not.toBe(c.side)
  })
  it('is deterministic (order from topology.nodes)', () => {
    const a = deriveRoleColors(PATTERN.topology, PATTERN.event_styles)
    const b = deriveRoleColors(PATTERN.topology, PATTERN.event_styles)
    expect(a).toEqual(b)
  })
  it('missing event_style falls back to neutral', () => {
    const c = deriveRoleColors(
      { nodes: [{ node_id: 'x', class_id: 'unknown', label: '', source_tag: 'unknown', where_rules: [] }], edges: [] },
      {})
    expect(c.x).toMatch(/^#/)
  })
})

describe('colorOf tier', () => {
  it('matched→roleColor / qualified→深灰 / detected→浅灰', () => {
    const rc = { burst: '#ff0000' }
    expect(colorOf('matched', 'burst', rc)).toBe('#ff0000')
    expect(colorOf('qualified', 'burst', rc)).toBe('#9ca3af')
    expect(colorOf('detected', 'burst', rc)).toBe('#d1d5db')
  })
  it('matched + role 缺色 → NEUTRAL 兜底', () => {
    expect(colorOf('matched', 'unknown', {})).toBe('#888888')
    expect(colorOf('matched', null, {})).toBe('#888888')
  })
})
