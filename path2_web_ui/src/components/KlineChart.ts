/**
 * KlineChart.ts — 纯点击分流逻辑（无 Vue 依赖）
 *
 * 职责：接收 ECharts click 事件 payload，根据 seriesName 和 matches 分流，
 * 调用 view store 的 actions 驱动四件状态（selectedMatch / highlightedEvents /
 * candidateMatches / pendingDisambig）。
 *
 * 不变量：
 * - MatchDict.children 是扁平且去重的 event_id 列表；同一 event_id 不会在同一
 *   match.children 中出现多次。multi-match（ms.length > 1）来源仅是同一 event_id
 *   被多个不同 match.children 共享——不会因 Kleene 复用产生假阳。
 * - candidate 与 selected 互斥：进 candidate 分支前必须先清 selected + highlight。
 * - bracket click 和 marker ms≤1 两个分支必须先 clearCandidates 防残留。
 */

import type { MatchDict } from '../types'
import type { useViewStore } from '../stores/view'

export type ChartClickPayload = {
  seriesName?: string
  data?: { event_id?: string; match_id?: string }
} | null

/**
 * 处理 ECharts chart.on('click', p) 事件，分流到四个 view store 动作分支。
 *
 * @param p       ECharts click payload（空白点击时为 null 或 seriesName 缺失）
 * @param matches 当前 effectiveAnalysis.matches
 * @param view    useViewStore() 实例
 */
export function handleChartClick(
  p: ChartClickPayload,
  matches: MatchDict[],
  view: ReturnType<typeof useViewStore>,
): void {
  // ── 空白 click → 清四样 ─────────────────────────────────────────────
  if (!p || !p.seriesName) {
    view.clearCandidates()
    view.clearHighlight()
    view.selectMatch(null)
    view.selectEvent(null)
    return
  }

  // ── brackets 分支 ────────────────────────────────────────────────────
  // bracket click 收尾：无论 match_id 是否在候选集中，一律收尾并清候选（防残留）
  if (p.seriesName === 'brackets' && p.data?.match_id) {
    const matchId = p.data.match_id
    const match = matches.find((m) => m.event_id === matchId)
    if (!match) return
    view.setHighlightedEvents(match.children)
    view.selectMatch(matchId)
    view.clearCandidates()
    return
  }

  // ── marker 分支（points / intervals / price-points / satellites）─────
  const MARKER_SERIES = ['points', 'intervals', 'price-points', 'satellites']
  if (MARKER_SERIES.includes(p.seriesName) && p.data?.event_id) {
    const eventId = p.data.event_id
    // 计算 event 归属的 match 集合
    const ms = matches.filter((m) => m.children.includes(eventId))

    if (ms.length === 0) {
      // M fallback：不归属任何 match，直接选 event，清候选防残留
      view.clearCandidates()
      view.selectEvent(eventId)
      return
    }

    if (ms.length === 1) {
      // 唯一归属：高亮整组 + 选定 match + 选 event，清候选防残留
      view.clearCandidates()
      view.setHighlightedEvents(ms[0].children)
      view.selectMatch(ms[0].event_id)
      view.selectEvent(eventId)
      return
    }

    // ms.length > 1：多归属 → 进 candidate 流（互斥：先清 selected + highlight）
    view.selectMatch(null)
    view.clearHighlight()
    view.selectEvent(null)
    view.setCandidateMatches(ms.map((m) => m.event_id))
    view.setPendingDisambig(eventId)
    return
  }
}
