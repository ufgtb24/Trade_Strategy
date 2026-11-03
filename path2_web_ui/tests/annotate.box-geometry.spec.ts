// 画框手势的判定与副图特征轨的几何:拖动阈值、框边、改起止、起止日期与下标互换、成交量带平移、
// 轨的位置与 option(框画虚线、选中的填浅灰、轨标题、框旁的标记)、bracket 轨、主图上标出的范围、样本的三角与暗一档。
import { describe, it, expect } from 'vitest'
import {
  DRAG_PX, EDGE_PX, boxAt, edgeOf, endIndex, isDrag, pannedZoom, resized, spanOf, startIndex,
} from '../src/annotate/boxGeometry'
import {
  AWAY_OPACITY, BOX_DASH, CAND_DASH, DIM_OPACITY, LANE_PAD, LANE_ROW_H, LANES_TOP, MEMBER_DASH, NEG_FILL, POS_FILL,
  TRI_GAP, TRI_H, afterDimSeries, bracketGeometry, bracketRects, buildAnnotateSubOption, laneAt, laneGeometry,
  mainMarksSeries, mainSamplesSeries, packBrackets, triangleRect, type BracketItem,
} from '../src/render/annotateLanes'
import { SUB_CANVAS_MIN_H } from '../src/render/subGeometry'
import type { Lane } from '../src/annotate/model'
import type { BoxMark } from '../src/annotate/samples'

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
    const el = opt.series[0].renderItem({ dataIndex: 1 }, api).children[0]
    expect(el.shape.x).toBe(10)
    expect(el.shape.width).toBe(30)
    expect(el.style.lineDash).toEqual(BOX_DASH)      // 用户画的:虚线
  })
  it('框的标记:选中样本时成员框加粗长虚线、画了没收的短虚线挂 ◂、跨过样本日的画淡挂 ⇥;框左侧写收了它的样本字母', () => {
    const { geom } = laneGeometry(lanes)
    const marks = new Map<string, BoxMark>([
      ['b1', { owners: ['a', 'b'], away: false, focus: 'member' }],
      ['b2', { owners: [], away: false, focus: 'cand' }],
      ['b3', { owners: [], away: false, focus: 'cross' }],
    ])
    const opt: any = buildAnnotateSubOption(DATES.map(date => ({ date } as any)), {
      lanes, geom, nameOf: () => 'x', selectedId: null, preview: null, draft: null, zoom: null, width: 800, marks,
    })
    const rows = opt.series[0].data
    const draw = (i: number) => opt.series[0].renderItem({ dataIndex: i },
      { size: () => [10], coord: ([k]: number[]) => [k * 10 + 5], value: (k: number) => rows[i][k] }).children
    const [r1, owners] = draw(0)
    expect([r1.style.lineWidth, r1.style.lineDash, r1.style.opacity]).toEqual([2.5, MEMBER_DASH, 1])
    expect([owners.style.text, owners.style.align]).toEqual(['a b', 'right'])
    const [r2, take] = draw(1)
    expect([r2.style.lineDash, take.style.text]).toEqual([CAND_DASH, '◂'])
    const [r3, cross] = draw(2)
    expect([r3.style.opacity, cross.style.text]).toEqual([DIM_OPACITY, '⇥'])
  })

  it('bracket 轨:在最上面、特征轨接在它下面;样本跨度按行排开,虚线,右端是样本的三角', () => {
    const items: BracketItem[] = [
      { id: 's1', start: '2025-01-02', end: '2025-01-06', pos: true, letter: 'a', faded: false, emphasis: 2 },
      { id: 's2', start: '2025-01-03', end: '2025-01-07', pos: false, letter: null, faded: true, emphasis: 0 },
    ]
    const { rows, placed } = packBrackets(items, DATES)
    expect(rows).toBe(2)
    const bg = bracketGeometry(rows)
    expect(bg.top).toBe(LANES_TOP)
    const { geom } = laneGeometry(lanes, bg.top + bg.h)
    expect(geom[0].top).toBe(bg.top + bg.h)
    const opt: any = buildAnnotateSubOption(DATES.map(date => ({ date } as any)), {
      lanes, geom, nameOf: () => 'x', selectedId: null, preview: null, draft: null, zoom: null, width: 800,
      bracket: { geom: bg, placed },
    })
    expect(opt.graphic.find((g: any) => g.type === 'text').style.text).toBe('bracket')
    const br = opt.series[1]
    expect(br.data.map((r: number[]) => [r[0], r[1]])).toEqual([[0, 2], [1, 3]])
    const draw = (i: number) => br.renderItem({ dataIndex: i },
      { size: () => [10], coord: ([k]: number[]) => [k * 10 + 5], value: (k: number) => br.data[i][k] }).children
    const [rect, tri, letter] = draw(0)
    expect([rect.style.lineDash, rect.style.lineWidth, tri.style.fill, letter.style.text]).toEqual([BOX_DASH, 2.5, POS_FILL, 'a'])
    const [rect2, tri2] = draw(1)
    expect([rect2.style.opacity, tri2.style.fill]).toEqual([AWAY_OPACITY, NEG_FILL])
    const px = bracketRects(placed, bg, DATES, i => i * 10 + 5, 10)
    expect(px.map(r => [r.id, r.left, r.right])).toEqual([['s1', 0, 30], ['s2', 10, 40]])
  })

  it('主图:正样本实心、负样本空心的三角,选中的线加粗;选中样本时样本日之后盖一层暗一档', () => {
    const bars = DATES.map((date, i) => ({ date, l: 10 + i } as any))
    const s: any = mainSamplesSeries(bars, [
      { id: 's1', date: '2025-01-03', pos: true, selected: true, faded: false, letter: 'a' },
      { id: 's2', date: '2025-01-06', pos: false, selected: false, faded: true, letter: null },
      { id: 's3', date: '2030-01-01', pos: true, selected: false, faded: false, letter: null },
    ])
    expect(s.data).toEqual([[1, 11], [2, 12]])
    const api = (i: number) => ({ coord: ([k, y]: number[]) => [k * 10, 100 - y], value: (k: number) => s.data[i][k] })
    const [t1, l1] = s.renderItem({ dataIndex: 0 }, api(0)).children
    expect([t1.style.fill, t1.style.lineWidth, l1.style.text]).toEqual([POS_FILL, 3, 'a'])
    expect(t1.shape.points[0]).toEqual([10, 89 + TRI_GAP])
    const [t2] = s.renderItem({ dataIndex: 1 }, api(1)).children
    expect([t2.style.fill, t2.style.opacity]).toEqual([NEG_FILL, AWAY_OPACITY])
    const r = triangleRect(10, 89)
    expect(r.top <= 89 + TRI_GAP && r.bottom >= 89 + TRI_GAP + TRI_H).toBe(true)

    const d: any = afterDimSeries(DATES, '2025-01-03')
    expect(d.data).toEqual([[2, DATES.length - 1]])
    expect(d.z).toBeGreaterThan(2)            // 压在 K 线(z 2)上面
    expect(afterDimSeries(DATES, null).data).toEqual([])
    expect(afterDimSeries(DATES, DATES.at(-1)!).data).toEqual([])
  })

  it('主图上标出选中的框与正在拖的框,整根 K 线对齐', () => {
    const s: any = mainMarksSeries(DATES, { start: '2025-01-03', end: '2025-01-06' }, null)
    expect(s.data).toEqual([[1, 2, 1]])
    const api = { size: () => [10], coord: ([i]: number[]) => [i * 10 + 5], value: (k: number) => s.data[0][k] }
    const el = s.renderItem({ coordSys: { x: 0, y: 40, width: 50, height: 300 } }, api)
    expect(el.shape).toEqual({ x: 10, y: 40, width: 20, height: 300 })
  })
})
