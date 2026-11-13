/**
 * KlineChart.ts — 纯点击分流逻辑（无 Vue 依赖）
 *
 * 职责：接收 ECharts click 事件 payload，根据 seriesName 分流到 view store 的选中动作
 * （clearFocus / clickBuyDay / clickHitCell / clickFamilyLine / focusMark）:点什么就选中什么。
 * 选中的那条路径怎么落到图上由 view.ts 统一做，本文件不直接消费 hits/events/edges。
 */

import type { HitDict } from '../types'
import type { useViewStore } from '../stores/view'
import { FEEDBACK_SERIES } from '../render/feedbackStrip'
import { familyKeyOf, HIT_FAMILY_PREFIX } from '../render/fold'

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
 * selectedInstanceId 等既有模式,store 是 KlineChart↔DetailSidebar 唯一
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
 * 处理 ECharts chart.on('click', p) 事件:点的是什么,选中的就是什么(view store 里的那条路径,render/select.ts)。
 *
 * 分流规则(点什么就选中什么,见 stores/view.ts):
 *   空白 click       → view.clearFocus()
 *   brackets click   → 买入日 ▼、和它同一列的格:view.clickBuyDay(那一族, 那天),选中这一天整体;
 *                      没有 ▼ 的那一列的格:view.clickHitCell(那一族, 格上的 hit),选中其中一次 hit
 *   MARKER_SERIES    → view.focusMark(记号上的成员):选中其中一个 event(价格点只有一个成员)
 *   bracket-lines    → 族底线那一行(透明命中区):view.clickFamilyLine(那一族),选中整族
 *   feedback-strip   → compare 的反馈带记号:选中那条反馈(由调用方 handleAppClick 做)
 *   返回 true = 点中了 app 的东西(compare 下调用方据此取消标注框的选中,免得 Delete 删到框)。
 *
 * @param p       ECharts click payload(空白点击时为 null 或 seriesName 缺失)
 * @param hits 当前 effectiveAnalysis.hits(保签名兼容,不再直接消费 —— view store 自己读)
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
    // 族键缺省时按这次 hit 的起点认族(图上的数据项都带族键)
    const start = view.effectiveAnalysis?.hits.find(m => m.hit_id === d.hit_id)?.start_idx
    const fk = d.family_key ?? (start !== undefined ? familyKeyOf(HIT_FAMILY_PREFIX, start) : null)
    if (!fk) return true
    // ▼ 和它那一列的格都选中这一天;没有 ▼ 的那一列(hit 的终点不是买点日)选中格里的一次 hit
    if (typeof d.buy_day === 'number') view.clickBuyDay(fk, d.buy_day)
    else view.clickHitCell(fk, d.hit_ids ?? [d.hit_id])
    return true
  }
  if (p.seriesName === 'bracket-lines' && d?.family_key) {
    // 代价(spec 6.13):格与格之间的空白原来点了是清选中,现在点到这一族;返回 true 让 compare 照旧取消框的选中
    view.clickFamilyLine(d.family_key)
    return true
  }
  if (p.seriesName === FEEDBACK_SERIES && d?.feedback_id) return true
  if (MARKER_SERIES.includes(p.seriesName) && d?.instance_id) {
    view.focusMark(d.member_ids ?? [d.instance_id])
    return true
  }
  return false
}


/** compare 下点中的反馈带记号是哪一条(它的编号);点的不是记号时为 null。 */
export function feedbackMarkOf(p: ChartClickPayload): string | null {
  return p?.seriesName === FEEDBACK_SERIES && p.data?.feedback_id ? p.data.feedback_id : null
}

/** handleAppClick 要的 compare 上下文:是否在 compare、app 是否跑完可对照、怎么取消框的选中、怎么选中一条反馈。 */
export interface AppClickCtx {
  comparing: boolean
  compareReady: boolean
  selectBox: (id: null) => void
  feedback: { select: (id: string | null) => void }
}

/**
 * 主图、副图的一次系列点击(KlineChart.vue 的 onAppClick 就是它):焦点照旧走 handleChartClick;
 * compare 下点中 app 的东西(格、条、▼、族那一行、反馈记号)时取消标注框的选中(否则框仍选中,按 Delete 会删掉标注);
 * app 跑完可对照时,点反馈记号选中那条反馈(换掉原来选中的;它收进来的 hit 画细框)。
 * 点只选中,不开反馈面板:面板由 Enter 或显示栏的 feedback 按钮对选中的那一个打开(stores/feedback.ts 的 openSelected)。
 * 返回 handleChartClick 的结果。
 */
export function handleAppClick(p: ChartClickPayload, hits: HitDict[],
                               view: ReturnType<typeof useViewStore>, ctx: AppClickCtx): boolean {
  const hitApp = handleChartClick(p, hits, view)
  if (hitApp && ctx.comparing) ctx.selectBox(null)
  if (!ctx.compareReady) return hitApp
  const id = feedbackMarkOf(p)
  if (id) {
    view.clickFeedback({ id })
    ctx.feedback.select(id)
  }
  return hitApp
}
