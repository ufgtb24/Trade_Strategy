/**
 * Task 8 · splitIntervalAtScanEnd 纯函数 + computeEventData 消费端测试
 * (tb v4 状态机 spec §10 样本消费窗截取的 UI 面)。
 *
 * 语义:后端把样本统计截到 [start_ts, end_ts],但 events 全量下发(机器在尾缓冲区
 * 的轨迹有意可见)。副图 band interval 与 scanEnd(= scan.end_date 的 bar 索引,
 * 即 strictWindow.endIdx)相交时拆两段:
 *   - 窗内段:维持三档 level 色(matched 彩色)
 *   - 窗后段:detected 灰(#d1d5db,与 detected/traced 灰色语义同族 =「检测到但非样本」)
 * 边界:scanEndIdx 本身归窗内(与主图 buildShadingMarkArea 从 endIdx+1 起灰同一口径)。
 *
 * strictWindow 缺省(null)不拆 —— 与主图 shading 同门控,旧调用零回归。
 */
import { describe, it, expect } from 'vitest'
import { splitIntervalAtScanEnd } from '../src/render/visible'
import { computeEventData } from '../src/render/chart'
import type { BandRenderInput } from '../src/render/chart'
import type { Bar, EventDict, MatchDict } from '../src/types'

describe('splitIntervalAtScanEnd(纯函数)', () => {
  it('完全窗内(end <= scanEndIdx)→ [原区间],窗内段', () => {
    expect(splitIntervalAtScanEnd({ start: 10, end: 20 }, 30))
      .toEqual([{ start: 10, end: 20, afterWindow: false }])
  })

  it('完全窗外(start > scanEndIdx)→ [原区间(窗后)]', () => {
    expect(splitIntervalAtScanEnd({ start: 35, end: 40 }, 30))
      .toEqual([{ start: 35, end: 40, afterWindow: true }])
  })

  it('跨界 → [窗内段(…scanEndIdx), 窗后段(scanEndIdx+1…)],按时间序', () => {
    expect(splitIntervalAtScanEnd({ start: 10, end: 40 }, 30))
      .toEqual([
        { start: 10, end: 30, afterWindow: false },
        { start: 31, end: 40, afterWindow: true },
      ])
  })

  it('边界:end === scanEndIdx 本身归窗内(单段,不拆)', () => {
    expect(splitIntervalAtScanEnd({ start: 25, end: 30 }, 30))
      .toEqual([{ start: 25, end: 30, afterWindow: false }])
  })

  it('边界:start === scanEndIdx + 1 → 完全窗外', () => {
    expect(splitIntervalAtScanEnd({ start: 31, end: 40 }, 30))
      .toEqual([{ start: 31, end: 40, afterWindow: true }])
  })

  it('退化跨界:start === scanEndIdx → 窗内段坍缩为单 bar [scanEndIdx, scanEndIdx]', () => {
    expect(splitIntervalAtScanEnd({ start: 30, end: 40 }, 30))
      .toEqual([
        { start: 30, end: 30, afterWindow: false },
        { start: 31, end: 40, afterWindow: true },
      ])
  })
})

// ─── 消费端:computeEventData 在 strictWindow.endIdx 处拆 intervalData ───────

const bars: Bar[] = Array.from({ length: 5 }, (_, i) => ({
  date: `2025-01-0${i + 1}`, o: 10, c: 12, h: 13, l: 9, v: 100, rv: 0,
}))

function baseInput(strictWindow: BandRenderInput['strictWindow']): BandRenderInput {
  return {
    topology: { nodes: [{ node_id: 'tb_seg' }] } as any,
    isolatedNodeIds: new Set<string>(),
    tagList: ['tb_seg'],
    level: 'matched',
    nodeColors: { tb_seg: '#16a34a' },
    eventTier: () => 'matched',
    nodeOfEventByBand: (e) => e.node_id,
    bandKeyOf: (e) => e.node_id,
    strictWindow,
  }
}

describe('computeEventData — band interval 按 scanEnd 拆段', () => {
  const events: EventDict[] = [
    { instance_id: 'seg_cross#0', node_id: 'tb_seg', instance_idx: 0, start_idx: 2, end_idx: 4 },  // 跨界
    { instance_id: 'seg_after#0', node_id: 'tb_seg', instance_idx: 0, start_idx: 4, end_idx: 4 },  // 点(窗外)
  ]
  const matches: MatchDict[] = []

  it('strictWindow 缺省 → interval 不拆(老行为,单条原色)', () => {
    const bundle = computeEventData(bars, events, matches, baseInput(null))
    const cross = bundle.intervalData.filter((d) => d.instance_id === 'seg_cross#0')
    expect(cross).toHaveLength(1)
    expect(cross[0].value.slice(0, 2)).toEqual([2, 4])
    expect(cross[0].itemStyle.color).toBe('#16a34a')
  })

  it('跨界 interval → 两条记录:窗内段原 level 色、窗后段 detected 灰,同 lane/band/instance_id', () => {
    const bundle = computeEventData(bars, events, matches,
      baseInput({ startIdx: 0, endIdx: 3 }))
    const parts = bundle.intervalData.filter((d) => d.instance_id === 'seg_cross#0')
    expect(parts).toHaveLength(2)
    // 窗内段 [2,3]:matched 彩色(node 本色)
    expect(parts[0].value.slice(0, 2)).toEqual([2, 3])
    expect(parts[0].itemStyle.color).toBe('#16a34a')
    // 窗后段 [4,4]:detected 灰(colorOf('detected') = #d1d5db)
    expect(parts[1].value.slice(0, 2)).toEqual([4, 4])
    expect(parts[1].itemStyle.color).toBe('#d1d5db')
    // lane/band 不变(拆的是时间跨度,不占新轨道)
    expect(parts[0].value[2]).toBe(parts[1].value[2])
    expect(parts[0].value[3]).toBe(parts[1].value[3])
    expect(parts[1].tier).toBe('matched')
  })

  it('完全窗外 interval → 单条整段灰(机器轨迹可见但不计样本)', () => {
    const spanEvents: EventDict[] = [
      { instance_id: 'seg_after_all#0', node_id: 'tb_seg', instance_idx: 0, start_idx: 3, end_idx: 4 },
    ]
    const bundle = computeEventData(bars, spanEvents, matches,
      baseInput({ startIdx: 0, endIdx: 2 }))
    const parts = bundle.intervalData.filter((d) => d.instance_id === 'seg_after_all#0')
    expect(parts).toHaveLength(1)
    expect(parts[0].value.slice(0, 2)).toEqual([3, 4])
    expect(parts[0].itemStyle.color).toBe('#d1d5db')
  })

  it('point 事件不拆(本 task 范围 = interval band;窗外 point 维持原色)', () => {
    const bundle = computeEventData(bars, events, matches,
      baseInput({ startIdx: 0, endIdx: 3 }))
    const pts = bundle.pointData.filter((d) => d.instance_id === 'seg_after#0')
    expect(pts).toHaveLength(1)
    expect(pts[0].itemStyle.color).toBe('#16a34a')
  })
})
