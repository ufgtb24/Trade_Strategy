import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useScanStore } from '../src/stores/scan'
import * as api from '../src/api'

describe('scan store · rename + open(name)', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it('rename 调 renameScan 并刷新 history', async () => {
    const renameSpy = vi.spyOn(api, 'renameScan').mockResolvedValue({ name: '新名字' })
    const listSpy = vi.spyOn(api, 'listScans').mockResolvedValue([
      { name: '新名字', scan_ts: '20260729T100000', pattern_ids: ['bo_only'],
        hits: 1, total: 10, size: 100, partial: false, per_pattern: {} },
    ])
    const s = useScanStore()
    await s.rename('old', '新名字')
    expect(renameSpy).toHaveBeenCalledWith('old', '新名字')
    expect(listSpy).toHaveBeenCalled()
    expect(s.history[0].name).toBe('新名字')
  })

  it('open(name) 调 loadScan(name)', async () => {
    const loadSpy = vi.spyOn(api, 'loadScan').mockResolvedValue({
      pattern_ids: [], per_pattern: {}, scan: {
        scan_ts: '20260729T100000', name: 'myexp', start_date: '', end_date: '',
        workers: 1, scanned: 0, hits: 0, errors: 0, dataset_dir: '',
        win_start: '', win_end: '', label_horizon: 20,
      } as any, results: [],
    } as any)
    const s = useScanStore()
    await s.open('myexp')
    expect(loadSpy).toHaveBeenCalledWith('myexp')
  })
})
