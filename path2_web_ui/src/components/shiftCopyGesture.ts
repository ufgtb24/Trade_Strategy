/**
 * 主图上按住 Shift 复制一天、一段(spec 1.14「复制一天、一段」),四档通用:
 * - 按住 Shift 在主图上按下:拖开 → 拖动中给竖带预览,松手复制这一段;没拖开 → 复制这一天。
 *   移动超过 DRAG_PX 才算拖开(同画框、反馈拖选的口径,也是图表判不判点击的口径);按下时按着 Shift 就算,
 *   途中松开 Shift 不影响;拖出图区按图窗里的首尾 K 线截住。
 * - 只复制,不改图上的状态:按下就在捕获阶段截下,图表(平移、框选、点击)、标注手势(平移、画框、放样本、
 *   反馈拖选)都收不到这一下;松手后跟着来的那次 click 也截下,所以不会被当成「点空白」清掉选中。
 *   不让出输入框的焦点、不改当前日、不平移,工具亮着也不熄。
 * - 唯一例外:在 event 的记号上 Shift+点(没拖开),照旧是跨图配对查询:按下时记下鼠标停着的记号(markerAt),
 *   松手时交给 pick(KlineChart.ts 的 handleShiftClick)。按下一样截下——图表收不到按下就不会派这次点击,
 *   所以由这里补上;从记号上拖开仍是复制一段。
 * 接的范围由调用方的 onChart 定(主图 K 线区与成交量带);副图不接。
 */
import type { ECharts } from 'echarts'
import { isDrag, spanOf } from '../annotate/boxGeometry'

export interface ShiftCopyDeps {
  main: () => ECharts | null
  mainEl: () => HTMLElement | null
  /** K 线根数(下标夹到 [0, 根数-1]) */
  count: () => number
  /** 图区的左右边(相对主图容器的像素):拖出去时把 x 截在里面,下标就落在图窗里的首尾 K 线上 */
  plot: () => { left: number; right: number }
  /** 这一点(相对主图容器)接不接:主图的 K 线区、成交量带 */
  onChart: (x: number, y: number) => boolean
  /** 鼠标此刻停着的 event 记号(instance_id);不在记号上为 null */
  markerAt: () => string | null
  /** 在记号上 Shift+点(没拖开):照旧的跨图配对查询 */
  pick: (instanceId: string) => void
  /** 拖动中的预览:首尾下标(左小右大);null 收起 */
  setPreview: (span: [number, number] | null) => void
  /** 松手:复制下标 i0…i1(同一根是一天) */
  copy: (i0: number, i1: number) => void
}

function local(el: HTMLElement, ev: MouseEvent): [number, number] {
  const r = el.getBoundingClientRect()
  return [ev.clientX - r.left, ev.clientY - r.top]
}

export function createShiftCopyGesture(deps: ShiftCopyDeps) {
  let gesture: { x0: number; y0: number; i0: number; marker: string | null; moved: boolean } | null = null
  /** 刚松手:跟着来的那次 click 截下(不让图表当成点空白清掉选中) */
  let swallowClick = false

  /** 这一 x(相对主图容器)落在哪根 K 线上;先截在图区里,拖出图区就停在图窗的首尾那根 */
  const indexAt = (x: number): number => {
    const main = deps.main()
    const n = deps.count()
    const { left, right } = deps.plot()
    const cx = Math.max(left + 1, Math.min(right - 1, x))
    const v = main ? Number(main.convertFromPixel({ xAxisIndex: 0 }, cx)) : 0
    return Math.max(0, Math.min(n - 1, Math.round(Number.isFinite(v) ? v : 0)))
  }

  function onDown(ev: MouseEvent) {
    swallowClick = false
    const el = deps.mainEl()
    if (ev.button !== 0 || !ev.shiftKey || !el || !deps.main() || deps.count() === 0) return
    const [x, y] = local(el, ev)
    if (!deps.onChart(x, y)) return
    gesture = { x0: x, y0: y, i0: indexAt(x), marker: deps.markerAt(), moved: false }
    // 截下:图表与标注手势都收不到这一下;preventDefault 挡住浏览器 Shift+按下时扩展文字选区
    ev.preventDefault()
    ev.stopImmediatePropagation()
  }

  function onMove(ev: MouseEvent) {
    const g = gesture, el = deps.mainEl()
    if (!g || !el) return
    const [x, y] = local(el, ev)
    if (!g.moved && !isDrag(g.x0, g.y0, x, y)) return
    g.moved = true
    deps.setPreview(spanOf(g.i0, indexAt(x)))
  }

  function onUp(ev: MouseEvent) {
    const g = gesture, el = deps.mainEl()
    gesture = null
    if (!g) return
    deps.setPreview(null)
    swallowClick = true
    // 松手处不在主图上时浏览器不派 click 到主图:下一轮事件前放开,免得截下以后真正的点击
    setTimeout(() => { swallowClick = false }, 0)
    const at = el ? local(el, ev) : null
    // 拖出去又回到按下处附近松手:算点一下——在记号上是配对查询,否则复制按下那一天
    if (!g.moved || !at || !isDrag(g.x0, g.y0, at[0], at[1])) {
      if (g.marker) deps.pick(g.marker)
      else deps.copy(g.i0, g.i0)
      return
    }
    const [s, e] = spanOf(g.i0, indexAt(at[0]))
    deps.copy(s, e)
  }

  function onClick(ev: MouseEvent) {
    if (!swallowClick) return
    swallowClick = false
    ev.preventDefault()
    ev.stopImmediatePropagation()
  }

  function cancel() {
    if (!gesture) return
    gesture = null
    deps.setPreview(null)
  }

  return {
    attach() {
      // 捕获阶段挂在主图容器上:先于图表(挂在容器里面的画布层)与标注手势(冒泡阶段)
      deps.mainEl()?.addEventListener('mousedown', onDown, true)
      deps.mainEl()?.addEventListener('click', onClick, true)
      // 捕获阶段挂在 window 上:拖到图外、图表拦下冒泡的 mousemove 时也收得到
      window.addEventListener('mousemove', onMove, true)
      window.addEventListener('mouseup', onUp, true)
    },
    detach() {
      deps.mainEl()?.removeEventListener('mousedown', onDown, true)
      deps.mainEl()?.removeEventListener('click', onClick, true)
      window.removeEventListener('mousemove', onMove, true)
      window.removeEventListener('mouseup', onUp, true)
    },
    cancel,
  }
}
