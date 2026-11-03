/**
 * annotate 下图上的鼠标手势(只在 tool = box 时生效):
 * - K 线区(主图上半)拖动 → 画一个新框(还没起名);只点一下 → 取消选中;
 * - 特征轨(副图)拖动 → 画一个带这个特征的新框;按在框的左右边拖 → 改它的起止;只点一下框 → 选中它;
 * - 成交量带拖动 → 左右平移图窗(K 线区的拖动留给画框;滚轮照常缩放)。
 * 拖动超过 DRAG_PX 才算拖动(annotate/boxGeometry.ts)。拖的过程中的样子(新框、改了起止的框)交给调用方去画,
 * 松手时才保存。
 */
import type { ECharts } from 'echarts'
import type { AnnBox, Lane } from '../annotate/model'
import {
  boxAt, edgeOf, endIndex, isDrag, pannedZoom, resized, spanOf, startIndex,
} from '../annotate/boxGeometry'
import { boxRects, laneAt, type LaneGeom } from '../render/annotateLanes'
import { MAIN_GRID_LEFT, MAIN_GRID_RIGHT } from '../render/chart'

export interface Draft { start: string; end: string; lane: number }

export interface GestureDeps {
  main: () => ECharts | null
  sub: () => ECharts | null
  mainEl: () => HTMLElement | null
  subEl: () => HTMLElement | null
  active: () => boolean                     // annotate 且 tool = box 且有 K 线
  dates: () => readonly string[]
  lanes: () => readonly Lane[]
  geom: () => readonly LaneGeom[]
  zoom: () => { start: number; end: number } | null
  setDraft: (d: Draft | null) => void
  setPreview: (b: AnnBox | null) => void
  createBox: (start: string, end: string, feature: string | null) => void
  resizeBox: (id: string, start: string, end: string) => void
  select: (id: string | null) => void
}

type Gesture =
  | { kind: 'draw'; src: 'main' | 'sub'; x0: number; y0: number; i0: number; lane: number;
      feature: string | null; hit: string | null; moved: boolean }
  | { kind: 'resize'; x0: number; y0: number; box: AnnBox; side: 'l' | 'r'; moved: boolean }
  | { kind: 'pan'; x0: number; start: number; end: number; width: number }

function local(el: HTMLElement, ev: MouseEvent): [number, number] {
  const r = el.getBoundingClientRect()
  return [ev.clientX - r.left, ev.clientY - r.top]
}

export function createAnnotateGestures(d: GestureDeps) {
  let g: Gesture | null = null

  const indexAt = (chart: ECharts | null, x: number): number => {
    const n = d.dates().length
    const v = chart ? Number(chart.convertFromPixel({ xAxisIndex: 0 }, x)) : 0
    return Math.max(0, Math.min(n - 1, Math.round(Number.isFinite(v) ? v : 0)))
  }
  const subRects = () => {
    const sub = d.sub()
    if (!sub) return []
    const toPx = (i: number) => Number(sub.convertToPixel({ xAxisIndex: 0 }, i))
    return boxRects(d.lanes(), d.geom(), d.dates(), toPx, toPx(1) - toPx(0))
  }
  /** 主图拖出的框还没起名,画在 unnamed 轨上(还没有就在最后另起一条)。 */
  const unnamedLane = () => {
    const i = d.lanes().findIndex(l => l.key === null)
    return i >= 0 ? i : d.lanes().length
  }

  function onMainDown(ev: MouseEvent) {
    const main = d.main(), el = d.mainEl()
    if (ev.button !== 0 || !d.active() || !main || !el) return
    const [x, y] = local(el, ev)
    if (main.containPixel({ gridIndex: 0 }, [x, y])) {
      g = { kind: 'draw', src: 'main', x0: x, y0: y, i0: indexAt(main, x), lane: unnamedLane(),
            feature: null, hit: null, moved: false }
      ev.preventDefault()
    } else if (main.containPixel({ gridIndex: 1 }, [x, y])) {
      const z = d.zoom() ?? { start: 0, end: 100 }
      g = { kind: 'pan', x0: ev.clientX, start: z.start, end: z.end,
            width: el.clientWidth - MAIN_GRID_LEFT - MAIN_GRID_RIGHT }
      ev.preventDefault()
    }
  }

  function onSubDown(ev: MouseEvent) {
    const sub = d.sub(), el = d.subEl()
    if (ev.button !== 0 || !d.active() || !sub || !el) return
    const [x, y] = local(el, ev)
    const hit = boxAt(subRects(), x, y)
    const side = hit ? edgeOf(hit, x) : null
    if (hit && side) {
      const box = d.lanes().flatMap(l => l.boxes).find(lb => lb.box.id === hit.id)!.box
      g = { kind: 'resize', x0: x, y0: y, box, side, moved: false }
    } else {
      const li = laneAt(d.geom(), y)
      g = { kind: 'draw', src: 'sub', x0: x, y0: y, i0: indexAt(sub, x), lane: li >= 0 ? li : unnamedLane(),
            feature: li >= 0 ? d.lanes()[li].key : null, hit: hit?.id ?? null, moved: false }
    }
    ev.preventDefault()
  }

  function onMove(ev: MouseEvent) {
    if (!g) { hoverCursor(ev); return }
    const dates = d.dates()
    if (g.kind === 'pan') {
      const z = pannedZoom(g.start, g.end, ev.clientX - g.x0, g.width)
      d.main()?.dispatchAction({ type: 'dataZoom', start: z.start, end: z.end })
      return
    }
    const el = g.kind === 'draw' && g.src === 'main' ? d.mainEl() : d.subEl()
    const chart = g.kind === 'draw' && g.src === 'main' ? d.main() : d.sub()
    if (!el) return
    const [x, y] = local(el, ev)
    if (!g.moved && !isDrag(g.x0, g.y0, x, y)) return
    g.moved = true
    const i = indexAt(chart, x)
    if (g.kind === 'draw') {
      const [s, e] = spanOf(g.i0, i)
      d.setDraft({ start: dates[s], end: dates[e], lane: g.lane })
    } else {
      const [s, e] = resized(startIndex(dates, g.box.start), endIndex(dates, g.box.end), g.side, i)
      d.setPreview({ ...g.box, start: dates[s], end: dates[e] })
    }
  }

  function onUp(ev: MouseEvent) {
    const done = g
    g = null
    if (!done || done.kind === 'pan') return
    const dates = d.dates()
    if (done.kind === 'draw') {
      d.setDraft(null)
      if (!done.moved) { d.select(done.hit); return }
      const el = done.src === 'main' ? d.mainEl() : d.subEl()
      const chart = done.src === 'main' ? d.main() : d.sub()
      if (!el) return
      const [s, e] = spanOf(done.i0, indexAt(chart, local(el, ev)[0]))
      d.createBox(dates[s], dates[e], done.feature)
      return
    }
    d.setPreview(null)
    if (!done.moved) { d.select(done.box.id); return }
    const el = d.subEl()
    if (!el) return
    const [s, e] = resized(startIndex(dates, done.box.start), endIndex(dates, done.box.end), done.side,
                           indexAt(d.sub(), local(el, ev)[0]))
    if (dates[s] !== done.box.start || dates[e] !== done.box.end) d.resizeBox(done.box.id, dates[s], dates[e])
    d.select(done.box.id)
  }

  /** 悬停在框的左右边上时,光标换成左右拖的样子。 */
  function hoverCursor(ev: MouseEvent) {
    const el = d.subEl(), sub = d.sub()
    if (!el || !sub || !d.active() || !el.contains(ev.target as Node)) return
    const [x, y] = local(el, ev)
    const hit = boxAt(subRects(), x, y)
    if (hit && edgeOf(hit, x)) sub.getZr().setCursorStyle('ew-resize')
  }

  function cancel() {
    if (!g) return
    g = null
    d.setDraft(null)
    d.setPreview(null)
  }

  return {
    attach() {
      d.mainEl()?.addEventListener('mousedown', onMainDown)
      d.subEl()?.addEventListener('mousedown', onSubDown)
      // 捕获阶段:ECharts 在拖动期间会拦下冒泡的 mousemove
      window.addEventListener('mousemove', onMove, true)
      window.addEventListener('mouseup', onUp, true)
    },
    detach() {
      d.mainEl()?.removeEventListener('mousedown', onMainDown)
      d.subEl()?.removeEventListener('mousedown', onSubDown)
      window.removeEventListener('mousemove', onMove, true)
      window.removeEventListener('mouseup', onUp, true)
    },
    cancel,
  }
}
