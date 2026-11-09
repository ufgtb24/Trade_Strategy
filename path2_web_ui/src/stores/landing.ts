/**
 * 落到 compare 的某一天:侧栏 feedback 页点一行、落在 compare 的直达链接(格式见 annotate/directLinks.ts)都走这里。
 *
 * land(symbol, win, day, onLanded):按代码打开那只股票(view.openSymbol)、图窗停在 win 上,不在 compare 就切进去
 * (stores/appLink.ts 的 setMode,能不能切由调用方先核过),记下一个「待落的那天」;等这张图的 K 线重读完,
 * 把当前日竖线停在 day(那天不是交易日就取它之后的第一根)。
 *
 * 谁来落:compare 下 K 线或 app 的现算结果到了,图会做默认聚焦(components/KlineChart.vue:有选中的样本 / 框就聚焦它,
 * 否则聚焦离图窗中心最近的样本)。默认聚焦先问 claim():有待落的那天、而且这张图的 K 线已经是 land 之后重读的,
 * 就由它落下这一天并消费掉,默认聚焦不再挑样本;K 线还没重读完(换股票时现算结果先到)就先不落,等 K 线到了的
 * 那次默认聚焦再落。只有 app 没跑成(runStatus 为 load_failed)、默认聚焦不会发生时,才由这里自己在 K 线到了
 * 以后落下。
 * 落到别的股票、离开 compare、或者又落一次时,没落下的作废。
 *
 * 落下时先清掉 app 的焦点(样本与它配对的 hit),图上只剩那根竖线;onLanded 在落下后调(侧栏点行用它选中那条反馈)。
 */
import { defineStore } from 'pinia'
import { watch } from 'vue'
import type { ViewWindow } from '../types'
import { useAppLinkStore } from './appLink'
import { useViewStore } from './view'

/** day 在交易日里的下标;那天不是交易日取它之后的第一根,比最后一根还晚为 null。 */
export function dayIndexOnOrAfter(dates: readonly string[], day: string): number | null {
  const i = dates.findIndex(d => d >= day)
  return i < 0 ? null : i
}

/** 待落的那天:哪只股票、哪天、land 时的 K 线(重读后是新的数组)、落下后调什么、作废时拆掉什么。 */
interface Pending {
  symbol: string
  day: string
  before: readonly string[]
  onLanded?: () => void
  stop: () => void
}

export const useLandingStore = defineStore('landing', () => {
  const view = useViewStore()
  let pending: Pending | null = null

  /** 没落下的作废。 */
  function cancel(): void {
    pending?.stop()
    pending = null
  }

  /** 落到别的股票或离开了 compare。 */
  const off = (p: Pending) => view.symbol !== p.symbol || !view.comparing

  /** 落下:当前日竖线停在那天,消费掉。 */
  function apply(p: Pending): void {
    cancel()
    view.clearFocus()
    view.setCurrentDay(dayIndexOnOrAfter(view.barDates, p.day))
    p.onLanded?.()
  }

  /** 打开那只股票、落在 compare,记下待落的那天;返回落没落进 compare(没落进就什么都不记)。 */
  function land(symbol: string, win: ViewWindow, day: string, onLanded?: () => void): boolean {
    cancel()
    const appLink = useAppLinkStore()
    const before = view.barDates
    view.openSymbol(symbol, win)
    if (!view.comparing) appLink.setMode('compare')
    if (!view.comparing) return false

    // app 没跑成时默认聚焦不会发生:K 线一到由这里落下
    const unwatch = watch([() => view.barDates, () => appLink.runStatus, () => view.symbol, () => view.mode], () => {
      if (pending !== me) return
      if (off(me)) { cancel(); return }
      if (appLink.runStatus === 'load_failed' && view.barDates !== me.before) apply(me)
    })
    const me: Pending = { symbol, day, before, onLanded, stop: unwatch }
    pending = me
    return true
  }

  /**
   * 默认聚焦(components/KlineChart.vue)挑样本之前先问:有待落的那天、而且这张图的 K 线已经重读过,就落下它、
   * 消费掉,返回 true(默认聚焦不再挑样本);没有返回 false。落到别的股票、离开了 compare 的,顺手作废。
   */
  function claim(): boolean {
    const p = pending
    if (!p) return false
    if (off(p)) { cancel(); return false }
    if (view.barDates === p.before) return false
    apply(p)
    return true
  }

  return { land, claim, cancel }
})
