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
import { boxRects, laneAt, type Draft, type LaneGeom } from '../render/annotateLanes'
import { MAIN_GRID_LEFT, MAIN_GRID_RIGHT } from '../render/chart'

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

export function createAnnotateGestures(deps: GestureDeps) {
  let gesture: Gesture | null = null

  /** 手势落在哪张图上:主图上拖出新框在 K 线区,其余(轨上拖框、改起止)在副图。 */
  const surfaceOf = (g: Gesture): { el: HTMLElement | null; chart: ECharts | null } =>
    g.kind === 'draw' && g.src === 'main' ? { el: deps.mainEl(), chart: deps.main() } : { el: deps.subEl(), chart: deps.sub() }

  const indexAt = (chart: ECharts | null, x: number): number => {
    const n = deps.dates().length
    const v = chart ? Number(chart.convertFromPixel({ xAxisIndex: 0 }, x)) : 0
    return Math.max(0, Math.min(n - 1, Math.round(Number.isFinite(v) ? v : 0)))
  }
  const subRects = () => {
    const sub = deps.sub()
    if (!sub) return []
    const toPx = (i: number) => Number(sub.convertToPixel({ xAxisIndex: 0 }, i))
    return boxRects(deps.lanes(), deps.geom(), deps.dates(), toPx, toPx(1) - toPx(0))
  }
  /** 主图拖出的框还没起名,画在 unnamed 轨上(还没有就在最后另起一条)。 */
  const unnamedLane = () => {
    const i = deps.lanes().findIndex(l => l.key === null)
    return i >= 0 ? i : deps.lanes().length
  }

  function onMainDown(ev: MouseEvent) {
    const main = deps.main(), el = deps.mainEl()
    if (ev.button !== 0 || !deps.active() || !main || !el) return
    const [x, y] = local(el, ev)
    if (main.containPixel({ gridIndex: 0 }, [x, y])) {
      gesture = { kind: 'draw', src: 'main', x0: x, y0: y, i0: indexAt(main, x), lane: unnamedLane(),
                  feature: null, hit: null, moved: false }
      ev.preventDefault()
    } else if (main.containPixel({ gridIndex: 1 }, [x, y])) {
      const z = deps.zoom() ?? { start: 0, end: 100 }
      gesture = { kind: 'pan', x0: ev.clientX, start: z.start, end: z.end,
                  width: el.clientWidth - MAIN_GRID_LEFT - MAIN_GRID_RIGHT }
      ev.preventDefault()
    }
  }

  function onSubDown(ev: MouseEvent) {
    const sub = deps.sub(), el = deps.subEl()
    if (ev.button !== 0 || !deps.active() || !sub || !el) return
    const [x, y] = local(el, ev)
    const hit = boxAt(subRects(), x, y)
    const side = hit ? edgeOf(hit, x) : null
    if (hit && side) {
      const box = deps.lanes().flatMap(l => l.boxes).find(lb => lb.box.id === hit.id)!.box
      gesture = { kind: 'resize', x0: x, y0: y, box, side, moved: false }
    } else {
      const li = laneAt(deps.geom(), y)
      gesture = { kind: 'draw', src: 'sub', x0: x, y0: y, i0: indexAt(sub, x), lane: li >= 0 ? li : unnamedLane(),
                  feature: li >= 0 ? deps.lanes()[li].key : null, hit: hit?.id ?? null, moved: false }
    }
    ev.preventDefault()
  }

  function onMove(ev: MouseEvent) {
    const g = gesture
    if (!g) { hoverCursor(ev); return }
    if (g.kind === 'pan') {
      const z = pannedZoom(g.start, g.end, ev.clientX - g.x0, g.width)
      deps.main()?.dispatchAction({ type: 'dataZoom', start: z.start, end: z.end })
      return
    }
    const { el, chart } = surfaceOf(g)
    if (!el) return
    const [x, y] = local(el, ev)
    if (!g.moved && !isDrag(g.x0, g.y0, x, y)) return
    g.moved = true
    const dates = deps.dates(), i = indexAt(chart, x)
    if (g.kind === 'draw') {
      const [s, e] = spanOf(g.i0, i)
      deps.setDraft({ start: dates[s], end: dates[e], lane: g.lane })
    } else {
      const [s, e] = resized(startIndex(dates, g.box.start), endIndex(dates, g.box.end), g.side, i)
      deps.setPreview({ ...g.box, start: dates[s], end: dates[e] })
    }
  }

  function onUp(ev: MouseEvent) {
    const g = gesture
    gesture = null
    if (!g || g.kind === 'pan') return
    const { el, chart } = surfaceOf(g)
    const dates = deps.dates()
    if (g.kind === 'draw') {
      deps.setDraft(null)
      if (!g.moved) { deps.select(g.hit); return }
      if (!el) return
      const [s, e] = spanOf(g.i0, indexAt(chart, local(el, ev)[0]))
      deps.createBox(dates[s], dates[e], g.feature)
      return
    }
    deps.setPreview(null)
    if (g.moved && el) {
      const [s, e] = resized(startIndex(dates, g.box.start), endIndex(dates, g.box.end), g.side,
                             indexAt(chart, local(el, ev)[0]))
      if (dates[s] !== g.box.start || dates[e] !== g.box.end) deps.resizeBox(g.box.id, dates[s], dates[e])
    }
    deps.select(g.box.id)
  }

  /** 悬停在框的左右边上时,光标换成左右拖的样子。 */
  function hoverCursor(ev: MouseEvent) {
    const el = deps.subEl(), sub = deps.sub()
    if (!el || !sub || !deps.active() || !el.contains(ev.target as Node)) return
    const [x, y] = local(el, ev)
    const hit = boxAt(subRects(), x, y)
    if (hit && edgeOf(hit, x)) sub.getZr().setCursorStyle('ew-resize')
  }

  function cancel() {
    if (!gesture) return
    gesture = null
    deps.setDraft(null)
    deps.setPreview(null)
  }

  return {
    attach() {
      deps.mainEl()?.addEventListener('mousedown', onMainDown)
      deps.subEl()?.addEventListener('mousedown', onSubDown)
      // 捕获阶段:ECharts 在拖动期间会拦下冒泡的 mousemove
      window.addEventListener('mousemove', onMove, true)
      window.addEventListener('mouseup', onUp, true)
    },
    detach() {
      deps.mainEl()?.removeEventListener('mousedown', onMainDown)
      deps.subEl()?.removeEventListener('mousedown', onSubDown)
      window.removeEventListener('mousemove', onMove, true)
      window.removeEventListener('mouseup', onUp, true)
    },
    cancel,
  }
}
