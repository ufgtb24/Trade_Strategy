/**
 * 左右栏的收起与拖宽:几何的常数与纯函数(组件只管量和画,怎么夹宽度都在这里)。
 *
 * - 左栏(四档,components/LeftPanel.vue)像抽屉:清单按内容排成自己的宽度(最少 LEFT_FLOOR、最多半屏,
 *   叫「内容全宽」),拖栏边不重排内容,只改露出多少;从靠图的一侧遮起,代码列在最左、最后遮。
 *   露出宽度 = min(记下的宽度, 内容全宽);记下的宽度是 null 时全开。
 * - 右栏(annotate / compare 的标注侧栏、app / scan 的诊断侧栏,components/ChartArea.vue)内容跟着宽度重排;
 *   没拖过时用各自的默认宽度,拖宽夹在 [最窄, 半屏] 里。
 * - 拖到最窄就停,不会拖成收起:收起只靠栏边的小箭头和 Shift+L / Shift+R。
 *
 * 数值是会话默认(spec 第 10 节「左栏抽屉的边界」「右栏拖宽的边界」,detail 类,用起来再调)。
 */

/** 左栏内容全宽的下限:内容不足这么宽时按这么宽算。 */
export const LEFT_FLOOR = 220
/** 左栏拖到最窄的固定宽度:刚好露出代码列(找图清单三页、扫描列表的 symbol 列都在最左)。 */
export const LEFT_MIN = 70

/** 右栏的宽度范围:没拖过时的宽度与最窄(最宽统一是半屏)。 */
export interface RightSize { dflt: number; min: number }
/** 标注侧栏:最窄时字段名一列加值一列不挤坏(在真浏览器里看过四个页签)。 */
export const ANN_SIZE: RightSize = { dflt: 320, min: 260 }
/** 诊断侧栏。 */
export const DETAIL_SIZE: RightSize = { dflt: 280, min: 220 }

/**
 * 左栏拖到 w(CSS 像素)时记下的宽度。
 * full:当前内容的全宽(已含 LEFT_FLOOR 与半屏两道边);prev:拖之前记下的宽度。
 * - 夹在 [LEFT_MIN, full] 里,取整;
 * - 拖到或拖过 full:先前记下的宽度本来就不小于 full 时(这一页内容窄、栏边已经在最外面,往外拖拖不动)照旧,
 *   换回内容宽的页时还是先前拖出的宽度;否则记 null(全开)。
 */
export function leftDragged(w: number, full: number, prev: number | null): number | null {
  if (w >= full - 0.5) return prev !== null && prev >= full ? prev : null
  return Math.round(Math.max(LEFT_MIN, w))
}

/**
 * 右栏拖到 w 时记下的宽度:夹在 [最窄, 半屏] 里(半屏不足最窄时取最窄)。
 * viewportW:窗口宽度(CSS 像素)。
 */
export function rightDragged(w: number, size: RightSize, viewportW: number): number {
  return Math.round(Math.min(Math.max(size.min, viewportW / 2), Math.max(size.min, w)))
}

/** 右栏的样式:没拖过用默认宽度;窗口变窄时 CSS 再按半屏截一道,但不窄过最窄。 */
export function rightStyle(dragged: number | null, size: RightSize): Record<string, string> {
  return { width: `${dragged ?? size.dflt}px`, maxWidth: '50vw', minWidth: `${size.min}px` }
}
