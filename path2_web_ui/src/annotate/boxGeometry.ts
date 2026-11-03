/**
 * 图上画框的几何与判定(纯函数,像素与 K 线下标之间的换算由调用方给):
 * - 按下后移动超过 DRAG_PX 才算拖动画框,否则算点一下(选中);
 * - 按在框的左右边 EDGE_PX 以内拖,是改这个框的起止;
 * - 框的起止日期与 K 线下标互换;
 * - 在成交量带上拖动是平移图窗(K 线区的拖动留给画框)。
 */
import { rankOf } from './membership'

export const DRAG_PX = 4     // 待验证:移动超过这么多像素才算拖动
export const EDGE_PX = 5     // 待验证:离框左右边这么多像素以内按下,是改起止

/** 从按下的点到现在的点,是否已经算拖动。 */
export function isDrag(x0: number, y0: number, x: number, y: number): boolean {
  return Math.hypot(x - x0, y - y0) > DRAG_PX
}

/** 两次落点的下标 → 框的起止下标(左小右大)。 */
export function spanOf(i0: number, i1: number): [number, number] {
  return i0 <= i1 ? [i0, i1] : [i1, i0]
}

/** 改起止:拖左边时起点跟着走、不越过终点;拖右边同理。 */
export function resized(s: number, e: number, side: 'l' | 'r', i: number): [number, number] {
  return side === 'l' ? [Math.min(i, e), e] : [s, Math.max(i, s)]
}

export interface BoxPx { id: string; left: number; right: number; top: number; bottom: number }

/** 落在哪个框上(后画的盖在上面,倒着找)。 */
export function boxAt(rects: readonly BoxPx[], x: number, y: number): BoxPx | null {
  for (let i = rects.length - 1; i >= 0; i--) {
    const r = rects[i]
    if (x >= r.left - EDGE_PX && x <= r.right + EDGE_PX && y >= r.top && y <= r.bottom) return r
  }
  return null
}

/** 按下的点离这个框的哪条边在 EDGE_PX 以内:'l'、'r' 或 null(离两边一样近时取近的那边)。 */
export function edgeOf(r: BoxPx, x: number): 'l' | 'r' | null {
  const dl = Math.abs(x - r.left), dr = Math.abs(x - r.right)
  if (Math.min(dl, dr) > EDGE_PX) return null
  return dl <= dr ? 'l' : 'r'
}

/** 框起点日期 → K 线下标(起点不在 K 线上时取它之后的第一根)。 */
export function startIndex(dates: readonly string[], d: string): number {
  return Math.min(rankOf(dates, d), dates.length - 1)
}

/** 框终点日期 → K 线下标(终点不在 K 线上时取它之前的最后一根)。 */
export function endIndex(dates: readonly string[], d: string): number {
  const i = rankOf(dates, d)
  return Math.max(0, i < dates.length && dates[i] === d ? i : i - 1)
}

/**
 * 在成交量带上拖了 dx 像素后的图窗(dataZoom 起止百分比):往右拖看更早的 K 线。
 * widthPx 是图区宽度;起止宽度不变,夹在 0~100 之间。
 */
export function pannedZoom(start: number, end: number, dx: number, widthPx: number): { start: number; end: number } {
  if (widthPx <= 0) return { start, end }
  const span = end - start
  let s = start - (dx / widthPx) * span
  s = Math.max(0, Math.min(100 - span, s))
  return { start: s, end: s + span }
}
