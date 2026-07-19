/**
 * Task 2 · anchorsOf 表 + findBoBar helper + DEBUG_ENABLED_CLASSES 单元测试
 *
 * v2 契约:
 * - tb → 3 项(entry/trough/end),entry bar = findBoBar(anchor_bo_id, events)
 * - _default → [](防 "菜单显示但后端未埋 debug_break" 无声失败 · v2 D7)
 * - DEBUG_ENABLED_CLASSES 与 anchorsOf 硬耦合,单一 source of truth(v2 D8)
 */
import { describe, it, expect } from 'vitest'
import { anchorsOf, findBoBar, DEBUG_ENABLED_CLASSES } from '../src/stores/view'

function mkTbEvent(overrides: Partial<any> = {}): any {
  return {
    event_id: 'tb_1', class_id: 'tb',
    start_idx: 42, end_idx: 55,
    anchor_bo_id: 'bo_1',
    ...overrides,
  }
}

function mkBoEvent(overrides: Partial<any> = {}): any {
  return {
    event_id: 'bo_1', class_id: 'bo',
    start_idx: 30, end_idx: 30,
    ...overrides,
  }
}

describe('anchorsOf', () => {
  it('tb → 3 项 · entry/trough/end 顺序', () => {
    const tb = mkTbEvent()
    const bo = mkBoEvent()
    const anchors = anchorsOf.tb(tb, [bo, tb])
    expect(anchors).toHaveLength(3)
    expect(anchors.map(a => a.key)).toEqual(['entry', 'trough', 'end'])
  })

  it('tb entry bar = findBoBar(anchor_bo_id, events)', () => {
    const tb = mkTbEvent({ anchor_bo_id: 'bo_1' })
    const bo = mkBoEvent({ event_id: 'bo_1', end_idx: 33 })
    const anchors = anchorsOf.tb(tb, [bo, tb])
    const entry = anchors.find(a => a.key === 'entry')!
    expect(entry.bar).toBe(33)
    expect(entry.disabled).toBeFalsy()
  })

  it('tb trough bar = event.start_idx', () => {
    const tb = mkTbEvent({ start_idx: 44 })
    const bo = mkBoEvent()
    const anchors = anchorsOf.tb(tb, [bo, tb])
    const trough = anchors.find(a => a.key === 'trough')!
    expect(trough.bar).toBe(44)
  })

  it('tb end bar = event.end_idx', () => {
    const tb = mkTbEvent({ end_idx: 57 })
    const bo = mkBoEvent()
    const anchors = anchorsOf.tb(tb, [bo, tb])
    const end = anchors.find(a => a.key === 'end')!
    expect(end.bar).toBe(57)
  })

  it('tb entry disabled when anchor_bo_id 反查失败(bo 不在 events)', () => {
    const tb = mkTbEvent({ anchor_bo_id: 'bo_missing' })
    const anchors = anchorsOf.tb(tb, [tb])  // events 里没有 bo
    const entry = anchors.find(a => a.key === 'entry')!
    expect(entry.disabled).toBe(true)
    expect(entry.disabledReason).toContain('未找到 anchor bo event')
  })

  it('_default → [](未埋点 class 不显示菜单项 · 防无声失败)', () => {
    const trend = { event_id: 't1', class_id: 'trend', start_idx: 10, end_idx: 20 }
    expect(anchorsOf._default(trend as any, [])).toEqual([])
  })
})

describe('findBoBar', () => {
  it('返回 bo.end_idx', () => {
    const bo = mkBoEvent({ event_id: 'bo_x', end_idx: 77 })
    expect(findBoBar('bo_x', [bo])).toBe(77)
  })

  it('bo 不存在返 null', () => {
    expect(findBoBar('bo_missing', [])).toBeNull()
  })

  it('event_id 匹配 · 不看 class_id', () => {
    const other = { event_id: 'x', class_id: 'other', end_idx: 88 } as any
    expect(findBoBar('x', [other])).toBe(88)
  })
})

describe('DEBUG_ENABLED_CLASSES', () => {
  it('含 tb', () => {
    expect(DEBUG_ENABLED_CLASSES).toContain('tb')
  })

  it('不含 _default(v2 D8 硬耦合过滤)', () => {
    expect(DEBUG_ENABLED_CLASSES).not.toContain('_default')
  })
})
