// 图窗 → dataZoom 起止百分比
import { describe, it, expect } from 'vitest'
import { zoomForWindow } from '../src/annotate/viewWindow'

const DATES = ['2025-01-02', '2025-01-03', '2025-01-06', '2025-01-07', '2025-01-08']

describe('zoomForWindow', () => {
  it('两端正好是 K 线日期', () => {
    expect(zoomForWindow(DATES, { start: '2025-01-03', end: '2025-01-07' })).toEqual({ start: 20, end: 80 })
  })
  it('两端落在没有 K 线的日子:取里面的那几根', () => {
    expect(zoomForWindow(DATES, { start: '2025-01-04', end: '2025-01-05' })).toBeNull()
    expect(zoomForWindow(DATES, { start: '2025-01-04', end: '2025-01-09' })).toEqual({ start: 40, end: 100 })
    expect(zoomForWindow(DATES, { start: '2024-12-01', end: '2025-01-02' })).toEqual({ start: 0, end: 20 })
  })
  it('整段在图外或没有 K 线 → null', () => {
    expect(zoomForWindow(DATES, { start: '2026-01-01', end: '2026-02-01' })).toBeNull()
    expect(zoomForWindow([], { start: '2025-01-01', end: '2025-02-01' })).toBeNull()
  })
})
