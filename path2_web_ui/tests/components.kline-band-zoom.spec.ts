import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { computeSubGeometry } from '../src/render/subGeometry'

describe('bandZoomFactor 状态语义(隔离于 Vue mount,纯函数式契约)', () => {
  const LS_KEY = 'kline-band-zoom-v1'

  beforeEach(() => { localStorage.clear() })
  afterEach(() => { localStorage.clear() })

  it('subCanvasH 按 factor 涨:computeSubGeometry({...}, 2.0).subCanvasH > .subCanvasH(1.0)', () => {
    // laneCounts 取 [5,5]:让各 band 自然高远离 BAND_MIN_H(20) clamp,真实断言 factor 增长
    // (SUB_CANVAS_MIN_H 已收窄为空数据专用兜底,不再影响非空输入)
    const input = { bracketLaneCount: 1, bandLaneCounts: [5, 5] }
    const g1 = computeSubGeometry(input, 1.0)
    const g2 = computeSubGeometry(input, 2.0)
    expect(g2.subCanvasH).toBeGreaterThan(g1.subCanvasH)
  })
})
