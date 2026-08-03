import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import ScanConfigDialog from '../../src/components/ScanConfigDialog.vue'
import { usePatternsStore } from '../../src/stores/patterns'
import { useConfigStore } from '../../src/stores/config'
import { useScanStore } from '../../src/stores/scan'
import { useViewStore } from '../../src/stores/view'
import { startScan } from '../../src/api'

vi.mock('../../src/api', () => ({ saveWcMirror: async () => ({ ok: true } as any), clearWcMirror: async () => ({ ok: true } as any),
  getPatterns: vi.fn(() => Promise.resolve([
    { pattern_id: 'bo_only', topology: { nodes: [], edges: [] }, event_styles: {} },
    { pattern_id: 'bbb',     topology: { nodes: [], edges: [] }, event_styles: {} },
    { pattern_id: 'three',   topology: { nodes: [], edges: [] }, event_styles: {} },
  ])),
  getConfig: vi.fn(() => Promise.resolve({
    dataset_dir: '/d',
    scan: { start_date: '2025-01-01', end_date: '2025-12-31',
            workers: 8, ticker_regex: null, label_horizon: 20 },
    last_selected_pattern: '',
  })),
  putConfig: vi.fn(() => Promise.resolve()),
  startScan: vi.fn(() => Promise.resolve('scan_id_x')),
  streamScan: vi.fn(() => ({ close: () => {} } as any)),
  cancelScan: vi.fn(() => Promise.resolve({ ok: true })),
  listParamFiles: vi.fn((pid: string) =>
    Promise.resolve(pid === 'bo_only'
      ? ['params.yaml', 'exp_wide.yaml']
      : ['params.yaml'])),
}))

describe('ScanConfigDialog', () => {
  beforeEach(() => { setActivePinia(createPinia()); localStorage.clear() })
  // vi.stubGlobal('alert', ...) 在下面的 startScan 失败例里用;vite.config.ts 的 test: 块未设
  // unstubGlobals,不手动清会泄漏到本文件后续追加的测试(Task 4/8 都要往这个 spec 加例)
  afterEach(() => { vi.unstubAllGlobals() })

  it('[开始扫描] enabled after selecting one pattern', async () => {
    const w = mount(ScanConfigDialog)
    await flushPromises()
    const ps = usePatternsStore()
    ps.toggleSelected('bo_only')
    await w.vm.$nextTick()
    const btn = w.findAll('button').find(b => b.text() === '开始扫描')!
    expect(btn.attributes('disabled')).toBeUndefined()
  })

  it('click row (no modifier) replaces selection', async () => {
    const w = mount(ScanConfigDialog)
    await flushPromises()
    const rows = w.findAll('li[data-pid]')
    await rows[0].trigger('click')
    await rows[1].trigger('click')                    // 单选替换
    const ps = usePatternsStore()
    expect([...ps.selectedIds]).toEqual(['bbb'])
  })

  it('ctrl+click toggles current only', async () => {
    const w = mount(ScanConfigDialog)
    await flushPromises()
    const rows = w.findAll('li[data-pid]')
    await rows[0].trigger('click')                    // {bo_only}
    await rows[2].trigger('click', { ctrlKey: true }) // {bo_only, three}
    const ps = usePatternsStore()
    expect([...ps.selectedIds].sort()).toEqual(['bo_only', 'three'])
  })

  it('shift+click selects range from anchor to current', async () => {
    const w = mount(ScanConfigDialog)
    await flushPromises()
    const rows = w.findAll('li[data-pid]')
    await rows[0].trigger('click')                    // anchor = 0, {bo_only}
    await rows[2].trigger('click', { shiftKey: true })// 0..2 全选
    const ps = usePatternsStore()
    expect([...ps.selectedIds].sort()).toEqual(['bbb', 'bo_only', 'three'])
  })

  it('[全选] / [清空] / [反选] buttons work', async () => {
    const w = mount(ScanConfigDialog)
    await flushPromises()
    const ps = usePatternsStore()
    const btns = w.findAll('.patterns-block button')
    const btnAll = btns.find(b => b.text() === '全选')!
    const btnNone = btns.find(b => b.text() === '清空')!
    const btnInv = btns.find(b => b.text() === '反选')!
    await btnAll.trigger('click')
    expect(ps.selectedIds.size).toBe(3)
    await btnNone.trigger('click')
    expect(ps.selectedIds.size).toBe(0)
    ps.toggleSelected('bo_only')
    await btnInv.trigger('click')
    expect([...ps.selectedIds].sort()).toEqual(['bbb', 'three'])
  })

  it('[开始扫描] saves 5 fields + runs scan + emits close', async () => {
    const w = mount(ScanConfigDialog)
    await flushPromises()
    const ps = usePatternsStore(); ps.toggleSelected('bo_only')
    const cfg = useConfigStore()
    const scan = useScanStore()
    const spySave = vi.spyOn(cfg, 'save')
    const spyRun = vi.spyOn(scan, 'run')
    await w.vm.$nextTick()
    const btn = w.findAll('button').find(b => b.text() === '开始扫描')!
    btn.trigger('click')
    await flushPromises()
    expect(spySave).toHaveBeenCalled()
    const savedArg = spySave.mock.calls[0][0]
    expect(savedArg.scan).toMatchObject({
      start_date: '2025-01-01', end_date: '2025-12-31',
      workers: 8, label_horizon: 20, ticker_regex: null,
    })
    expect(spyRun).toHaveBeenCalled()
    expect(w.emitted('close')).toBeTruthy()
  })

  it('[取消] emits close without save', async () => {
    const w = mount(ScanConfigDialog)
    await flushPromises()
    const cfg = useConfigStore()
    const spySave = vi.spyOn(cfg, 'save')
    const btn = w.findAll('button').find(b => b.text() === '取消')!
    await btn.trigger('click')
    expect(spySave).not.toHaveBeenCalled()
    expect(w.emitted('close')).toBeTruthy()
  })

  it('ticker regex empty string -> saved as null', async () => {
    const w = mount(ScanConfigDialog)
    await flushPromises()
    const ps = usePatternsStore(); ps.toggleSelected('bo_only')
    const cfg = useConfigStore()
    const spySave = vi.spyOn(cfg, 'save')
    const tr = w.find('input[data-field="ticker_regex"]')
    await tr.setValue('  ')                            // 空白 -> null
    const btn = w.findAll('button').find(b => b.text() === '开始扫描')!
    await btn.trigger('click')
    expect(spySave.mock.calls[0][0].scan.ticker_regex).toBe(null)
  })

  it('startScan 失败 → running 复位 + 不关对话框 + alert 带后端 detail', async () => {
    // 回归守卫:曾经 startScan 抛错无人接,running 永真 → 按钮永久 disabled、只能刷页面
    const alertSpy = vi.fn()
    vi.stubGlobal('alert', alertSpy)
    vi.mocked(startScan).mockRejectedValueOnce(
      new Error('params_files[bo_only]: 参数文件不存在: ghost.yaml'))
    const w = mount(ScanConfigDialog)
    await flushPromises()
    const ps = usePatternsStore()
    ps.selectedIds = new Set(['bo_only'])
    await w.vm.$nextTick()
    const btn = w.findAll('button').find(b => b.text() === '开始扫描')!
    btn.trigger('click')
    await flushPromises()
    const scan = useScanStore()
    expect(scan.running).toBe(false)
    expect(w.emitted('close')).toBeFalsy()
    expect(alertSpy.mock.calls[0][0]).toContain('ghost.yaml')
  })

  it('默认参数源 = params.yaml → 两个通道都不传(后端走兜底)', async () => {
    const w = mount(ScanConfigDialog)
    await flushPromises()
    const ps = usePatternsStore(); ps.selectedIds = new Set(['bo_only'])
    const scan = useScanStore()
    const spyRun = vi.spyOn(scan, 'run').mockResolvedValue(undefined as any)
    await w.vm.$nextTick()
    w.findAll('button').find(b => b.text() === '开始扫描')!.trigger('click')
    await flushPromises()
    const req = spyRun.mock.calls[0][0] as any
    expect(req.params_files).toBeUndefined()
    expect(req.params_overrides).toBeUndefined()
  })

  it('选非默认文件 → 进 params_files,不进 params_overrides', async () => {
    const w = mount(ScanConfigDialog)
    await flushPromises()
    const ps = usePatternsStore(); ps.selectedIds = new Set(['bo_only'])
    const sel = w.find('select[data-testid="param-source"][data-pid="bo_only"]')
    await sel.setValue('exp_wide.yaml')
    const scan = useScanStore()
    const spyRun = vi.spyOn(scan, 'run').mockResolvedValue(undefined as any)
    w.findAll('button').find(b => b.text() === '开始扫描')!.trigger('click')
    await flushPromises()
    const req = spyRun.mock.calls[0][0] as any
    expect(req.params_files).toEqual({ bo_only: 'exp_wide.yaml' })
    expect(req.params_overrides).toBeUndefined()
  })

  it('★红线:文件源的 pid 不进 wcPids(否则扫完静默删用户的 Working Copy)', async () => {
    // 有 WC 但参数源选了文件 → 该 pid 既不进 overrides、也不进 markWcLaunch
    const view = useViewStore()
    view.loadScanFile({
      pattern_ids: ['bo_only'],
      per_pattern: { bo_only: {
        pattern_spec: { pattern_id: 'bo_only', topology: { nodes: [], edges: [] }, event_styles: {} },
        end_node: 'bo', params_snapshot: { bo: { total_window: 10 } } } },
      scan: { scan_ts: '20260726T000000', start_date: '2025-01-01',
              end_date: '2025-06-01', label_horizon: 20 },
      results: [],
    } as any)
    view.forkWorkingCopy('bo_only')
    view.updateWorkingCopy('bo_only', { bo: { total_window: 42 } })
    expect(view.workingCopy['bo_only']).toBeTruthy()   // 前提:没有 WC 的话本例退化成与上一例重复、红线裸奔

    const w = mount(ScanConfigDialog)
    await flushPromises()
    const ps = usePatternsStore(); ps.selectedIds = new Set(['bo_only'])
    const sel = w.find('select[data-testid="param-source"][data-pid="bo_only"]')
    await sel.setValue('exp_wide.yaml')          // 有 WC,但显式改选文件
    const scan = useScanStore()
    const spyMark = vi.spyOn(scan, 'markWcLaunch')
    const spyRun = vi.spyOn(scan, 'run').mockResolvedValue(undefined as any)
    w.findAll('button').find(b => b.text() === '开始扫描')!.trigger('click')
    await flushPromises()
    expect(spyMark).toHaveBeenCalledWith([])     // 空数组,不含 bo_only
    expect(spyRun.mock.calls[0][0].params_overrides).toBeUndefined()   // 也不进 overrides,否则撞后端互斥 400
  })

  it('过滤字段填值 → 同时进配置与扫描请求', async () => {
    const w = mount(ScanConfigDialog)
    await flushPromises()
    const ps = usePatternsStore(); ps.selectedIds = new Set(['bo_only'])
    await w.find('input[data-field="price_min"]').setValue('0.5')
    await w.find('input[data-field="price_max"]').setValue('20')
    await w.find('input[data-field="volume_min"]').setValue('10000')
    const cfg = useConfigStore(); const scan = useScanStore()
    const spySave = vi.spyOn(cfg, 'save')
    const spyRun = vi.spyOn(scan, 'run').mockResolvedValue(undefined as any)
    w.findAll('button').find(b => b.text() === '开始扫描')!.trigger('click')
    await flushPromises()
    expect(spySave.mock.calls[0][0].scan).toMatchObject({
      price_min: 0.5, price_max: 20, volume_min: 10000,
    })
    expect(spyRun.mock.calls[0][0]).toMatchObject({
      price_min: 0.5, price_max: 20, volume_min: 10000,
    })
  })

  it('过滤字段留空 → null(不过滤)', async () => {
    const w = mount(ScanConfigDialog)
    await flushPromises()
    const ps = usePatternsStore(); ps.selectedIds = new Set(['bo_only'])
    const scan = useScanStore()
    const spyRun = vi.spyOn(scan, 'run').mockResolvedValue(undefined as any)
    w.findAll('button').find(b => b.text() === '开始扫描')!.trigger('click')
    await flushPromises()
    expect(spyRun.mock.calls[0][0]).toMatchObject({
      price_min: null, price_max: null, volume_min: null,
    })
  })

  it('过滤字段非法值(如带千分位)→ 按钮禁用,不静默降级为不过滤', async () => {
    // 回归守卫:numOrNull 曾把 "1,000,000" 这类误输入直接映射成 null(=不过滤),
    // 静默放宽筛选、事后无法从 scan.filters 分辨「误输入」与「故意不填」
    const w = mount(ScanConfigDialog)
    await flushPromises()
    const ps = usePatternsStore(); ps.selectedIds = new Set(['bo_only'])
    const scan = useScanStore()
    const spyRun = vi.spyOn(scan, 'run').mockResolvedValue(undefined as any)
    await w.find('input[data-field="volume_min"]').setValue('1,000,000')
    await w.vm.$nextTick()
    const btn = w.findAll('button').find(b => b.text() === '开始扫描')!
    expect(btn.attributes('disabled')).toBeDefined()
    await btn.trigger('click')
    await flushPromises()
    expect(spyRun).not.toHaveBeenCalled()
  })

  it('过滤字段合法值 0 不被判非法(0 是有意义的下限,不是"未填")', async () => {
    const w = mount(ScanConfigDialog)
    await flushPromises()
    const ps = usePatternsStore(); ps.selectedIds = new Set(['bo_only'])
    const scan = useScanStore()
    const spyRun = vi.spyOn(scan, 'run').mockResolvedValue(undefined as any)
    await w.find('input[data-field="volume_min"]').setValue('0')
    await w.vm.$nextTick()
    const btn = w.findAll('button').find(b => b.text() === '开始扫描')!
    expect(btn.attributes('disabled')).toBeUndefined()
    await btn.trigger('click')
    await flushPromises()
    expect(spyRun.mock.calls[0][0]).toMatchObject({ volume_min: 0 })
  })
})
