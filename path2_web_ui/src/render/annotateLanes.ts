/**
 * annotate 下的副图:一个特征一条轨,用户的框画在自己特征的轨上(虚线:全界面虚线只表示「用户画的」)。
 * 轨的排法(轨序、子框轨、交叠的框分行)由 annotate/model.ts 的 computeLanes 给;本模块只管几何与画法,
 * 以及主图 K 线区上「选中的框」「正在拖的框」的那一层。
 *
 * 配色:框和文字一律黑(#111),选中的框填浅灰;不引入新色相。轨标题里的特征名是用户写的内容,
 * 用正常字体加浅灰底(--chip-bg 同值),「⊂」与 unnamed 是程序固定文字,用等宽字体。
 */
import type { Bar } from '../types'
import type { AnnBox, Lane } from '../annotate/model'
import { endIndex, startIndex, type BoxPx } from '../annotate/boxGeometry'
import { SUB_CANVAS_MIN_H, SUB_GRID_LEFT, SUB_GRID_RIGHT } from './subGeometry'

export const LANE_ROW_H = 18          // 轨里一行的高度
export const LANE_BOX_H = 13          // 框的高度(行高减去上下空隙)
export const LANE_PAD = 4             // 轨的上下内边距
export const LANES_TOP = 4            // 第一条轨上方留白

export const INK = '#111'             // 文字与框线一律黑
export const CHIP_BG = '#f4f4f5'      // 用户写的内容(不在输入框里)的浅灰底,同 App.vue 的 --chip-bg
export const LANE_LINE = '#e4e4e7'    // 轨之间的分隔线,同 --line-soft
export const SELECTED_FILL = 'rgba(0,0,0,0.10)'   // 选中的框:填浅灰(填充只表示「选中」)
export const BOX_DASH = [5, 3]        // 用户的框:虚线
export const DRAFT_DASH = [2, 2]      // 正在拖出的框:短虚线
export const MONO = 'ui-monospace, "JetBrains Mono", "DejaVu Sans Mono", Consolas, monospace'

export interface LaneGeom { top: number; h: number }

/** 每条轨的位置与高度,以及副图需要的总高(至少 SUB_CANVAS_MIN_H)。 */
export function laneGeometry(lanes: readonly Lane[]): { geom: LaneGeom[]; height: number } {
  const geom: LaneGeom[] = []
  let y = LANES_TOP
  for (const l of lanes) {
    const h = LANE_PAD * 2 + l.rows * LANE_ROW_H
    geom.push({ top: y, h })
    y += h
  }
  return { geom, height: Math.max(SUB_CANVAS_MIN_H, y + LANES_TOP) }
}

/** 落在哪条轨上(按 y);不在任何轨上为 -1。 */
export function laneAt(geom: readonly LaneGeom[], y: number): number {
  return geom.findIndex(g => y >= g.top && y < g.top + g.h)
}

/** 一个框在轨里的竖直范围。 */
export function boxYRange(g: LaneGeom, row: number): { top: number; bottom: number } {
  const top = g.top + LANE_PAD + row * LANE_ROW_H + (LANE_ROW_H - LANE_BOX_H) / 2
  return { top, bottom: top + LANE_BOX_H }
}

export interface LaneDraw {
  lanes: readonly Lane[]
  geom: readonly LaneGeom[]
  nameOf: (fid: string | null) => string | null
  selectedId: string | null
  /** 改起止时拖着的框:画在它新的位置上 */
  preview: AnnBox | null
  /** 正在拖出的新框:画在它要进的那条轨上(没有就画在最后) */
  draft: { start: string; end: string; lane: number } | null
  zoom: { start: number; end: number } | null
  width: number
}

/** 轨标题:特征名(浅灰底)、子框轨写成「缩量 ⊂ 横盘」,还没起名的轨写 unnamed。 */
function laneTitle(l: Lane, nameOf: LaneDraw['nameOf']): any {
  if (l.key === null) return { text: '{sym|unnamed}', rich: { sym: { fontFamily: MONO, fontSize: 12, color: INK } } }
  const biz = (s: string) => `{biz|${s.replace(/[{}|]/g, ' ')}}`
  const text = l.parent ? `${biz(nameOf(l.key) ?? '')}{sym| ⊂ }${biz(nameOf(l.parent) ?? '')}` : biz(nameOf(l.key) ?? '')
  return {
    text,
    rich: {
      biz: { backgroundColor: CHIP_BG, color: INK, fontSize: 12, padding: [1, 4], borderRadius: 3 },
      sym: { fontFamily: MONO, fontSize: 12, color: INK, fontWeight: 'bold' },
    },
  }
}

/** annotate 副图的 ECharts option:轨的分隔线与标题(graphic)+ 框(custom series)。 */
export function buildAnnotateSubOption(bars: Bar[], d: LaneDraw): unknown {
  const dates = bars.map(b => b.date)
  const graphics: any[] = []
  const w = d.width - SUB_GRID_LEFT - SUB_GRID_RIGHT
  d.geom.forEach((g, i) => {
    graphics.push({ type: 'rect', left: SUB_GRID_LEFT, top: g.top + g.h - 0.5, shape: { width: w, height: 1 },
                    style: { fill: LANE_LINE }, z: 1, silent: true })
    const t = laneTitle(d.lanes[i], d.nameOf)
    graphics.push({ type: 'text', left: SUB_GRID_LEFT + 2, top: g.top + LANE_PAD, z: 30, silent: true,
                    style: { ...t, fill: INK, fontSize: 12, backgroundColor: 'rgba(255,255,255,0.85)', padding: [0, 2] } })
  })

  // 每个框一行数据:[起点下标, 终点下标, 顶, 底, 选中, 拖出中, 编号]
  const rows: any[] = []
  const push = (b: { id: string; start: string; end: string }, top: number, bottom: number, sel: boolean, draft: boolean) => {
    if (!dates.length) return
    rows.push([startIndex(dates, b.start), endIndex(dates, b.end), top, bottom, sel ? 1 : 0, draft ? 1 : 0, b.id])
  }
  d.lanes.forEach((l, i) => {
    for (const lb of l.boxes) {
      const b = d.preview && d.preview.id === lb.box.id ? d.preview : lb.box
      const { top, bottom } = boxYRange(d.geom[i], lb.row)
      push(b, top, bottom, b.id === d.selectedId, false)
    }
  })
  if (d.draft) {
    const g = d.geom[d.draft.lane] ?? { top: (d.geom.at(-1)?.top ?? LANES_TOP) + (d.geom.at(-1)?.h ?? 0), h: LANE_ROW_H + 2 * LANE_PAD }
    const { top, bottom } = boxYRange(g, 0)
    push({ id: '__draft', start: d.draft.start, end: d.draft.end }, top, bottom, false, true)
  }

  return {
    animation: false,
    tooltip: { trigger: 'item', show: true, appendToBody: true, confine: true },
    grid: [{ left: SUB_GRID_LEFT, right: SUB_GRID_RIGHT, top: 0, bottom: 0 }],
    graphic: graphics,
    xAxis: [{
      type: 'category', data: dates, gridIndex: 0, boundaryGap: true,
      axisLine: { show: false }, axisTick: { show: false }, axisLabel: { show: false }, splitLine: { show: false },
      axisPointer: { show: true, type: 'none', snap: true, label: { show: false }, triggerTooltip: false },
    }],
    yAxis: [{ type: 'value', gridIndex: 0, show: false, min: 0, max: 1 }],
    // 拖动留给画框和改起止;滚轮照常缩放(和主图同步)
    dataZoom: [{ type: 'inside', xAxisIndex: 0, start: d.zoom?.start ?? 0, end: d.zoom?.end ?? 100,
                 moveOnMouseMove: false }],
    series: [{
      type: 'custom', name: 'annotation-boxes', xAxisIndex: 0, yAxisIndex: 0, clip: true,
      data: rows, encode: { x: [0, 1] }, z: 10,
      tooltip: {
        formatter: (p: any) => {
          const [s, e] = [p.value[0], p.value[1]]
          return `<span style="font-family:${MONO};color:${INK}">${dates[s]} – ${dates[e]}</span>`
        },
      },
      renderItem: (_p: any, api: any) => {
        const bw = api.size([1, 0])[0]
        const x0 = api.coord([api.value(0), 0])[0] - bw / 2
        const x1 = api.coord([api.value(1), 0])[0] + bw / 2
        const top = api.value(2), bottom = api.value(3)
        const sel = api.value(4) === 1, draft = api.value(5) === 1
        return {
          type: 'rect',
          shape: { x: x0, y: top, width: Math.max(3, x1 - x0), height: bottom - top, r: 2 },
          style: {
            fill: sel ? SELECTED_FILL : 'rgba(255,255,255,0)',
            stroke: INK, lineWidth: sel ? 2.5 : 1.5, lineDash: draft ? DRAFT_DASH : BOX_DASH,
          },
        }
      },
    }],
  }
}

/** 框在副图上的像素范围(点选、改起止用)。toPx:K 线下标 → 该根 K 线中心的 x;bw:一根 K 线的宽度。 */
export function boxRects(lanes: readonly Lane[], geom: readonly LaneGeom[], dates: readonly string[],
                         toPx: (i: number) => number, bw: number): BoxPx[] {
  const out: BoxPx[] = []
  if (!dates.length) return out
  lanes.forEach((l, i) => {
    for (const lb of l.boxes) {
      const { top, bottom } = boxYRange(geom[i], lb.row)
      out.push({ id: lb.box.id, left: toPx(startIndex(dates, lb.box.start)) - bw / 2,
                 right: toPx(endIndex(dates, lb.box.end)) + bw / 2, top, bottom })
    }
  })
  return out
}

/**
 * 主图 K 线区上标出的范围:选中的框(浅灰底、虚线边)和正在拖出或改起止的框(虚线边)。
 * 返回 kline 系列的 markArea。
 */
export function mainBoxMarks(dates: readonly string[],
                             selected: { start: string; end: string } | null,
                             live: { start: string; end: string } | null): unknown {
  const area = (b: { start: string; end: string }, fill: string) => [
    { xAxis: dates[startIndex(dates, b.start)], itemStyle: { color: fill, borderColor: INK, borderWidth: 1, borderType: 'dashed' } },
    { xAxis: dates[endIndex(dates, b.end)] },
  ]
  const data: any[] = []
  if (dates.length && selected) data.push(area(selected, 'rgba(0,0,0,0.06)'))
  if (dates.length && live) data.push(area(live, 'rgba(255,255,255,0)'))
  return { silent: true, data }
}
