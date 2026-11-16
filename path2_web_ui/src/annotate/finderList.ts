/**
 * 标注三档左栏找图清单(components/FinderList.vue)的派生量:每一行标过什么、全部标过的股票、翻页落到哪一行。
 * 只读标注状态(含还没存完的动作,stores/annotation.ts 的 state)和已有的大涨段清单,不碰网络与界面。
 * 三页只列用户自己存下的东西(加上这次 random 抽到的图):不出现 app 的任何结果,也不记看过什么。
 *
 * 「标过」按一行的图窗 [start, end] 算(两端都含,日期是 YYYY-MM-DD 字符串,可直接比大小):
 * - 样本日落在图窗里的样本才计 pattern 名,悬停列出这些样本;没归 pattern 的样本记作 unsorted(pattern 为 null);
 * - 框和图窗有重叠(打开这张图看得见它的一部分)就计进框数。框数让「只画了框」和「完全没碰」看得出区别。
 *
 * charts 页一只股票一行:这只股票上有框或有样本就列,只画了框的也列;只有反馈的不列——反馈是在 compare 里
 * 对 app 买点的作答,不是自己标出的形状,列进来就把「app 在这买过」带进了标注三档的左栏。
 */
import type { AnnChart, AnnState } from './model'
import type { ViewWindow } from '../types'

/** 一行里列出的一个样本(悬停时看)。 */
export interface MarkedSample { id: string; date: string; pattern: string | null; judgment: 'pos' | 'neg' }

/** 一行标过什么:pattern 名(去重,按名字排,unsorted 即 null 排最后)、这些样本(按日期)、框数。 */
export interface Marks {
  patterns: (string | null)[]
  samples: MarkedSample[]
  boxes: number
}

/** charts 页的一行:一只股票上全部的样本与框,另数出正、负样本数。 */
export interface ChartsRow extends Marks { symbol: string; pos: number; neg: number }

export const NO_MARKS: Marks = { patterns: [], samples: [], boxes: 0 }

/** 股票 → 它在标注状态里的那张图;状态还没读到时为空表。 */
export function chartsBySymbol(state: AnnState | null): Map<string, AnnChart> {
  return new Map((state?.charts ?? []).map(c => [c.symbol, c]))
}

function patternOrder(a: string | null, b: string | null): number {
  if (a === b) return 0
  if (a === null) return 1
  if (b === null) return -1
  return a < b ? -1 : 1
}

function marksOf(chart: AnnChart, keepDay: (d: string) => boolean,
                 keepBox: (start: string, end: string) => boolean): Marks {
  const samples = chart.samples
    .filter(s => keepDay(s.date))
    .map(s => ({ id: s.id, date: s.date, pattern: s.pattern, judgment: s.judgment }))
    .sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : a.id < b.id ? -1 : 1))
  const patterns = [...new Set(samples.map(s => s.pattern))].sort(patternOrder)
  const boxes = chart.boxes.filter(b => keepBox(b.start, b.end)).length
  return { patterns, samples, boxes }
}

/** 一张图在图窗 win 里标过什么(rally、random 页的一行);这只股票没标过为 NO_MARKS。 */
export function marksInWindow(chart: AnnChart | undefined, win: ViewWindow): Marks {
  if (!chart) return NO_MARKS
  return marksOf(chart, d => win.start <= d && d <= win.end, (s, e) => s <= win.end && e >= win.start)
}

/** charts 页:全部标过的股票(有框或有样本),按代码排。 */
export function chartsRows(state: AnnState | null): ChartsRow[] {
  return (state?.charts ?? [])
    .filter(c => c.boxes.length > 0 || c.samples.length > 0)
    .map(c => {
      const m = marksOf(c, () => true, () => true)
      const pos = m.samples.filter(s => s.judgment === 'pos').length
      return { symbol: c.symbol, ...m, pos, neg: m.samples.length - pos }
    })
    .sort((a, b) => (a.symbol < b.symbol ? -1 : a.symbol > b.symbol ? 1 : 0))
}

/**
 * PageUp / PageDown 翻到哪一行:n 行、当前在 cur(不在这一页为 -1)。当前图不在这一页时从第一行起;
 * 到头就停在头上。返回要换到的那一行,不用换(没有行、已在头上)时为 null。
 */
export function stepIndex(n: number, cur: number, key: 'PageUp' | 'PageDown'): number | null {
  if (n === 0) return null
  if (cur < 0) return 0
  const next = key === 'PageDown' ? Math.min(cur + 1, n - 1) : Math.max(cur - 1, 0)
  return next === cur ? null : next
}
