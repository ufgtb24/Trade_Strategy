// 悬浮面板几何:位置/尺寸 + 拖拽/缩放 + 视口钳制 + localStorage 持久化。
// 供 WorkingCopyDrawer 消费,把原「右侧贴边全高抽屉」变成可拖可缩的悬浮窗
// (痛点=固定抽屉遮挡 K 线关注区)。几何计算是纯函数,与 DOM 解耦,可单测。
//
// 两个实现约定,都有原因:
//   · 拖拽走 window 监听 + pointerId 匹配(同 ResizableDivider),不用 setPointerCapture
//     ——jsdom 未实现 capture,window 模式才测得动。
//   · 位移用 left/top,不用 transform——面板里嵌 monaco,祖先带 transform 会成为新包含块,
//     补全框/hover 浮层的定位会跑偏。
import { onBeforeUnmount, ref, type Ref } from 'vue'

export interface PanelRect { x: number; y: number; w: number; h: number }

export const RECT_KEY = 'p2wc:drawer:rect'   // 沿用抽屉既有 key 前缀(同 p2wc:drawer:anchorKind)

export const MIN_W = 360        // 再窄 monaco 的 diff 双栏没法用
export const MIN_H = 280
export const EDGE_KEEP_X = 80   // 水平方向至少留在视口内的宽度(拖不丢)
export const EDGE_KEEP_Y = 40   // 垂直方向:标题栏高度,保证永远抓得到

const DEF_W = 480               // 与改造前的抽屉同宽,观感不突变
const DEF_H = 760
const MARGIN = 12               // 默认位置离视口边缘的留白

function clamp(v: number, lo: number, hi: number): number {
  return Math.min(Math.max(v, lo), hi)
}

/** 把矩形钳进视口:尺寸卡在 [MIN, 视口] 内,位置保证标题栏始终抓得到 */
export function clampRect(r: PanelRect, vw: number, vh: number): PanelRect {
  const w = clamp(r.w, Math.min(MIN_W, vw), vw)
  const h = clamp(r.h, Math.min(MIN_H, vh), vh)
  return {
    w, h,
    x: clamp(r.x, EDGE_KEEP_X - w, vw - EDGE_KEEP_X),
    y: clamp(r.y, 0, vh - EDGE_KEEP_Y),
  }
}

/** 首次打开的位置:右上角贴边,接近改造前的抽屉观感,只是不再顶天立地 */
export function defaultRect(vw: number, vh: number): PanelRect {
  const w = Math.min(DEF_W, vw - 2 * MARGIN)
  const h = Math.min(DEF_H, vh - 2 * MARGIN)
  return clampRect({ x: vw - w - MARGIN, y: MARGIN, w, h }, vw, vh)
}

function isFiniteNum(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v)
}

/** 读持久化几何;缺失/损坏/非有限数一律回默认,读到的合法值也要钳进当前视口 */
export function loadRect(vw: number, vh: number): PanelRect {
  try {
    const raw = localStorage.getItem(RECT_KEY)
    if (!raw) return defaultRect(vw, vh)
    const o = JSON.parse(raw)
    if (!o || !isFiniteNum(o.x) || !isFiniteNum(o.y) || !isFiniteNum(o.w) || !isFiniteNum(o.h)) {
      return defaultRect(vw, vh)
    }
    return clampRect({ x: o.x, y: o.y, w: o.w, h: o.h }, vw, vh)
  } catch {
    return defaultRect(vw, vh)   // localStorage 被禁用/配额异常时静默回默认
  }
}

export function saveRect(r: PanelRect): void {
  try {
    localStorage.setItem(RECT_KEY, JSON.stringify(r))
  } catch {
    /* 存不进去不影响本次使用,静默忽略 */
  }
}

export interface FloatingPanel {
  rect: Ref<PanelRect>
  dragging: Ref<boolean>
  resizing: Ref<boolean>
  onDragPointerDown: (e: PointerEvent) => void
  onResizePointerDown: (e: PointerEvent) => void
}

export function useFloatingPanel(): FloatingPanel {
  const rect = ref<PanelRect>(loadRect(window.innerWidth, window.innerHeight))
  const dragging = ref(false)
  const resizing = ref(false)

  let mode: 'drag' | 'resize' | null = null
  let activePointerId = -1
  let startX = 0
  let startY = 0
  let startRect: PanelRect = { x: 0, y: 0, w: 0, h: 0 }

  function begin(e: PointerEvent, m: 'drag' | 'resize') {
    if (e.button !== 0) return
    mode = m
    dragging.value = m === 'drag'
    resizing.value = m === 'resize'
    activePointerId = e.pointerId
    startX = e.clientX
    startY = e.clientY
    startRect = { ...rect.value }
    document.body.style.cursor = m === 'drag' ? 'move' : 'nwse-resize'
    document.body.style.userSelect = 'none'   // 拖动时别在页面上划出一片选中文本
    window.addEventListener('pointermove', onPointerMove)
    window.addEventListener('pointerup', onPointerUp)
    window.addEventListener('pointercancel', onPointerUp)
  }

  /** 标题栏起拖;其中的按钮/下拉/输入框要放行,否则点 × 会把面板拽走 */
  function onDragPointerDown(e: PointerEvent) {
    const t = e.target as HTMLElement | null
    if (t?.closest?.('button, select, input, a, textarea')) return
    begin(e, 'drag')
  }

  function onResizePointerDown(e: PointerEvent) {
    begin(e, 'resize')
  }

  function onPointerMove(e: PointerEvent) {
    if (!mode || e.pointerId !== activePointerId) return
    // delta 相对按下点累计,不用逐帧增量:丢帧/钳制都不会让面板跟手偏移
    const dx = e.clientX - startX
    const dy = e.clientY - startY
    const next = mode === 'drag'
      ? { ...startRect, x: startRect.x + dx, y: startRect.y + dy }
      : { ...startRect, w: startRect.w + dx, h: startRect.h + dy }
    rect.value = clampRect(next, window.innerWidth, window.innerHeight)
  }

  function onPointerUp(e: PointerEvent) {
    if (e.pointerId !== activePointerId) return
    teardown()
    saveRect(rect.value)
  }

  function teardown() {
    mode = null
    dragging.value = false
    resizing.value = false
    activePointerId = -1
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
    window.removeEventListener('pointermove', onPointerMove)
    window.removeEventListener('pointerup', onPointerUp)
    window.removeEventListener('pointercancel', onPointerUp)
  }

  function onViewportResize() {
    rect.value = clampRect(rect.value, window.innerWidth, window.innerHeight)
  }
  window.addEventListener('resize', onViewportResize)

  onBeforeUnmount(() => {
    teardown()
    window.removeEventListener('resize', onViewportResize)
  })

  return { rect, dragging, resizing, onDragPointerDown, onResizePointerDown }
}
