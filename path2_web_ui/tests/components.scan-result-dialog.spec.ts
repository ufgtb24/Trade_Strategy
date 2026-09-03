import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ScanResultDialog from '../src/components/ScanResultDialog.vue'
import * as api from '../src/api'
import type { ScanHistoryEntry } from '../src/types'

const ROWS: ScanHistoryEntry[] = [
  { name: 'tb深度28-38', scan_ts: '20260729T100000', pattern_ids: ['bottom_burst'],
    hits: 3, total: 100, size: 2048, partial: false,
    per_pattern: { bottom_burst: { hits: 12, median: 0.13,
                                   fp: { ratio: 0.526, random_ratio: 0.498 },
                                   params_consistent: false } } },
  { name: '20260728T090000', scan_ts: '20260728T090000', pattern_ids: ['bo_only'],
    hits: 1, total: 100, size: 1024, partial: false,
    per_pattern: { bo_only: { hits: 25, median: null, fp: null,
                              params_consistent: true } } },
  { name: '双pattern', scan_ts: '20260727T090000', pattern_ids: ['bo_only', 'bottom_burst'],
    hits: 1, total: 100, size: 2048, partial: false,
    per_pattern: { bo_only: { hits: 5, median: 0.08,
                              fp: { ratio: 0.6, random_ratio: 0.498 },
                              params_consistent: true },
                   bottom_burst: { hits: 3, median: -0.02, fp: null,
                                   params_consistent: null } } },
]

describe('ScanResultDialog · 显示 name + rename', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it('列表显示 name 而非纯时间戳', async () => {
    vi.spyOn(api, 'listScans').mockResolvedValue(ROWS)
    const w = mount(ScanResultDialog, { attachTo: document.body })
    await flushPromises()
    expect(w.text()).toContain('tb深度28-38')
    w.unmount()
  })

  it('选中一行点 Rename → 输入新名 → 调 scan.rename 并刷新', async () => {
    vi.spyOn(api, 'listScans').mockResolvedValue(ROWS)
    const renameSpy = vi.spyOn(api, 'renameScan').mockResolvedValue({ name: '新名' })
    const w = mount(ScanResultDialog, { attachTo: document.body })
    await flushPromises()
    const rows = w.findAll('tbody tr')
    await rows[0].trigger('click')
    const renameBtn = w.find('button[data-testid="rename"]')
    await renameBtn.trigger('click')
    const input = w.find('input[data-testid="rename-input"]')
    await input.setValue('新名')
    await w.find('button[data-testid="rename-confirm"]').trigger('click')
    await flushPromises()
    expect(renameSpy).toHaveBeenCalledWith('tb深度28-38', '新名')
    w.unmount()
  })

  it('Hits 列显示每 pattern 的 match 数 chip,Median 列同序显示中位数', async () => {
    vi.spyOn(api, 'listScans').mockResolvedValue(ROWS)
    const w = mount(ScanResultDialog, { attachTo: document.body })
    await flushPromises()
    const row0 = w.findAll('tbody tr')[0]
    expect(row0.findAll('.hits-chip').map(c => c.text())).toEqual(['bottom_burst'])
    expect(row0.findAll('.hits-num').map(c => c.text())).toEqual(['12'])
    expect(row0.text()).toContain('+13.0%')
    const row1 = w.findAll('tbody tr')[1]
    expect(row1.findAll('.hits-chip').map(c => c.text())).toEqual(['bo_only'])
    expect(row1.findAll('.hits-num').map(c => c.text())).toEqual(['25'])
    expect(row1.text()).toContain('—')          // median null → —
    const row2 = w.findAll('tbody tr')[2]
    expect(row2.findAll('.hits-chip').map(c => c.text())).toEqual(['bo_only', 'bottom_burst'])
    expect(row2.findAll('.hits-num').map(c => c.text())).toEqual(['5', '3'])
    expect(row2.findAll('.median-val').map(c => c.text())).toEqual(['+8.0%', '-2.0%'])
    w.unmount()
  })

  it('FP 列同序显示 方向/随机 对比,缺失显示 —', async () => {
    vi.spyOn(api, 'listScans').mockResolvedValue(ROWS)
    const w = mount(ScanResultDialog, { attachTo: document.body })
    await flushPromises()
    expect(w.find('thead').text()).toContain('FP')
    const rows = w.findAll('tbody tr')
    expect(rows[0].findAll('.fp-val').map(c => c.text())).toEqual(['52.6% / 49.8%'])
    expect(rows[1].findAll('.fp-val').map(c => c.text())).toEqual(['—'])
    expect(rows[2].findAll('.fp-val').map(c => c.text())).toEqual(['60.0% / 49.8%', '—'])
    w.unmount()
  })

  it('参数结构不一致的 pattern chip 红底,一致/无法判断保持灰色', async () => {
    vi.spyOn(api, 'listScans').mockResolvedValue(ROWS)
    const w = mount(ScanResultDialog, { attachTo: document.body })
    await flushPromises()
    const rows = w.findAll('tbody tr')
    // row0:bottom_burst 不一致 → 该 chip 红底 + title
    const stale = rows[0].find('.chip--stale')
    expect(stale.exists()).toBe(true)
    expect(stale.text()).toBe('bottom_burst')
    expect(stale.attributes('title')).toContain('参数结构不一致')
    // row1:一致 → 无红 chip
    expect(rows[1].findAll('.chip--stale').length).toBe(0)
    // row2:bo_only 一致 + bottom_burst 无法判断 → 均无红 chip
    expect(rows[2].findAll('.chip--stale').length).toBe(0)
    w.unmount()
  })
})
