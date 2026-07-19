/** brush 双 event 模式 handler factory · 拆分 payload 与 trigger 两个信号:
 *
 * - brushselected event:ECharts 一次 brush 交互(mousedown → drag → mouseup)会触发多次
 *   (drag 过程每帧都触发) · 本 handler 只更新缓存 latestRange · **不 emit request**
 * - brushEnd event:brush interaction 完成时 ECharts 自动触发一次(mouseup 后) · 本 handler
 *   读缓存 → emit(startIdx, endIdx) → 清缓存
 *
 * 为何双 event(不能只用 brushEnd):ECharts docs 中 brushEnd event payload 未明确文档化
 * ("No explicit payload structure provided"),不能可靠取 coordRange;而 brushselected
 * event 有明确 batch[0].areas[0].coordRange 契约。分离 what(brushselected 提供 payload)
 * 与 when(brushEnd 提供触发信号)。
 *
 * 依据设计:docs/superpowers/specs/2026-07-18-brush-double-request-fix-design.md
 * 前置 SDD:docs/superpowers/plans/2026-07-18-path2-web-double-pause-fix.md(后端已修单
 * request 内 detector 双跑;本 factory 消除前端 brush 一次交互连发多个 request 的根因)。 */

export type BrushRequestEmit = (startIdx: number, endIdx: number) => void

export interface BrushRequestHandler {
  onBrushSelected: (p: any) => void
  onBrushEnd: () => void
}

export function createBrushRequestHandler(
  emit: BrushRequestEmit,
  getBarsLen: () => number,
): BrushRequestHandler {
  let latestRange: [number, number] | null = null

  return {
    onBrushSelected(p: any) {
      // ECharts brushselected event payload 契约:batch[0].areas[0].coordRange。
      // coordRange 缺失(如 brush 组件被清空)→ 缓存 null · brushEnd 不 emit。
      const area = p?.batch?.[0]?.areas?.[0]
      const coordRange = area?.coordRange as [number, number] | undefined
      latestRange = coordRange ?? null
    },
    onBrushEnd() {
      if (latestRange === null) return
      const [a, b] = latestRange
      const startIdx = Math.max(0, Math.round(Math.min(a, b)))
      const endIdx = Math.min(getBarsLen() - 1, Math.round(Math.max(a, b)))
      // 消费后清缓存 · 防下次 brush 前 brushEnd 空跑读到旧值。
      latestRange = null
      if (endIdx < startIdx) return
      emit(startIdx, endIdx)
    },
  }
}
