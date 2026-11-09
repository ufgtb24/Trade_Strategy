/**
 * annotate / compare 下图上的鼠标手势。顶栏的工具(tool)默认都不亮,点亮一个只用一次:
 * - 不亮:K 线区、副图上拖动 → 左右平移图窗;点一下照常:K 线区点样本的三角 → 选中样本,点别处 → 什么都不选;
 *   副图上点框 → 选中它,点 bracket 轨上样本的跨度 → 选中样本,点画了没收的框右侧的 ◂ → 把它收进选中的样本。
 *   框的左右边拖不动(改起止要先点亮 box)。
 * - box:K 线区拖动 → 画一个新框(还没起名);副图特征轨上拖动 → 画一个带这个特征的新框(bracket 轨上拖出的还没起名);
 *   按在框的左右边拖 → 改它的起止;点一下和不亮时一样,工具不熄。画完一个框或改完一次起止,工具熄灭(toolDone)。
 * - point:点 K 线区某一根 → 在那天放样本(或选中当前 pattern 那天已有的样本),之后工具熄灭(store 的 placeSample);
 *   副图上和不亮时一样。
 * - feedback(只在 compare,spec 6.13):K 线区与整张副图(含 app 区,左右轨名栏除外)上拖动 → 拖出一段日期(range):
 *   拖动中把首尾两根 K 线交给调用方画竖带预览(setRange),松手时工具熄灭(toolDone)、再把范围与松开处交给调用方
 *   (rangeDone:范围里有买点就弹面板,没有就在松开处提示)。点一下不拖和不亮时一样,工具不熄:用户区照常选中,
 *   app 区留给图表自己的点击(点 ▼ / 格 / 族照样弹反馈面板)。拖出去又回到按下处 4 像素以内松手,也算点一下——
 *   和 ECharts 判不判 click 的口径一致(zrender 的 Handler:按下与松开相距超过 4 像素不派 click),
 *   这样一次操作不会既弹 range 面板、又被图表的点击弹出 point 面板。成交量带上拖动照旧平移。
 * - 成交量带拖动 → 平移,工具亮不亮都一样;compare 下副图 app 区(hit 行、band)拖动也是平移,点一下留给图表自己的点击。
 * 改起止时,框是某些样本的成员框的,终点停在其中最早的样本日(不越过样本日),停住时在鼠标旁写它是哪个样本的
 * 成员框:改共用的框时不悄悄改掉旧样本的依据。
 * 移动超过 DRAG_PX 才算拖动(annotate/boxGeometry.ts),否则算点一下。拖的过程中的样子(新框、改了起止的框)交给
 * 调用方去画,松手时才保存。鼠标样式(cursorAt):工具亮着时图上是十字,能点的地方是手,box 下框的左右边是左右拖。
 */
import type { ECharts } from 'echarts'
import type { AnnBox, Lane } from '../annotate/model'
import type { BoxMark } from '../annotate/samples'
import { UNCLAIMED } from '../annotate/membership'
import {
  boxAt, edgeOf, endIndex, isDrag, pannedZoom, resized, spanOf, startIndex, type BoxPx,
} from '../annotate/boxGeometry'
import {
  SIDE_MARK_X, boxRects, bracketPick, bracketRects, laneAt, type Draft, type LaneGeom, type PlacedBracket,
} from '../render/annotateLanes'
import { MAIN_GRID_LEFT, MAIN_GRID_RIGHT } from '../render/chart'
import { SUB_GRID_LEFT, SUB_GRID_RIGHT } from '../render/subGeometry'

export interface GestureDeps {
  main: () => ECharts | null
  sub: () => ECharts | null
  mainEl: () => HTMLElement | null
  subEl: () => HTMLElement | null
  active: () => boolean                     // annotate 且有 K 线、标注已读到
  /** 亮着的工具;null = 都不亮 */
  tool: () => 'box' | 'point' | 'feedback' | null
  /** box / feedback 用完一次(画了一个框、改了一次起止、拖出一段):熄灭工具 */
  toolDone: () => void
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
  /** feedback 拖选中的范围(首尾两根 K 线的日期,start ≤ end),画竖带预览;null 收起 */
  setRange: (r: { start: string; end: string } | null) => void
  /** feedback 拖完一段:范围(首尾两根 K 线的日期)与松开处(视口坐标,同 clientX / clientY);此前工具已熄灭 */
  rangeDone: (start: string, end: string, at: { x: number; y: number }) => void
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
  /**
   * 副图上这一高度(相对副图容器)归不归标注手势:compare 下只有用户轨与 bracket 的 user 行归它,
   * 其余(app 的 band、hit 行)留给图表自己的点击。不给 = 整张副图都归它(annotate)。
   */
  claims?: (y: number) => boolean
}

type Gesture =
  | { kind: 'draw'; src: 'main' | 'sub'; x0: number; y0: number; i0: number; lane: number;
      feature: string | null; hit: string | null; sample: string | null; take: string | null; moved: boolean }
  | { kind: 'resize'; x0: number; y0: number; box: AnnBox; side: 'l' | 'r'; moved: boolean }
  | { kind: 'point'; x0: number; y0: number; moved: boolean }
  /** feedback 拖一段;没拖动就松手时做 click(点一下的效果),null = 留给图表自己的点击 */
  | { kind: 'range'; src: 'main' | 'sub'; x0: number; y0: number; i0: number; moved: boolean;
      click: (() => void) | null }
  /** 平移;没拖动就松手时做 click(点一下的效果),null = 点一下什么都不做。x0/y0 是页面坐标 */
  | { kind: 'pan'; x0: number; y0: number; start: number; end: number; width: number; moved: boolean;
      click: (() => void) | null }

function local(el: HTMLElement, ev: MouseEvent): [number, number] {
  const r = el.getBoundingClientRect()
  return [ev.clientX - r.left, ev.clientY - r.top]
}

export function createAnnotateGestures(deps: GestureDeps) {
  let gesture: Gesture | null = null

  /** 手势落在哪张图上:主图上拖出新框、放样本在 K 线区,其余(轨上拖框、改起止)在副图。 */
  const surfaceOf = (g: Gesture): { el: HTMLElement | null; chart: ECharts | null } =>
    ((g.kind === 'draw' || g.kind === 'range') && g.src === 'main') || g.kind === 'point'
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
  /** 副图上这一点落在 bracket 轨哪个样本上(同起点并成一行时取 ▲ 离点最近的,见 bracketPick)。 */
  const bracketAt = (x: number, y: number): string | null => {
    const b = deps.bracket(), px = subPx()
    if (!b || !px) return null
    return bracketPick(bracketRects(b.placed, b.geom, deps.dates(), px.toPx, px.bw), px.bw, x, y)
  }
  /** 副图上这一点落在哪个画了没收的框右侧的 ◂ 上。 */
  const takeAt = (x: number, y: number): string | null => {
    const marks = deps.marks()
    if (!marks) return null
    for (const r of subRects()) {
      if (marks.get(r.id)?.focus !== UNCLAIMED) continue
      if (x >= r.right + SIDE_MARK_X[0] && x <= r.right + SIDE_MARK_X[1] && y >= r.top && y <= r.bottom) return r.id
    }
    return null
  }
  /** 主图拖出的框还没起名,画在 unnamed 轨上(还没有就在最后另起一条)。 */
  const unnamedLane = () => {
    const i = deps.lanes().findIndex(l => l.key === null)
    return i >= 0 ? i : deps.lanes().length
  }

  /** 副图上这一 x 在不在 grid 里(左边的轨名栏、右边的留白都不算)。 */
  const inPlot = (el: HTMLElement, x: number) => x >= SUB_GRID_LEFT && x <= el.clientWidth - SUB_GRID_RIGHT

  /** 副图用户区(特征轨、bracket 的 user 行)上点一下的效果:点 ◂ 收进选中的样本,点样本跨度选中样本,
   *  点框选中框,点空白什么都不选。按下时就定好(之后的重画不影响这一下点的是什么)。 */
  const userClick = (x: number, y: number): (() => void) => {
    const take = takeAt(x, y)
    const hit = take ? null : boxAt(subRects(), x, y)
    const sample = hit || take ? null : bracketAt(x, y)
    return () => {
      if (take) deps.take(take)
      else if (sample) deps.selectSample(sample)
      else deps.select(hit?.id ?? null)
    }
  }

  /** 从这一下开始平移;width 是图区宽(像素)。 */
  const panFrom = (ev: MouseEvent, width: number, click: (() => void) | null): Gesture => {
    const z = deps.zoom() ?? { start: 0, end: 100 }
    return { kind: 'pan', x0: ev.clientX, y0: ev.clientY, start: z.start, end: z.end, width, moved: false, click }
  }

  /**
   * 按在图上开始手势时让出输入框的焦点:mousedown 上的 preventDefault 会挡住浏览器默认的失焦,
   * 写完定义、note 后直接点图上的框,焦点还留在输入框里,Delete 删框就被当成在输入框里删字。
   * 输入框失焦时照常保存(各输入框的 blur 处理)。
   */
  function releaseFocus() {
    const a = document.activeElement as HTMLElement | null
    if (a && a !== document.body && a.closest('input, textarea, select, [contenteditable=""], [contenteditable="true"]')) a.blur()
  }

  function onMainDown(ev: MouseEvent) {
    const main = deps.main(), el = deps.mainEl()
    if (ev.button !== 0 || !deps.active() || !main || !el) return
    const [x, y] = local(el, ev)
    const width = el.clientWidth - MAIN_GRID_LEFT - MAIN_GRID_RIGHT
    if (main.containPixel({ gridIndex: 0 }, [x, y])) {
      const tool = deps.tool()
      if (tool === 'point') gesture = { kind: 'point', x0: x, y0: y, moved: false }
      else if (tool === 'feedback') {
        const sample = deps.sampleAt(x, y)
        gesture = { kind: 'range', src: 'main', x0: x, y0: y, i0: indexAt(main, x), moved: false,
                    click: () => (sample ? deps.selectSample(sample) : deps.select(null)) }
      } else if (tool === 'box') {
        gesture = { kind: 'draw', src: 'main', x0: x, y0: y, i0: indexAt(main, x), lane: unnamedLane(),
                    feature: null, hit: null, sample: deps.sampleAt(x, y), take: null, moved: false }
      } else {
        const sample = deps.sampleAt(x, y)
        gesture = panFrom(ev, width, () => (sample ? deps.selectSample(sample) : deps.select(null)))
      }
    } else if (main.containPixel({ gridIndex: 1 }, [x, y])) {
      gesture = panFrom(ev, width, null)
    } else return
    releaseFocus()
    ev.preventDefault()
  }

  function onSubDown(ev: MouseEvent) {
    const sub = deps.sub(), el = deps.subEl()
    if (ev.button !== 0 || !deps.active() || !sub || !el) return
    const [x, y] = local(el, ev)
    const width = el.clientWidth - SUB_GRID_LEFT - SUB_GRID_RIGHT
    // feedback 亮着:整张副图(含 app 区)的拖动归它;点一下在用户区照常选中,在 app 区留给图表自己的点击
    if (deps.tool() === 'feedback' && inPlot(el, x)) {
      const userArea = !deps.claims || deps.claims(y)
      gesture = { kind: 'range', src: 'sub', x0: x, y0: y, i0: indexAt(sub, x), moved: false,
                  click: userArea ? userClick(x, y) : null }
      releaseFocus()
      ev.preventDefault()
      return
    }
    // compare 的 app 区:拖动平移;点一下是图表自己的(app 的格、条、▼),这里不抢焦点、不拦默认行为
    if (deps.claims && !deps.claims(y)) { gesture = panFrom(ev, width, null); return }
    // 左右两边的轨名栏:框画在 grid 里(伸出去的部分裁掉了),这里点不中框、也不画框,只平移
    if (!inPlot(el, x)) {
      gesture = panFrom(ev, width, null)
      releaseFocus()
      ev.preventDefault()
      return
    }
    const take = takeAt(x, y)
    const hit = take ? null : boxAt(subRects(), x, y)
    const side = hit ? edgeOf(hit, x) : null
    if (deps.tool() !== 'box') {
      gesture = panFrom(ev, width, userClick(x, y))
    } else if (hit && side) {
      const box = deps.lanes().flatMap(l => l.boxes).find(lb => lb.box.id === hit.id)!.box
      gesture = { kind: 'resize', x0: x, y0: y, box, side, moved: false }
    } else {
      const li = laneAt(deps.geom(), y)
      gesture = { kind: 'draw', src: 'sub', x0: x, y0: y, i0: indexAt(sub, x), lane: li >= 0 ? li : unnamedLane(),
                  feature: li >= 0 ? deps.lanes()[li].key : null, hit: hit?.id ?? null,
                  sample: hit || take ? null : bracketAt(x, y), take, moved: false }
    }
    releaseFocus()
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
    if (!g) return
    if (g.kind === 'pan') {
      if (!g.moved && !isDrag(g.x0, g.y0, ev.clientX, ev.clientY)) return
      g.moved = true
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
    if (g.kind === 'range') {
      const [s, e] = spanOf(g.i0, i)
      deps.setRange({ start: dates[s], end: dates[e] })
      return
    }
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
    if (!g) return
    if (g.kind === 'pan') {
      if (!g.moved) g.click?.()
      return
    }
    const { el, chart } = surfaceOf(g)
    const dates = deps.dates()
    if (g.kind === 'point') {
      if (!g.moved && el) deps.placeSample(dates[indexAt(chart, local(el, ev)[0])])
      return
    }
    if (g.kind === 'range') {
      deps.setRange(null)
      const at = el ? local(el, ev) : null
      // 拖出去又回到按下处附近松手:算点一下(图表这时也会派 click,见文件头)
      if (!g.moved || !at || !isDrag(g.x0, g.y0, at[0], at[1])) { g.click?.(); return }
      const [s, e] = spanOf(g.i0, indexAt(chart, at[0]))
      deps.toolDone()
      deps.rangeDone(dates[s], dates[e], { x: ev.clientX, y: ev.clientY })
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
      deps.toolDone()
      return
    }
    deps.setPreview(null)
    deps.setStop(null)
    if (g.moved && el) {
      const [s, e] = resizedWithin(g, indexAt(chart, local(el, ev)[0]), null)
      if (dates[s] !== g.box.start || dates[e] !== g.box.end) deps.resizeBox(g.box.id, dates[s], dates[e])
      deps.toolDone()
    }
    deps.select(g.box.id)
  }

  /**
   * 鼠标停在图上这一点(相对 which 那张图的容器)时的样式;null = 交给图表(ECharts 每次移动都会重设,
   * 所以调用方要在图表自己的 mousemove 之后设)。拖动中不管。
   */
  function cursorAt(which: 'main' | 'sub', x: number, y: number): string | null {
    if (gesture || !deps.active()) return null
    const tool = deps.tool()
    if (which === 'main') {
      const main = deps.main()
      if (!main || !main.containPixel({ gridIndex: 0 }, [x, y])) return null
      if (tool) return 'crosshair'
      return deps.sampleAt(x, y) ? 'pointer' : null
    }
    const el = deps.subEl()
    if (tool === 'feedback') return el && inPlot(el, x) ? 'crosshair' : null
    if ((deps.claims && !deps.claims(y)) || !el || !inPlot(el, x)) return null
    if (takeAt(x, y) || bracketAt(x, y)) return 'pointer'
    if (tool !== 'box') return null
    const hit = boxAt(subRects(), x, y)
    return hit && edgeOf(hit, x) ? 'ew-resize' : 'crosshair'
  }

  function cancel() {
    if (!gesture) return
    gesture = null
    deps.setDraft(null)
    deps.setRange(null)
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
    cursorAt,
  }
}
