/**
 * 左右栏的收起与拖宽:几何的常数与纯函数(组件只管量和画,怎么夹宽度都在这里)。
 *
 * - 左栏(四档,components/LeftPanel.vue)像抽屉:清单按内容排成自己的宽度(最少 LEFT_FLOOR、最多半屏,
 *   叫「内容全宽」),拖边不重排内容,只改露出多少;从靠图的一侧遮起,代码列在最左、最后遮。
 *   露出宽度夹在 [LEFT_MIN, 内容全宽] 里;拖到内容全宽就记成「全开」(null),换到更宽的内容也全开。
 * - 右栏(annotate / compare 的标注侧栏、app / scan 的诊断侧栏,components/ChartArea.vue)内容跟着宽度重排;
 *   没拖过时是各自原来的宽度,拖宽夹在 [最窄, 半屏] 里。
 * - 拖到最窄就停,不会拖成收起:收起只靠箭头和 Shift+L / Shift+R。
 *
 * 数值是会话默认(spec 第 10 节「左栏抽屉的边界」「右栏拖宽的边界」,detail 类,用起来再调)。
 */

/** 左栏内容全宽的下限:内容不足这么宽时按这么宽算(沿用原来左栏「最少 220px」)。 */
export const LEFT_FLOOR = 220
/** 左栏拖到最窄的固定宽度:刚好露出代码列(找图清单三页、扫描列表的 symbol 列都在最左)。 */
export const LEFT_MIN = 70
/** 标注侧栏:没拖过时的宽度(原来的固定宽度)与最窄(字段名一列 + 值一列不挤坏)。 */
export const ANN_DEFAULT = 320
export const ANN_MIN = 260
/** 诊断侧栏:没拖过时的宽度(原来的固定宽度)与最窄。 */
export const DETAIL_DEFAULT = 280
export const DETAIL_MIN = 220

/**
 * 左栏拖到 w(CSS 像素)时记下的露出宽度。
 * full:当前内容的全宽(已含 LEFT_FLOOR 与半屏两道边)。夹在 [LEFT_MIN, full] 里;到了 full 记 null(全开)。
 */
export function leftDragged(w: number, full: number): number | null {
  if (w >= full - 0.5) return null
  return Math.round(Math.max(LEFT_MIN, w))
}

/**
 * 右栏拖到 w 时记下的宽度:夹在 [min, 半屏] 里(半屏不足 min 时取 min)。
 * viewportW:窗口宽度(CSS 像素)。
 */
export function rightDragged(w: number, min: number, viewportW: number): number {
  return Math.round(Math.min(Math.max(min, viewportW / 2), Math.max(min, w)))
}

/** 右栏的样式:没拖过用默认宽度;窗口变窄时 CSS 再按半屏截一道,但不窄过 min。 */
export function rightStyle(dragged: number | null, dflt: number, min: number): Record<string, string> {
  return { width: `${dragged ?? dflt}px`, maxWidth: '50vw', minWidth: `${min}px` }
}
