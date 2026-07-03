import { describe, it, expect } from 'vitest'
import { windowOf } from '../src/render/visible'
import type { ScanMeta } from '../src/types'

const baseScan: ScanMeta = {
  scan_ts: '20260627T120000',
  start_date: '2024-01-01', end_date: '2024-06-30',
  workers: 1, scanned: 100, hits: 5, errors: 0,
  dataset_dir: '/data', params: 'default',
  win_start: '2023-08-01', win_end: '2024-07-15',
  label_horizon: 20,
}

describe('windowOf', () => {
  it('returns win_start/win_end from buffered scan meta', () => {
    expect(windowOf(baseScan)).toEqual({ start: '2023-08-01', end: '2024-07-15' })
  })

  it('throws when win_start is missing(铁律下不应发生,防御)', () => {
    const bad = { ...baseScan, win_start: undefined as any }
    expect(() => windowOf(bad)).toThrow()
  })
})
