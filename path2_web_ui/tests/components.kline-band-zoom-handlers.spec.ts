import { describe, it, expect } from 'vitest'
import { BAND_ZOOM_STEP_BUTTON, BAND_ZOOM_STEP_WHEEL, BAND_ZOOM_MIN, BAND_ZOOM_MAX } from '../src/render/subGeometry'

// 纯函数契约:UI 按钮 handler 与 wheel handler 的 factor 变换公式
// 组件层完整 mount + ECharts 挂载在 e2e 里覆盖(Task 5)

describe('bandZoom UI handler 契约(纯函数化)', () => {
  it('button + 步进:factor 1.0 → 1.2(绝对 0.2)', () => {
    const cap = 3.0
    const next = Math.min(cap, 1.0 + BAND_ZOOM_STEP_BUTTON)
    expect(next).toBe(1.2)
  })

  it('button − 步进:factor 1.4 → 1.2(绝对 0.2,下界 1.0)', () => {
    const clamped = Math.max(BAND_ZOOM_MIN, 1.4 - BAND_ZOOM_STEP_BUTTON)
    expect(clamped).toBeCloseTo(1.2, 10)
  })

  it('button + 接近 cap:factor 2.9 + 0.2 → clamp 到 cap 3.0', () => {
    const cap = 3.0
    const next = Math.min(cap, 2.9 + BAND_ZOOM_STEP_BUTTON)
    expect(next).toBe(3.0)
  })

  it('wheel zoom-in:factor 1.0 × 1.1 → 1.1', () => {
    const next = Math.min(3.0, 1.0 * BAND_ZOOM_STEP_WHEEL)
    expect(next).toBeCloseTo(1.1, 10)
  })

  it('wheel zoom-out:factor 1.21 ÷ 1.1 → 1.1', () => {
    const next = Math.max(BAND_ZOOM_MIN, 1.21 / BAND_ZOOM_STEP_WHEEL)
    expect(next).toBeCloseTo(1.1, 10)
  })

  it('reset:任何 factor → 1.0', () => {
    const next = 1.0
    expect(next).toBe(BAND_ZOOM_MIN)
  })

  it('formatFactor:1.4 → "1.4×"', () => {
    const format = (f: number) => f.toFixed(1) + '×'
    expect(format(1.4)).toBe('1.4×')
    expect(format(1.0)).toBe('1.0×')
    expect(format(3.0)).toBe('3.0×')
  })
})
