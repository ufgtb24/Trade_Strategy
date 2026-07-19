/**
 * KlineChart.ts — 纯点击分流逻辑（无 Vue 依赖）
 *
 * 职责：接收 ECharts click 事件 payload，根据 seriesName 分流到 view store 的三个
 * 高层焦点 action（clearFocus / focusMatch / focusEvent）。归属判定（0/1/>1 match）
 * 等不变量已下沉到 view.ts::focusEvent 内部，本文件不再直接消费 matches/events/edges。
 */

import type { MatchDict } from '../types'
import type { useViewStore } from '../stores/view'

export type ChartClickPayload = {
  seriesName?: string
  data?: { event_id?: string; match_id?: string }
} | null

/** marker 分支覆盖的四种 series(点/区间/价格点/卫星);Task 18 shift+click 判定复用同一清单
 * (hoisted 到模块级,避免 handleChartClick 内部与 KlineChart.vue 各修一份漂移)。*/
export const MARKER_SERIES = ['points', 'intervals', 'price-points', 'satellites']

export type ShiftClickSource = 'main' | 'sub'

/**
 * 入口 D · shift+click 跨图累积(Task 18):2 击选定 (src,dst) → 触发 view.triggerPairQuery;
 * 第 3 击清空重来(保留新点作为下一轮的 src)。状态放 view.shiftSelectedEvents——同
 * selectedEventId/candidateMatchIds 既有模式,store 是 KlineChart↔DetailSidebar 唯一跨组件状态
 * 载体(两者皆零 props/零 emit,见 ChartArea.vue 组合关系)。与 handleChartClick 同测试范式:
 * 纯函数 + 真 Pinia store,不需要 mount .vue / echarts。
 */
export function handleShiftClick(
  event_id: string,
  class_id: string,
  source: ShiftClickSource,
  view: ReturnType<typeof useViewStore>,
): void {
  const cur = view.shiftSelectedEvents
  if (cur.length < 2) {
    const next = [...cur, { event_id, class_id, source }]
    view.setShiftSelectedEvents(next)
    if (next.length === 2) {
      void view.triggerPairQuery(next[0].event_id, next[1].event_id)
    }
  } else {
    view.setShiftSelectedEvents([{ event_id, class_id, source }])
  }
}

/**
 * 处理 ECharts chart.on('click', p) 事件,分流到 view store 三个高层 action。
 *
 * 分流规则(spec §3.3):
 *   空白 click       → view.clearFocus()
 *   brackets click   → view.focusMatch(match_id)
 *   MARKER_SERIES    → view.focusEvent(event_id) · 内部走归属判定 4 分支(0/1/>1 归属)
 *
 * @param p       ECharts click payload(空白点击时为 null 或 seriesName 缺失)
 * @param matches 当前 effectiveAnalysis.matches(保签名兼容,不再直接消费 —— focusEvent 内部读)
 * @param view    useViewStore() 实例
 */
export function handleChartClick(
  p: ChartClickPayload,
  matches: MatchDict[],
  view: ReturnType<typeof useViewStore>,
): void {
  if (!p || !p.seriesName) {
    view.clearFocus()
    return
  }
  if (p.seriesName === 'brackets' && p.data?.match_id) {
    // focusMatch 里不校验存在(简化);消费方无 bracket 不会触发该分支。
    view.focusMatch(p.data.match_id)
    return
  }
  if (MARKER_SERIES.includes(p.seriesName) && p.data?.event_id) {
    view.focusEvent(p.data.event_id)
    return
  }
}
