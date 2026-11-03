// 画框手势的判定与副图特征轨的几何:拖动阈值、框边、改起止、起止日期与下标互换、成交量带平移、
// 轨的位置与 option(框画虚线、选中的填浅灰、轨标题)、主图上标出的范围。
import { describe, it, expect } from 'vitest'
import {
  DRAG_PX, EDGE_PX, boxAt, edgeOf, endIndex, isDrag, pannedZoom, resized, spanOf, startIndex,
} from '../src/annotate/boxGeometry'
import {
  BOX_DASH, LANE_PAD, LANE_ROW_H, LANES_TOP, buildAnnotateSubOption, laneAt, laneGeometry, mainMarksSeries,
} from '../src/render/annotateLanes'
import { SUB_CANVAS_MIN_H } from '../src/render/subGeometry'
import type { Lane } from '../src/annotate/model'

const DATES = ['2025-01-02', '2025-01-03', '2025-01-06', '2025-01-07', '2025-01-08']

describe('手势判定', () => {
  it(`移动超过 ${DRAG_PX} 像素才算拖动`, () => {
    expect(isDrag(0, 0, DRAG_PX, 0)).toBe(false)
    expect(isDrag(0, 0, DRAG_PX + 1, 0)).toBe(true)
  })
  it('起止左小右大;改起止不越过另一端', () => {
    expect(spanOf(7, 3)).toEqual([3, 7])
    expect(resized(3, 7, 'l', 9)).toEqual([7, 7])
    expect(resized(3, 7, 'r', 1)).toEqual([3, 3])
    expect(resized(3, 7, 'r', 9)).toEqual([3, 9])
  })
  it(`框边 ${EDGE_PX} 像素以内才算按在边上`, () => {
    const r = { id: 'b', left: 100, right: 200, top: 0, bottom: 10 }
    expect(edgeOf(r, 100 + EDGE_PX)).toBe('l')
    expect(edgeOf(r, 200 - EDGE_PX)).toBe('r')
    expect(edgeOf(r, 150)).toBeNull()
    expect(boxAt([r], 150, 5)?.id).toBe('b')
    expect(boxAt([r], 150, 11)).toBeNull()
  })
  it('起止日期 → K 线下标:起点取当天或之后,终点取当天或之前', () => {
    expect(startIndex(DATES, '2025-01-04')).toBe(2)
    expect(endIndex(DATES, '2025-01-04')).toBe(1)
    expect(endIndex(DATES, '2025-01-07')).toBe(3)
  })
  it('成交量带上往右拖看更早的 K 线,图窗宽度不变、不出界', () => {
    expect(pannedZoom(50, 70, 100, 1000)).toEqual({ start: 48, end: 68 })
    expect(pannedZoom(2, 22, 1000, 1000)).toEqual({ start: 0, end: 20 })
    expect(pannedZoom(80, 100, -1000, 1000)).toEqual({ start: 80, end: 100 })
  })
})

describe('特征轨', () => {
  const box = (id: string, start: string, end: string) => ({ id, feature: 'w1', start, end })
  const lanes: Lane[] = [
    { key: 'w1', parent: null, rows: 2, boxes: [{ box: box('b1', '2025-01-02', '2025-01-06'), row: 0 },
                                                 { box: box('b2', '2025-01-03', '2025-01-07'), row: 1 }] },
    { key: 'w2', parent: 'w1', rows: 1, boxes: [{ box: { ...box('b3', '2025-01-06', '2025-01-06'), feature: 'w2' }, row: 0 }] },
  ]
  it('轨从上往下排,高度随行数;总高至少是副图的兜底高度', () => {
    const { geom, height } = laneGeometry(lanes)
    expect(geom[0]).toEqual({ top: LANES_TOP, h: 2 * LANE_PAD + 2 * LANE_ROW_H })
    expect(geom[1].top).toBe(geom[0].top + geom[0].h)
    expect(height).toBe(Math.max(SUB_CANVAS_MIN_H, geom[1].top + geom[1].h + LANES_TOP))
    expect(laneAt(geom, geom[1].top + 1)).toBe(1)
    expect(laneAt(geom, 0)).toBe(-1)
  })
  it('option:每个框一行数据、选中的标出来;子框轨标题写成「名 ⊂ 父名」;拖动不平移', () => {
    const { geom } = laneGeometry(lanes)
    const names: Record<string, string> = { w1: '横盘', w2: '缩量' }
    const opt: any = buildAnnotateSubOption(DATES.map(date => ({ date } as any)), {
      lanes, geom, nameOf: f => (f ? names[f] : null), selectedId: 'b2', preview: null,
      draft: { start: '2025-01-07', end: '2025-01-08', lane: 0 }, zoom: { start: 0, end: 100 }, width: 800,
    })
    const rows = opt.series[0].data
    expect(rows.map((r: any[]) => [r[6], r[0], r[1], r[4], r[5]])).toEqual([
      ['b1', 0, 2, 0, 0], ['b2', 1, 3, 1, 0], ['b3', 2, 2, 0, 0], ['__draft', 3, 4, 0, 1]])
    const titles = opt.graphic.filter((g: any) => g.type === 'text').map((g: any) => g.style.text)
    expect(titles).toEqual(['{biz|横盘}', '{biz|缩量}{sym| ⊂ }{biz|横盘}'])
    expect(opt.dataZoom[0].moveOnMouseMove).toBe(false)
    const api = { size: () => [10], coord: ([i]: number[]) => [i * 10 + 5], value: (k: number) => rows[1][k] }
    const el = opt.series[0].renderItem({}, api)
    expect(el.shape.x).toBe(10)
    expect(el.shape.width).toBe(30)
    expect(el.style.lineDash).toEqual(BOX_DASH)      // 用户画的:虚线
  })
  it('主图上标出选中的框与正在拖的框,整根 K 线对齐', () => {
    const s: any = mainMarksSeries(DATES, { start: '2025-01-03', end: '2025-01-06' }, null)
    expect(s.data).toEqual([[1, 2, 1]])
    const api = { size: () => [10], coord: ([i]: number[]) => [i * 10 + 5], value: (k: number) => s.data[0][k] }
    const el = s.renderItem({ coordSys: { x: 0, y: 40, width: 50, height: 300 } }, api)
    expect(el.shape).toEqual({ x: 10, y: 40, width: 20, height: 300 })
  })
})
