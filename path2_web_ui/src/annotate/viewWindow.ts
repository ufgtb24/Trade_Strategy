/**
 * 图窗 → 主图 dataZoom 的起止百分比:让图停在 [start, end] 这段日期上(两端含)。
 *
 * dates 是图上全部 K 线的日期(升序)。取第一根不早于 start 的、最后一根不晚于 end 的;
 * 这段里一根都没有就返回 null(调用方按默认缩放画)。
 */
import type { ViewWindow } from '../types'

export function zoomForWindow(dates: readonly string[], win: ViewWindow): { start: number; end: number } | null {
  const n = dates.length
  if (!n) return null
  const i = dates.findIndex(d => d >= win.start)
  let j = -1
  for (let k = n - 1; k >= 0; k--) { if (dates[k] <= win.end) { j = k; break } }
  if (i < 0 || j < i) return null
  return { start: (i / n) * 100, end: ((j + 1) / n) * 100 }
}
