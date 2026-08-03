import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ScanResultDialog from '../src/components/ScanResultDialog.vue'
import * as api from '../src/api'

const ROWS = [
  { name: 'tb深度28-38', scan_ts: '20260729T100000', pattern_ids: ['bottom_burst'],
    hits: 3, total: 100, size: 2048, partial: false },
  { name: '20260728T090000', scan_ts: '20260728T090000', pattern_ids: ['bo_only'],
    hits: 1, total: 100, size: 1024, partial: false },
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
})
