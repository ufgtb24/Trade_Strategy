/**
 * KlineChart.ts — 纯点击分流逻辑（无 Vue 依赖）
 *
 * 职责：接收 ECharts click 事件 payload，根据 seriesName 分流到 view store 的三个
 * 高层焦点 action（clearFocus / focusHit / focusEvent）。归属判定（0/1/>1 hit）
 * 等不变量已下沉到 view.ts::focusEvent 内部，本文件不再直接消费 hits/events/edges。
 */

import type { HitDict } from '../types'
import type { useViewStore } from '../stores/view'
import type { FeedbackRange } from '../annotate/feedback'
import type { PanelAt } from '../stores/feedback'
import { FEEDBACK_SERIES } from '../render/feedbackStrip'

export type ChartClickPayload = {
  seriesName?: string
  data?: {
    instance_id?: string; hit_id?: string
    // 折叠后的记号(render/chart.ts computeEventData):成员 / hit 列表、族键、记号跨度;bracket 记录分 mark / buy
    member_ids?: string[]; hit_ids?: string[]; family_key?: string; value?: number[]
    kind?: 'mark' | 'buy'; buy_day?: number
    // 族底线(bracket-lines)那一行:族起点与这一族全部买入日(K 线下标);反馈带(feedback-strip)的记号:反馈编号
    family_start?: number; buy_days?: number[]; feedback_id?: string
  }
} | null

/** marker 分支覆盖的三种 series(点/区间/价格点;卫星 pk 通道已删,Task 7);
 * shift+click 判定复用同一清单(hoisted 到模块级,避免 handleChartClick 内部与 KlineChart.vue 各修一份漂移)。*/
export const MARKER_SERIES = ['points', 'intervals', 'price-points']

export type ShiftClickSource = 'main' | 'sub'

/**
 * 入口 D · shift+click 跨图累积:2 击选定 (src,dst) → 触发 view.triggerPairQuery;
 * 第 3 击清空重来(保留新点作为下一轮的 src)。状态放 view.shiftSelectedEvents——同
 * selectedInstanceId/candidateHitIds 既有模式,store 是 KlineChart↔DetailSidebar 唯一
 * 跨组件状态载体(两者皆零 props/零 emit,见 ChartArea.vue 组合关系)。与 handleChartClick
 * 同测试范式:纯函数 + 真 Pinia store,不需要 mount .vue / echarts。
 * 实例化契约:参数是 instance_id / node_id(取代旧的复合身份参数)。
 */
export function handleShiftClick(
  instance_id: string,
  node_id: string,
  source: ShiftClickSource,
  view: ReturnType<typeof useViewStore>,
): void {
  const cur = view.shiftSelectedEvents
  if (cur.length < 2) {
    const next = [...cur, { instance_id, node_id, source }]
    view.setShiftSelectedEvents(next)
    if (next.length === 2) {
      void view.triggerPairQuery(next[0].instance_id, next[1].instance_id)
    }
  } else {
    view.setShiftSelectedEvents([{ instance_id, node_id, source }])
  }
}

/**
 * 处理 ECharts chart.on('click', p) 事件,分流到 view store 三个高层 action。
 *
 * 分流规则(spec §3.3):
 *   空白 click       → view.clearFocus()
 *   brackets click   → 买入日 ▼:view.focusBuyDay(那天, 买在那天的 hit);hit 的记号:view.focusHits(记号上的 hit)
 *   MARKER_SERIES    → view.focusMark(记号上的成员)(几个成员的归属合起来;价格点只有一个成员)
 *   bracket-lines    → compare 下族底线那一行(透明命中区,只在 compare 可点):只设当家行为这一族,不动别的焦点
 *                      (不走 focusHits:几次 hit 买点日不同时它会进待选);family 反馈面板由调用方另开
 *   feedback-strip   → compare 的反馈带记号:不动焦点(打开那条反馈由调用方做)
 *   三处同一条点击规则(见 view store 的 focusHits):0 次 hit 只聚焦成员、1 次直选、几次买入日完全一样直选第一次、
 *   买入日不全一样进待选。都带上当家行(记号所在的族);当前日 = band 记号的终点 / ▼ 那天 / 选中那次 hit 的第一个买入日。
 *   返回 true = 点中了 app 的东西(compare 下调用方据此取消标注框的选中,免得 Delete 删到框)。
 *
 * @param p       ECharts click payload(空白点击时为 null 或 seriesName 缺失)
 * @param hits 当前 effectiveAnalysis.hits(保签名兼容,不再直接消费 —— focusEvent 内部读)
 * @param view    useViewStore() 实例
 */
export function handleChartClick(
  p: ChartClickPayload,
  hits: HitDict[],
  view: ReturnType<typeof useViewStore>,
): boolean {
  if (!p || !p.seriesName) {
    view.clearFocus()
    return false
  }
  const d = p.data
  if (p.seriesName === 'brackets' && d?.hit_id) {
    const family = d.family_key
    if (d.kind === 'buy' && typeof d.buy_day === 'number') {
      view.focusBuyDay(d.buy_day, d.hit_ids ?? [d.hit_id], family)
    } else {
      // 当前日缺省取选中那次 hit 的第一个买入日;待选时不画竖线
      view.focusHits(d.hit_ids ?? [d.hit_id], { family })
    }
    return true
  }
  if (p.seriesName === 'bracket-lines' && d?.family_key) {
    // 代价(spec 6.13):格与格之间的空白原来点了是清选中,现在点到这一族;返回 true 让 compare 照旧取消框的选中
    view.setActiveFamily({ kind: 'bracket', key: d.family_key })
    return true
  }
  if (p.seriesName === FEEDBACK_SERIES && d?.feedback_id) return true
  if (MARKER_SERIES.includes(p.seriesName) && d?.instance_id) {
    const members = d.member_ids ?? [d.instance_id]
    const day = d.value?.[1]
    view.focusMark(members, { day: typeof day === 'number' && p.seriesName !== 'price-points' ? day : undefined,
                              family: d.family_key })
    return true
  }
  return false
}


/**
 * compare 下一次副图点击要发起的反馈(spec 6.13「三种对象落成一段日期」);不是反馈对象时为 null。
 *   ▼(brackets 的 buy)            → point,start = end = 那天;
 *   格(brackets 的 mark)            → 这一格那一列有 ▼ 时 point(那天),没有不发起;
 *   族底线那一行(bracket-lines)    → 族里有买入日时 family:start / end = 全部 ▼ 的最早 / 最晚,family_start = 族起点;
 *   反馈带记号(feedback-strip)      → {id}:打开那条。
 * 图数据里的日子都是 K 线下标,经 dates 换成日期(存储只收日期);换不出来的不发起。同范围已有反馈时打开那条
 * 由 stores/feedback.ts 的 open 处理。只认日子,不认是哪个 hit。
 */
export function feedbackClickTarget(p: ChartClickPayload, dates: readonly string[],
                                    symbol: string | null): FeedbackRange | { id: string } | null {
  if (!p?.seriesName || !p.data) return null
  const d = p.data
  if (p.seriesName === FEEDBACK_SERIES) return d.feedback_id ? { id: d.feedback_id } : null
  if (!symbol) return null
  const day = (i: number | undefined) => (typeof i === 'number' ? dates[i] ?? null : null)
  if (p.seriesName === 'brackets' && typeof d.buy_day === 'number') {
    const date = day(d.buy_day)
    return date ? { symbol, start: date, end: date, target: 'point' } : null
  }
  if (p.seriesName === 'bracket-lines' && d.buy_days?.length) {
    const start = day(Math.min(...d.buy_days))
    const end = day(Math.max(...d.buy_days))
    const familyStart = day(d.family_start)
    return start && end && familyStart
      ? { symbol, start, end, target: 'family', family_start: familyStart }
      : null
  }
  return null
}

/** handleAppClick 要的 compare 上下文:是否在 compare、app 是否跑完可对照、这只股票的交易日与代码、怎么取消框的选中、
 *  反馈 store 里用到的两个动作(选中一条、在某处打开面板)。 */
export interface AppClickCtx {
  comparing: boolean
  compareReady: boolean
  dates: readonly string[]
  symbol: string | null
  selectBox: (id: null) => void
  feedback: { select: (id: string | null) => void; open: (at: PanelAt, what: FeedbackRange | { id: string }) => boolean }
}

/**
 * 主图、副图的一次系列点击(KlineChart.vue 的 onAppClick 就是它):焦点照旧走 handleChartClick;
 * compare 下点中 app 的东西(格、条、▼、族那一行、反馈记号)时取消标注框的选中(否则框仍选中,按 Delete 会删掉标注);
 * app 跑完可对照时,点 ▼ / 那一列有 ▼ 的格 / 有 ▼ 的族 / 反馈记号,另在点击处(原生事件的 clientX / clientY,视口坐标)
 * 打开反馈面板,点记号时先选中那条。返回 handleChartClick 的结果。
 */
export function handleAppClick(p: ChartClickPayload & { event?: { event?: MouseEvent } }, hits: HitDict[],
                               view: ReturnType<typeof useViewStore>, ctx: AppClickCtx): boolean {
  const hitApp = handleChartClick(p, hits, view)
  if (hitApp && ctx.comparing) ctx.selectBox(null)
  if (!ctx.compareReady) return hitApp
  const what = feedbackClickTarget(p, ctx.dates, ctx.symbol)
  const ev = p?.event?.event
  if (!what || !ev) return hitApp
  if ('id' in what) ctx.feedback.select(what.id)
  ctx.feedback.open({ x: ev.clientX, y: ev.clientY }, what)
  return hitApp
}
