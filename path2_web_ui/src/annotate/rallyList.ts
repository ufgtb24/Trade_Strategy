/**
 * 大涨段清单(顶栏 rally)的排序与显示格式。按 symbol / date / rise 三列排,
 * 同值时按 date、symbol 定序,保证每次排出来一样。
 */
import type { RallyItem } from '../types'

export const RALLY_SORT_KEYS = ['symbol', 'date', 'rise'] as const
export type RallySortKey = typeof RALLY_SORT_KEYS[number]

function cmp(a: RallyItem, b: RallyItem, key: RallySortKey): number {
  if (key === 'rise') return a.rise - b.rise
  return a[key] < b[key] ? -1 : a[key] > b[key] ? 1 : 0
}

export function sortRally(items: readonly RallyItem[], key: RallySortKey, desc: boolean): RallyItem[] {
  return [...items].sort((a, b) => {
    const c = cmp(a, b, key)
    if (c !== 0) return desc ? -c : c
    return cmp(a, b, 'date') || cmp(a, b, 'symbol')
  })
}

/** 涨幅写成带符号的百分数,一位小数:0.4567 → +45.7%。 */
export function formatRise(rise: number): string {
  return `${rise >= 0 ? '+' : ''}${(rise * 100).toFixed(1)}%`
}
