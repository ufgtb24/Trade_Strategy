/** 契约:双事件模式(brushselected 缓存 payload · brushEnd 触发 emit)
 *
 * 现状 KlineChart.vue L556 chartMain.on('brushselected', ...) 收到 payload 就直接调
 * view.triggerTimeQuery → ECharts brushselected 一次 brush 交互触发多次(拖动 + 结束都发)
 * → 后端 handler 被调多次 → gate debug_break 触发多次(pause 多次)。
 *
 * 修法:factory createBrushRequestHandler(emit, getBarsLen) 返回 { onBrushSelected, onBrushEnd }
 * closure。onBrushSelected 只更新缓存(不 emit),onBrushEnd 读缓存 emit 一次并清缓存。
 * 依据 spec: docs/superpowers/specs/2026-07-18-brush-double-request-fix-design.md §Architecture
 *
 * 测试策略:与 klineBrushKey.spec.ts 同 pattern —— 不 mount 组件(jsdom + ECharts 崩),
 * 直接 import pure factory 做纯函数 test。 */
import { describe, it, expect, vi } from 'vitest'
import { createBrushRequestHandler } from '../src/components/klineBrushHandler'

/** 构造 brushselected event payload:mirror ECharts docs 中 batch[0].areas[0].coordRange 契约。 */
const mkPayload = (a: number, b: number) => ({
  batch: [{ areas: [{ coordRange: [a, b] as [number, number] }] }],
})

describe('KlineChart · brush 双事件模式 · 一次交互 emit 恰 1 次', () => {
  it('3 次 brushselected + 1 次 brushEnd → emit 调 1 次(实参取最后一次 coordRange)', () => {
    const emit = vi.fn()
    const h = createBrushRequestHandler(emit, () => 300)
    h.onBrushSelected(mkPayload(50, 60))
    h.onBrushSelected(mkPayload(50, 70))
    h.onBrushSelected(mkPayload(50, 80))
    h.onBrushEnd()
    expect(emit).toHaveBeenCalledTimes(1)
    expect(emit).toHaveBeenCalledWith(50, 80)
  })

  it('brushEnd 无 preceding brushselected → emit 不调(缓存 null)', () => {
    const emit = vi.fn()
    const h = createBrushRequestHandler(emit, () => 300)
    h.onBrushEnd()
    expect(emit).not.toHaveBeenCalled()
  })

  it('两次完整 brush 交互 → emit 各调 1 次 · 无跨交互污染', () => {
    const emit = vi.fn()
    const h = createBrushRequestHandler(emit, () => 300)
    // 第一次 brush
    h.onBrushSelected(mkPayload(50, 60))
    h.onBrushEnd()
    // 第二次 brush(无残留缓存)
    h.onBrushSelected(mkPayload(100, 110))
    h.onBrushEnd()
    expect(emit).toHaveBeenCalledTimes(2)
    expect(emit).toHaveBeenNthCalledWith(1, 50, 60)
    expect(emit).toHaveBeenNthCalledWith(2, 100, 110)
  })

  it('startIdx clamp 到 0 · endIdx clamp 到 getBarsLen()-1(超出边界保护)', () => {
    const emit = vi.fn()
    const h = createBrushRequestHandler(emit, () => 100)
    h.onBrushSelected(mkPayload(-10, 200))
    h.onBrushEnd()
    expect(emit).toHaveBeenCalledTimes(1)
    expect(emit).toHaveBeenCalledWith(0, 99)
  })
})
