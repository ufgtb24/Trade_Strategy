// Ctrl+wheel 右锚定 x 缩放纯函数(承 BreakoutStrategy/UI/charts/axes_interaction.py 参考实现)。
//
// ECharts dataZoom 的 start/end 百分比模型(0-100)下,「缩放不动点锁定当前视图最右侧 K 线」
// 退化为「end 不动、只动 start」:
//   new_start = end - (end - start) * factor
// 参考实现里 anchor = min(xlim[1], n_bars-0.5) 的右界约束在此模型下天然消失
// (end ≤ 100 恒不越过最后一根 K 线),无需处理。

export const CTRL_ZOOM_IN_FACTOR = 0.85 // 上滚(deltaY<0):窗口宽 ×0.85 = 放大
export const CTRL_ZOOM_OUT_FACTOR = 1 / 0.85 // 下滚:÷0.85 = 缩小(与放大精确互逆)
export const CTRL_ZOOM_MIN_SPAN_BARS = 3 // 最小可见 3 根 K 线(承参考实现 MIN_WIDTH)

/**
 * 右锚定缩放:end 不动只动 start。
 * @param start 当前 dataZoom start 百分比(0-100)
 * @param end   当前 dataZoom end 百分比(0-100)
 * @param deltaY wheel 事件 deltaY(负=上滚放大,正=下滚缩小)
 * @param nBars K 线总根数(换算最小 span 百分比用)
 * @returns 新窗口 {start, end};null = no-op(入参无效 / clamp 后无变化),调用方不 dispatch
 */
export function computeRightAnchoredZoom(
  start: number,
  end: number,
  deltaY: number,
  nBars: number,
): { start: number; end: number } | null {
  if (nBars <= 0 || deltaY === 0 || end <= start) return null
  const factor = deltaY < 0 ? CTRL_ZOOM_IN_FACTOR : CTRL_ZOOM_OUT_FACTOR
  // 3 bar 换算百分比;nBars<3 时整个数据都不足 3 根,clamp 到 100
  const minSpan = Math.min(100, (CTRL_ZOOM_MIN_SPAN_BARS / nBars) * 100)
  const span = Math.max(minSpan, (end - start) * factor)
  const newStart = Math.max(0, end - span) // start ≥ 0(zoom-out 到满幅即止)
  if (newStart === start) return null
  return { start: newStart, end }
}
