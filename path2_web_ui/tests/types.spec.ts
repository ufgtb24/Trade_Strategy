import { describe, it, expect } from 'vitest'
import { PATTERN, ANALYSIS, SCAN_FILE, DIAG } from './fixtures'
import { isPoint } from '../src/types'

describe('types', () => {
  it('fixtures conform (compiles) and helpers work', () => {
    expect(PATTERN.pattern_id).toBe('bottom_breakout_burst')
    expect(SCAN_FILE.results[0].per_pattern['bottom_breakout_burst'].analysis.matches.length).toBe(1)
    expect(DIAG.nodes.bo.rel[0].ok_count).toBe(1)
    // 几何自描述
    expect(isPoint(ANALYSIS.events.find(e => e.event_id === 'bo9')!)).toBe(true)
    expect(isPoint(ANALYSIS.events.find(e => e.event_id === 'down1')!)).toBe(false)
    // render_grid 字段 (新增)
    const boNode = PATTERN.topology.nodes.find(n => n.node_id === 'bo')!
    expect(boNode.render_grid).toBe('price')
    const tbNode = PATTERN.topology.nodes.find(n => n.node_id === 'tb')!
    // render_grid 是可选字段, 不显式声明时 fixture 也不写
    expect(tbNode.render_grid === undefined || tbNode.render_grid === 'time').toBe(true)
    // referenced_points 字段 (新增)
    const bo9 = ANALYSIS.events.find(e => e.event_id === 'bo9')!
    expect(Array.isArray(bo9.referenced_points)).toBe(true)
  })
})
