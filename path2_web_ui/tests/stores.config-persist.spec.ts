// last_selected_pattern 持久化:saveLastPattern 的 loaded guard + setActivePattern 委托
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useConfigStore } from '../src/stores/config'
import { useViewStore } from '../src/stores/view'
import { putConfig } from '../src/api'
import type { MultiScanResultFile } from '../src/types'

vi.mock('../src/api', () => ({
  getConfig: vi.fn(() => Promise.resolve({
    dataset_dir: '/d',
    scan: { start_date: '2024-01-01', end_date: '2024-06-30', workers: 1, ticker_regex: null },
    last_selected_pattern: 'bbb',
    backend_port: 8000,   // AppConfig 类型外的键:round-trip 必须保留
  })),
  putConfig: vi.fn(() => Promise.resolve()),
  getDiagnose: vi.fn(() => Promise.resolve({} as any)),
  getPreview: vi.fn(),
}))

function makeFile(): MultiScanResultFile {
  return {
    pattern_ids: ['bo_only', 'bbb'],
    per_pattern: {
      bo_only: { pattern_spec: { pattern_id: 'bo_only', topology: { nodes: [], edges: [] }, event_styles: {}, debug_enabled_classes: [] }, end_node: 'bo' },
      bbb:     { pattern_spec: { pattern_id: 'bbb',     topology: { nodes: [], edges: [] }, event_styles: {}, debug_enabled_classes: [] }, end_node: 'tb' },
    },
    scan: {
      scan_ts: '20260703T120000', start_date: '2024-01-01', end_date: '2024-06-30',
      workers: 1, scanned: 1, hits: 1, errors: 0, dataset_dir: '/d', params: 'default',
      win_start: '2023-09-01', win_end: '2024-07-15', label_horizon: 20,
    },
    results: [],
  }
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.mocked(putConfig).mockClear()
})

describe('config store — saveLastPattern', () => {
  it('loaded=false: 只改内存,不 putConfig(防占位符覆盖 YAML)', () => {
    const cfg = useConfigStore()
    cfg.saveLastPattern('bbb')
    expect(cfg.config?.last_selected_pattern).toBe('bbb')
    expect(vi.mocked(putConfig)).not.toHaveBeenCalled()
  })

  it('loaded=true: putConfig 落盘,载荷含新 pid 且保留类型外键', async () => {
    const cfg = useConfigStore()
    await cfg.load()
    cfg.saveLastPattern('bo_only')
    expect(cfg.config?.last_selected_pattern).toBe('bo_only')
    expect(vi.mocked(putConfig)).toHaveBeenCalledOnce()
    const payload = vi.mocked(putConfig).mock.calls[0][0] as any
    expect(payload.last_selected_pattern).toBe('bo_only')
    expect(payload.backend_port).toBe(8000)
  })
})

describe('view store — setActivePattern 持久化委托', () => {
  it('切 active pattern 经 saveLastPattern 落盘', async () => {
    const cfg = useConfigStore()
    await cfg.load()
    const v = useViewStore()
    v.loadScanFile(makeFile())
    expect(v.activePatternId).toBe('bbb')   // load 后读到持久化值
    v.setActivePattern('bo_only')
    expect(cfg.config?.last_selected_pattern).toBe('bo_only')
    expect(vi.mocked(putConfig)).toHaveBeenCalledOnce()
  })
})
