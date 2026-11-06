/**
 * KlineChart.ts — 纯点击分流逻辑（无 Vue 依赖）
 *
 * 职责：接收 ECharts click 事件 payload，根据 seriesName 分流到 view store 的三个
 * 高层焦点 action（clearFocus / focusHit / focusEvent）。归属判定（0/1/>1 hit）
 * 等不变量已下沉到 view.ts::focusEvent 内部，本文件不再直接消费 hits/events/edges。
 */

import type { HitDict } from '../types'
import type { useViewStore } from '../stores/view'

export type ChartClickPayload = {
  seriesName?: string
  data?: {
    instance_id?: string; hit_id?: string
    // 折叠后的记号(render/chart.ts computeEventData):成员 / hit 列表、族键、记号跨度;bracket 记录分 mark / buy
    member_ids?: string[]; hit_ids?: string[]; family_key?: string; value?: number[]
    kind?: 'mark' | 'buy'; buy_day?: number
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
  if (MARKER_SERIES.includes(p.seriesName) && d?.instance_id) {
    const members = d.member_ids ?? [d.instance_id]
    const day = d.value?.[1]
    view.focusMark(members, { day: typeof day === 'number' && p.seriesName !== 'price-points' ? day : undefined,
                              family: d.family_key })
    return true
  }
  return false
}

