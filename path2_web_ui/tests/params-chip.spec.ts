// ParamsChip 两态(浏览灰/探索绿)+ chip 文本 A/B toggle + 内嵌抽屉 toggle 按钮 + mismatch dot
// spec: docs/research/params-editor-followup-decisions.md D1/D2/D3/P3
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import ParamsChip from '../src/components/ParamsChip.vue'
import { useViewStore } from '../src/stores/view'

const scanFileWith = (snapshot: any) => ({
  pattern_ids: ['bbb'],
  per_pattern: { bbb: { pattern_spec: { pattern_id: 'bbb', topology: { nodes: [], edges: [] }, event_styles: {} },
                        end_node: 'tb', ...(snapshot ? { params_snapshot: snapshot } : {}) } },
  // name = 文件标识符,后端恒写(未命名扫描 name = scan_ts,scan.py:376)
  scan: { scan_ts: '20260720T000000', name: '20260720T000000', start_date: '2025-01-01', end_date: '2025-06-01', label_horizon: 20 },
  results: [{ symbol: 'A', per_pattern: {} }],
})

describe('ParamsChip(两态)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(
      { ok: true, json: () => Promise.resolve({ has_snapshot: true, match: true, diffs: [] }) } as any)))
  })

  it('无 snapshot:chip 整体不渲染(D3,legacy 淘汰)', () => {
    useViewStore().loadScanFile(scanFileWith(null) as any)
    const w = mount(ParamsChip)
    expect(w.find('[data-testid="params-chip"]').exists()).toBe(false)
  })

  it('浏览态:灰 chip;「工作副本」checkbox 已删(D1)', async () => {
    useViewStore().loadScanFile(scanFileWith({ bo: { total_window: 10 } }) as any)
    const w = mount(ParamsChip)
    await new Promise(r => setTimeout(r))
    expect(w.get('[data-testid="params-chip"]').classes()).toContain('mode-browse')
    expect(w.text()).toContain('浏览')
    expect(w.find('.ab-toggle').exists()).toBe(false)
  })

  it('灰 + 无 WC:点 chip 文本无反应', async () => {
    const v = useViewStore()
    v.loadScanFile(scanFileWith({ bo: { total_window: 10 } }) as any)
    const w = mount(ParamsChip)
    await w.get('[data-testid="chip-label"]').trigger('click')
    expect(v.isExploring).toBe(false)
    expect(v.workingCopy['bbb']).toBeUndefined()
  })

  it('绿→点文本→灰(WC 保留);灰+有 WC→点文本→回绿(A/B 双向)', async () => {
    const v = useViewStore()
    v.loadScanFile(scanFileWith({ bo: { total_window: 10 } }) as any)
    v.forkWorkingCopy('bbb')
    v.updateWorkingCopy('bbb', { bo: { total_window: 42 } })
    const w = mount(ParamsChip)
    expect(w.get('[data-testid="params-chip"]').classes()).toContain('mode-explore')
    await w.get('[data-testid="chip-label"]').trigger('click')
    expect(v.isExploring).toBe(false)
    expect(v.workingCopy['bbb']!.currentDict).toEqual({ bo: { total_window: 42 } })  // 副本无损
    await w.get('[data-testid="chip-label"]').trigger('click')
    expect(v.isExploring).toBe(true)
  })

  it('内嵌按钮:两态都可点,emit toggle-drawer(P3 方案 a)', async () => {
    const v = useViewStore()
    v.loadScanFile(scanFileWith({ bo: { total_window: 10 } }) as any)
    const w = mount(ParamsChip)
    await w.get('[data-testid="drawer-btn"]').trigger('click')     // 灰态可点
    expect(w.emitted('toggle-drawer')).toHaveLength(1)
    v.forkWorkingCopy('bbb')
    await w.get('[data-testid="drawer-btn"]').trigger('click')     // 绿态可点
    expect(w.emitted('toggle-drawer')).toHaveLength(2)
    expect(v.isExploring).toBe(true)                               // 点按钮不影响模式
  })

  it('探索态白点:wcDirty 时出现', async () => {
    const v = useViewStore()
    v.loadScanFile(scanFileWith({ bo: { total_window: 10 } }) as any)
    v.forkWorkingCopy('bbb')
    v.updateWorkingCopy('bbb', { bo: { total_window: 42 } })
    const w = mount(ParamsChip)
    expect(w.find('.dirty').exists()).toBe(true)
  })

  it('yaml 漂移:mismatch dot 出现,title 含后端给出的 anchor_file(非硬编码 params.yaml)', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(
      { ok: true, json: () => Promise.resolve({ has_snapshot: true, match: false,
        diffs: [{ path: 'bo.total_window', snapshot: 10, current: 12 }],
        anchor_file: 'exp_wide.yaml' }) } as any)))
    useViewStore().loadScanFile(scanFileWith({ bo: { total_window: 10 } }) as any)
    const w = mount(ParamsChip)
    await vi.waitFor(() => expect(w.find('[data-testid="mismatch-dot"]').exists()).toBe(true))
    expect(w.get('[data-testid="mismatch-dot"]').attributes('title')).toContain('exp_wide.yaml')
  })

  it('yaml 漂移:响应无 anchor_file(老后端)→ title 兜底 params.yaml', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(
      { ok: true, json: () => Promise.resolve({ has_snapshot: true, match: false,
        diffs: [{ path: 'bo.total_window', snapshot: 10, current: 12 }] }) } as any)))
    useViewStore().loadScanFile(scanFileWith({ bo: { total_window: 10 } }) as any)
    const w = mount(ParamsChip)
    await vi.waitFor(() => expect(w.find('[data-testid="mismatch-dot"]').exists()).toBe(true))
    expect(w.get('[data-testid="mismatch-dot"]').attributes('title')).toContain('params.yaml')
  })

  it('drawer-btn 开/关状态类:drawerOpen prop → open class,与模式解耦', async () => {
    const v = useViewStore()
    v.loadScanFile(scanFileWith({ bo: { total_window: 10 } }) as any)
    const w = mount(ParamsChip, { props: { drawerOpen: false } })
    expect(w.get('[data-testid="drawer-btn"]').classes()).not.toContain('open')
    await w.setProps({ drawerOpen: true })
    expect(w.get('[data-testid="drawer-btn"]').classes()).toContain('open')
    v.forkWorkingCopy('bbb')                        // 切到探索态(chip 绿)
    await w.vm.$nextTick()
    expect(w.get('[data-testid="drawer-btn"]').classes()).toContain('open')      // 开态类不随模式变
    await w.setProps({ drawerOpen: false })
    expect(w.get('[data-testid="drawer-btn"]').classes()).not.toContain('open')  // 绿态下关=无 open
  })

  it('chip-label actionable 类:有 WC 才有(hover/pointer 门控,修假 affordance)', async () => {
    const v = useViewStore()
    v.loadScanFile(scanFileWith({ bo: { total_window: 10 } }) as any)
    const w = mount(ParamsChip)
    expect(w.get('[data-testid="chip-label"]').classes()).not.toContain('actionable')
    v.forkWorkingCopy('bbb')
    await w.vm.$nextTick()
    expect(w.get('[data-testid="chip-label"]').classes()).toContain('actionable')
  })

  // 后端 /params_diff 拿这个值当文件名去 load(scan.py:392 落盘名 = name or scan_ts,
  // api.py:684 name 来自扫描对话框「名称(可选)」)。命名过的扫描文件名 ≠ scan_ts,
  // 传 scan_ts 必然 404「scan not found」——标识符只能取 scan.name。
  it('params_diff 请求带 scan.name(命名扫描的文件标识符),不是 scan_ts', async () => {
    const spy = vi.fn((_url: string, ..._rest: any[]) => Promise.resolve(
      { ok: true, json: () => Promise.resolve({ has_snapshot: true, match: true, diffs: [] }) } as any))
    vi.stubGlobal('fetch', spy)
    const f = scanFileWith({ bo: { total_window: 10 } }) as any
    f.scan.name = 'tb深度28-38'                      // 用户填了名称 → 文件名 = 它
    useViewStore().loadScanFile(f)
    mount(ParamsChip)
    await vi.waitFor(() => expect(spy).toHaveBeenCalled())
    const url = String(spy.mock.calls[0]![0])
    expect(url).toContain(`scan_ts=${encodeURIComponent('tb深度28-38')}`)
    expect(url).not.toContain('20260720T000000')
  })

  it('未命名扫描:name 即时间戳,请求照样走 name(与命名扫描同一条路径)', async () => {
    const spy = vi.fn((_url: string, ..._rest: any[]) => Promise.resolve(
      { ok: true, json: () => Promise.resolve({ has_snapshot: true, match: true, diffs: [] }) } as any))
    vi.stubGlobal('fetch', spy)
    useViewStore().loadScanFile(scanFileWith({ bo: { total_window: 10 } }) as any)
    mount(ParamsChip)
    await vi.waitFor(() => expect(spy).toHaveBeenCalled())
    expect(String(spy.mock.calls[0]![0])).toContain('scan_ts=20260720T000000')
  })

  it('锚文件被删:anchor_missing 灰?dot 出现 + title 含文件名,mismatch dot 不出现', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(
      { ok: true, json: () => Promise.resolve({ has_snapshot: true, anchor_missing: true,
        match: false, diffs: [], anchor_file: 'gone.yaml' }) } as any)))
    useViewStore().loadScanFile(scanFileWith({ bo: { total_window: 10 } }) as any)
    const w = mount(ParamsChip)
    await vi.waitFor(() => expect(w.find('[data-testid="anchor-missing-dot"]').exists()).toBe(true))
    expect(w.get('[data-testid="anchor-missing-dot"]').attributes('title')).toContain('gone.yaml')
    expect(w.find('[data-testid="mismatch-dot"]').exists()).toBe(false)   // 排他:锚没了不显 mismatch
  })
})
