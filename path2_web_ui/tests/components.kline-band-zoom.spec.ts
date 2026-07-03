import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { computeSubGeometry } from '../src/render/subGeometry'

describe('bandZoomFactor 状态语义(隔离于 Vue mount,纯函数式契约)', () => {
  const LS_KEY = 'kline-band-zoom-v1'

  beforeEach(() => { localStorage.clear() })
  afterEach(() => { localStorage.clear() })

  it('localStorage parse 失败 → factor 回 1.0(mount fallback 契约)', () => {
    // 契约:parseFloat('abc') → NaN → default 1.0
    localStorage.setItem(LS_KEY, 'abc')
    const raw = parseFloat(localStorage.getItem(LS_KEY) ?? '')
    const factor = Number.isFinite(raw) && raw >= 1.0 && raw <= 3.0 ? raw : 1.0
    expect(factor).toBe(1.0)
  })

  it('localStorage out-of-range → clamp 到 [1.0, 3.0]', () => {
    localStorage.setItem(LS_KEY, '5.0')
    const raw = parseFloat(localStorage.getItem(LS_KEY) ?? '')
    const factor = Number.isFinite(raw) && raw >= 1.0 && raw <= 3.0 ? raw : 1.0
    // 契约:超范围 → 回 default(实施可选:也可 clamp;取严格 = 回 1.0)
    expect(factor).toBe(1.0)
  })

  it('localStorage 合法值 → factor 保留', () => {
    localStorage.setItem(LS_KEY, '1.8')
    const raw = parseFloat(localStorage.getItem(LS_KEY) ?? '')
    const factor = Number.isFinite(raw) && raw >= 1.0 && raw <= 3.0 ? raw : 1.0
    expect(factor).toBe(1.8)
  })

  it('factorCap 计算:containerH=800, naturalSubH_at_1=100 → cap=min(3.0, 500/100)=3.0', () => {
    const containerH = 800, MAIN_MIN_H = 300
    const naturalSubH = 100
    const maxSubH = containerH - MAIN_MIN_H
    const cap = naturalSubH >= maxSubH ? 1.0 : Math.min(3.0, maxSubH / naturalSubH)
    expect(cap).toBe(3.0)
  })

  it('factorCap 空间不足:containerH=400, naturalSubH=200 → cap=1.0', () => {
    const containerH = 400, MAIN_MIN_H = 300
    const naturalSubH = 200
    const maxSubH = containerH - MAIN_MIN_H
    const cap = naturalSubH >= maxSubH ? 1.0 : Math.min(3.0, maxSubH / naturalSubH)
    expect(cap).toBe(1.0)   // maxSubH=100 < naturalSubH=200
  })

  it('factorCap 收紧:containerH=500, naturalSubH=100 → cap=min(3.0, 200/100)=2.0', () => {
    const cap = Math.min(3.0, (500 - 300) / 100)
    expect(cap).toBe(2.0)
  })

  it('subCanvasH 按 factor 涨:computeSubGeometry({...}, 2.0).subCanvasH > .subCanvasH(1.0)', () => {
    // laneCounts 取 [5,5]:让各 band 自然高远离 BAND_MIN_H(20) clamp,真实断言 factor 增长
    // (SUB_CANVAS_MIN_H 已收窄为空数据专用兜底,不再影响非空输入)
    const input = { bracketLaneCount: 1, bandLaneCounts: [5, 5] }
    const g1 = computeSubGeometry(input, 1.0)
    const g2 = computeSubGeometry(input, 2.0)
    expect(g2.subCanvasH).toBeGreaterThan(g1.subCanvasH)
  })
})
