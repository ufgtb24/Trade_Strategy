import { describe, it, expect } from 'vitest'
import {
  computeRightAnchoredZoom,
  CTRL_ZOOM_IN_FACTOR,
  CTRL_ZOOM_OUT_FACTOR,
} from '../src/components/klineCtrlZoom'

// 纯函数契约:Ctrl+wheel 右锚定缩放公式(end 不动只动 start)
// 组件层 capture 拦截 + dispatchAction 链路在 e2e 里覆盖

describe('computeRightAnchoredZoom 契约', () => {
  it('放大:end 不变,start = end - (end-start)×0.85', () => {
    const r = computeRightAnchoredZoom(0, 100, -100, 1000)
    expect(r).not.toBeNull()
    expect(r!.end).toBe(100)
    expect(r!.start).toBeCloseTo(15, 10) // 100 - 100×0.85
  })

  it('缩小精确互逆:放大一档后再缩小一档,start 精确还原', () => {
    const zoomed = computeRightAnchoredZoom(0, 100, -100, 1000)!
    const back = computeRightAnchoredZoom(zoomed.start, zoomed.end, +100, 1000)!
    expect(back.end).toBe(100)
    expect(back.start).toBeCloseTo(0, 10) // 85÷0.85 = 100
    expect(CTRL_ZOOM_IN_FACTOR * CTRL_ZOOM_OUT_FACTOR).toBeCloseTo(1, 12)
  })

  it('start≥0 clamp:缩小超出满幅 → start=0,end 不动', () => {
    const r = computeRightAnchoredZoom(10, 100, +100, 1000)
    // 90÷0.85≈105.9 > 100 → clamp
    expect(r).toEqual({ start: 0, end: 100 })
  })

  it('满幅再缩小 = no-op(null)', () => {
    expect(computeRightAnchoredZoom(0, 100, +100, 1000)).toBeNull()
  })

  it('最小 span:N=100 时 minSpan=3%,放大在 3% 处止步', () => {
    // (96,100) span=4%,×0.85=3.4% ≥ 3% → 正常缩
    const r1 = computeRightAnchoredZoom(96, 100, -100, 100)
    expect(r1).toEqual({ start: 96.6, end: 100 })
    // (96.6,100) span=3.4%,×0.85=2.89% < 3% → clamp 到 3%
    const r2 = computeRightAnchoredZoom(r1!.start, 100, -100, 100)
    expect(r2!.start).toBeCloseTo(97, 10)
    expect(r2!.end).toBe(100)
  })

  it('已到最小 span 再放大 = no-op(null)', () => {
    expect(computeRightAnchoredZoom(97, 100, -100, 100)).toBeNull()
  })

  it('N<3:minSpan clamp 到 100,放大只会推到满幅', () => {
    // N=2 时 minSpan=100%,任何放大 span 都被顶到 100 → start=0
    const r = computeRightAnchoredZoom(20, 100, -100, 2)
    expect(r).toEqual({ start: 0, end: 100 })
    // 已在满幅则 no-op
    expect(computeRightAnchoredZoom(0, 100, -100, 2)).toBeNull()
  })

  it('边界防御:N=0 / deltaY=0 / end≤start → null', () => {
    expect(computeRightAnchoredZoom(0, 100, -100, 0)).toBeNull()
    expect(computeRightAnchoredZoom(0, 100, 0, 1000)).toBeNull()
    expect(computeRightAnchoredZoom(50, 50, -100, 1000)).toBeNull()
    expect(computeRightAnchoredZoom(60, 50, -100, 1000)).toBeNull()
  })

  it('end 恒不变:非满幅窗口放大/缩小,end 均保持入参值', () => {
    const cases: Array<[number, number, number]> = [
      [30, 80, -100],
      [30, 80, +100],
      [0, 55.5, -1],
      [12.3, 99.9, +1],
    ]
    for (const [s, e, dy] of cases) {
      const r = computeRightAnchoredZoom(s, e, dy, 500)
      expect(r).not.toBeNull()
      expect(r!.end).toBe(e)
    }
  })
})
