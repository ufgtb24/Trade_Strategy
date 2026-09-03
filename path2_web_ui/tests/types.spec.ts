import { describe, it, expect } from 'vitest'
import { PATTERN, ANALYSIS, SCAN_FILE, DIAG } from './fixtures'
import { isPoint } from '../src/types'

describe('types', () => {
  it('fixtures conform (compiles) and helpers work', () => {
    expect(PATTERN.pattern_id).toBe('bottom_burst')
    expect(SCAN_FILE.results[0].per_pattern['bottom_burst'].analysis.matches.length).toBe(1)
    expect(DIAG.nodes.bo.rel[0].ok_count).toBe(1)
    // 几何自描述
    expect(isPoint(ANALYSIS.events.find(e => e.instance_id === 'bo_9#0')!)).toBe(true)
    expect(isPoint(ANALYSIS.events.find(e => e.instance_id === 'down_1_6#0')!)).toBe(false)
    // render_grid 字段 (新增)
    const boNode = PATTERN.topology.nodes.find(n => n.node_id === 'bo')!
    expect(boNode.render_grid).toBe('price')
    const tbNode = PATTERN.topology.nodes.find(n => n.node_id === 'tb')!
    // render_grid 是可选字段, 不显式声明时 fixture 也不写
    expect(tbNode.render_grid === undefined || tbNode.render_grid === 'time').toBe(true)
    // referenced_points 已取消(Task 2 后端删除 BOEvent.referenced_points,前端类型同步移除)
    const bo9 = ANALYSIS.events.find(e => e.instance_id === 'bo_9#0')!
    expect((bo9 as any).referenced_points).toBeUndefined()
  })
})
