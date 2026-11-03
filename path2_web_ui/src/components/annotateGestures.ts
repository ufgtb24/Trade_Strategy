/**
 * annotate 下图上的鼠标手势:
 * - tool = box:
 *   - K 线区(主图上半)拖动 → 画一个新框(还没起名);点一下样本的三角 → 选中样本;点别处 → 什么都不选;
 *   - 副图:特征轨上拖动 → 画一个带这个特征的新框(bracket 轨上拖出的还没起名);按在框的左右边拖 → 改它的起止;
 *     点一下框 → 选中它;点 bracket 轨上样本的跨度 → 选中样本;点框右侧的 ◂ → 把这个画了没收的框收进选中的样本;
 * - tool = point:点 K 线区某一根 → 在那天放样本(或选中当前 pattern 那天已有的样本),之后工具自动回到 box;
 * - 成交量带拖动 → 左右平移图窗(K 线区的拖动留给画框;滚轮照常缩放)。两种工具都可以。
 * 改起止时,框是某些样本的成员框的,终点停在其中最早的样本日(不越过样本日),停住时在鼠标旁写它是哪个样本的
 * 成员框(M12)。
 * 拖动超过 DRAG_PX 才算拖动(annotate/boxGeometry.ts)。拖的过程中的样子(新框、改了起止的框)交给调用方去画,
 * 松手时才保存。
 */
import type { ECharts } from 'echarts'
import type { AnnBox, Lane } from '../annotate/model'
import type { BoxMark } from '../annotate/samples'
import {
  boxAt, edgeOf, endIndex, isDrag, pannedZoom, resized, spanOf, startIndex, type BoxPx,
} from '../annotate/boxGeometry'
import {
  SIDE_MARK_X, boxRects, bracketRects, laneAt, type Draft, type LaneGeom, type PlacedBracket,
} from '../render/annotateLanes'
import { MAIN_GRID_LEFT, MAIN_GRID_RIGHT } from '../render/chart'

export interface GestureDeps {
  main: () => ECharts | null
  sub: () => ECharts | null
  mainEl: () => HTMLElement | null
  subEl: () => HTMLElement | null
  active: () => boolean                     // annotate 且有 K 线、标注已读到
  tool: () => 'box' | 'point'
  dates: () => readonly string[]
  lanes: () => readonly Lane[]
  geom: () => readonly LaneGeom[]
  bracket: () => { geom: LaneGeom; placed: readonly PlacedBracket[] } | null
  marks: () => ReadonlyMap<string, BoxMark> | null
  zoom: () => { start: number; end: number } | null
  /** 主图上这一点落在哪个样本的三角上(相对主图容器的像素) */
  sampleAt: (x: number, y: number) => string | null
  /** 改起止时框终点的上限:收了它的样本里最早的样本日,以及停住时鼠标旁写的话;没有为 null */
  limitOf: (boxId: string) => { date: string; text: string } | null
  setDraft: (d: Draft | null) => void
  setPreview: (b: AnnBox | null) => void
  /** 改起止停在样本日时鼠标旁的提示(页面坐标);null 收起 */
  setStop: (s: { x: number; y: number; text: string } | null) => void
  createBox: (start: string, end: string, feature: string | null) => void
  resizeBox: (id: string, start: string, end: string) => void
  /** 选中框;null = 点在空白处,什么都不选 */
  select: (id: string | null) => void
  selectSample: (id: string) => void
  placeSample: (date: string) => void
  /** 把画了没收的框收进选中的样本 */
  take: (boxId: string) => void
}

type Gesture =
  | { kind: 'draw'; src: 'main' | 'sub'; x0: number; y0: number; i0: number; lane: number;
      feature: string | null; hit: string | null; sample: string | null; take: string | null; moved: boolean }
  | { kind: 'resize'; x0: number; y0: number; box: AnnBox; side: 'l' | 'r'; moved: boolean }
  | { kind: 'point'; x0: number; y0: number; moved: boolean }
  | { kind: 'pan'; x0: number; start: number; end: number; width: number }

function local(el: HTMLElement, ev: MouseEvent): [number, number] {
  const r = el.getBoundingClientRect()
  return [ev.clientX - r.left, ev.clientY - r.top]
}

export function createAnnotateGestures(deps: GestureDeps) {
  let gesture: Gesture | null = null

  /** 手势落在哪张图上:主图上拖出新框、放样本在 K 线区,其余(轨上拖框、改起止)在副图。 */
  const surfaceOf = (g: Gesture): { el: HTMLElement | null; chart: ECharts | null } =>
    (g.kind === 'draw' && g.src === 'main') || g.kind === 'point'
      ? { el: deps.mainEl(), chart: deps.main() } : { el: deps.subEl(), chart: deps.sub() }

  const indexAt = (chart: ECharts | null, x: number): number => {
    const n = deps.dates().length
    const v = chart ? Number(chart.convertFromPixel({ xAxisIndex: 0 }, x)) : 0
    return Math.max(0, Math.min(n - 1, Math.round(Number.isFinite(v) ? v : 0)))
  }
  const subPx = () => {
    const sub = deps.sub()
    if (!sub) return null
    const toPx = (i: number) => Number(sub.convertToPixel({ xAxisIndex: 0 }, i))
    return { toPx, bw: toPx(1) - toPx(0) }
  }
  const subRects = (): BoxPx[] => {
    const px = subPx()
    return px ? boxRects(deps.lanes(), deps.geom(), deps.dates(), px.toPx, px.bw) : []
  }
  const inRect = (r: BoxPx, x: number, y: number) => x >= r.left && x <= r.right && y >= r.top && y <= r.bottom
  /** 副图上这一点落在 bracket 轨哪个样本的跨度上。 */
  const bracketAt = (x: number, y: number): string | null => {
    const b = deps.bracket(), px = subPx()
    if (!b || !px) return null
    return bracketRects(b.placed, b.geom, deps.dates(), px.toPx, px.bw).find(r => inRect(r, x, y))?.id ?? null
  }
  /** 副图上这一点落在哪个画了没收的框右侧的 ◂ 上。 */
  const takeAt = (x: number, y: number): string | null => {
    const marks = deps.marks()
    if (!marks) return null
    for (const r of subRects()) {
      if (marks.get(r.id)?.focus !== 'cand') continue
      if (x >= r.right + SIDE_MARK_X[0] && x <= r.right + SIDE_MARK_X[1] && y >= r.top && y <= r.bottom) return r.id
    }
    return null
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
      gesture = deps.tool() === 'point'
        ? { kind: 'point', x0: x, y0: y, moved: false }
        : { kind: 'draw', src: 'main', x0: x, y0: y, i0: indexAt(main, x), lane: unnamedLane(),
            feature: null, hit: null, sample: deps.sampleAt(x, y), take: null, moved: false }
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
    if (ev.button !== 0 || !deps.active() || deps.tool() !== 'box' || !sub || !el) return
    const [x, y] = local(el, ev)
    const take = takeAt(x, y)
    const hit = take ? null : boxAt(subRects(), x, y)
    const side = hit ? edgeOf(hit, x) : null
    if (hit && side) {
      const box = deps.lanes().flatMap(l => l.boxes).find(lb => lb.box.id === hit.id)!.box
      gesture = { kind: 'resize', x0: x, y0: y, box, side, moved: false }
    } else {
      const li = laneAt(deps.geom(), y)
      gesture = { kind: 'draw', src: 'sub', x0: x, y0: y, i0: indexAt(sub, x), lane: li >= 0 ? li : unnamedLane(),
                  feature: li >= 0 ? deps.lanes()[li].key : null, hit: hit?.id ?? null,
                  sample: hit || take ? null : bracketAt(x, y), take, moved: false }
    }
    ev.preventDefault()
  }

  /**
   * 改起止后的起止下标;拖右边时,终点不越过收了它的样本里最早的样本日(停住时在鼠标旁写是哪个样本的成员框)。
   */
  function resizedWithin(g: Extract<Gesture, { kind: 'resize' }>, i: number, ev: MouseEvent | null): [number, number] {
    const dates = deps.dates()
    let [s, e] = resized(startIndex(dates, g.box.start), endIndex(dates, g.box.end), g.side, i)
    const lim = g.side === 'r' ? deps.limitOf(g.box.id) : null
    const li = lim ? endIndex(dates, lim.date) : null
    if (lim && li !== null && e > li) {
      e = Math.max(s, li)
      if (ev) deps.setStop({ x: ev.clientX, y: ev.clientY, text: lim.text })
    } else if (ev) deps.setStop(null)
    return [s, e]
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
    if (g.kind === 'point') return
    if (g.kind === 'draw') {
      const [s, e] = spanOf(g.i0, i)
      deps.setDraft({ start: dates[s], end: dates[e], lane: g.lane })
    } else {
      const [s, e] = resizedWithin(g, i, ev)
      deps.setPreview({ ...g.box, start: dates[s], end: dates[e] })
    }
  }

  function onUp(ev: MouseEvent) {
    const g = gesture
    gesture = null
    if (!g || g.kind === 'pan') return
    const { el, chart } = surfaceOf(g)
    const dates = deps.dates()
    if (g.kind === 'point') {
      if (!g.moved && el) deps.placeSample(dates[indexAt(chart, local(el, ev)[0])])
      return
    }
    if (g.kind === 'draw') {
      deps.setDraft(null)
      if (!g.moved) {
        if (g.take) deps.take(g.take)
        else if (g.sample) deps.selectSample(g.sample)
        else deps.select(g.hit)
        return
      }
      if (!el) return
      const [s, e] = spanOf(g.i0, indexAt(chart, local(el, ev)[0]))
      deps.createBox(dates[s], dates[e], g.feature)
      return
    }
    deps.setPreview(null)
    deps.setStop(null)
    if (g.moved && el) {
      const [s, e] = resizedWithin(g, indexAt(chart, local(el, ev)[0]), null)
      if (dates[s] !== g.box.start || dates[e] !== g.box.end) deps.resizeBox(g.box.id, dates[s], dates[e])
    }
    deps.select(g.box.id)
  }

  /** 悬停在框的左右边上时,光标换成左右拖的样子。 */
  function hoverCursor(ev: MouseEvent) {
    const el = deps.subEl(), sub = deps.sub()
    if (!el || !sub || !deps.active() || deps.tool() !== 'box' || !el.contains(ev.target as Node)) return
    const [x, y] = local(el, ev)
    if (takeAt(x, y) || bracketAt(x, y)) { sub.getZr().setCursorStyle('pointer'); return }
    const hit = boxAt(subRects(), x, y)
    if (hit && edgeOf(hit, x)) sub.getZr().setCursorStyle('ew-resize')
  }

  function cancel() {
    if (!gesture) return
    gesture = null
    deps.setDraft(null)
    deps.setPreview(null)
    deps.setStop(null)
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
