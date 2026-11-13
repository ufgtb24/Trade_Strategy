// 按键走动与视窗:只有这一下把当前日竖线带到了别的日子、而且出了视窗(两边各留 5 根)才平移,视窗宽度不变;
// 竖线没动的按键(到头、进到同一天的某一次、Esc 退回同一天)不动视窗——用户自己平移开去看别处时不被拉回来。
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import KlineChart from '../../src/components/KlineChart.vue'
import { useViewStore } from '../../src/stores/view'
import type { EventDict, HitDict, MultiScanResultFile } from '../../src/types'

vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })

const N = 100
const BARS = Array.from({ length: N }, (_, i) => ({
  date: new Date(Date.UTC(2025, 0, 1 + i)).toISOString().slice(0, 10), o: 10, h: 11, l: 9, c: 10 + (i % 2), v: 1000 + i, rv: 1,
}))

vi.mock('../../src/api', async (orig) => {
  const m: Record<string, unknown> = await orig()
  const out = Object.fromEntries(Object.entries(m).map(([k, v]) =>
    [k, typeof v === 'function' ? vi.fn(() => new Promise(() => {})) : v]))
  return { ...out, getOhlc: vi.fn(() => Promise.resolve({ bars: BARS })) }
})
vi.mock('../../src/stores/config', () => ({ useConfigStore: vi.fn(() => ({ config: null, saveLastPattern: vi.fn() })) }))

// 假的图表:视窗(dataZoom 的 start / end,百分比)由测试摆;平移动作(dispatchAction dataZoom)记下来并照它挪视窗
const zoom = { start: 0, end: 100 }
const pans: { start: number; end: number }[] = []
function makeFakeChart() {
  const zr = { on: vi.fn(), off: vi.fn() }
  return {
    setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn(), clear: vi.fn(),
    on: vi.fn(), off: vi.fn(), getZr: () => zr, getOption: () => ({ dataZoom: [{ ...zoom }] }),
    dispatchAction: vi.fn((a: any) => {
      if (a?.type !== 'dataZoom') return
      pans.push({ start: a.start, end: a.end })
      zoom.start = a.start; zoom.end = a.end
    }),
    convertToPixel: () => [0, 0], convertFromPixel: () => [0, 0], getWidth: () => 800, getHeight: () => 600,
  }
}
vi.mock('echarts', () => ({ init: vi.fn(() => makeFakeChart()) }))

const ev = (node: string, s: number, e: number, idx = 0, child_refs: Record<string, string[]> = {}): EventDict =>
  ({ instance_id: `${node}_${s}_${e}#${idx}`, node_id: node, instance_idx: idx, start_idx: s, end_idx: e, child_refs })
// 一族 hit(起于 0):第 13、14 天各两次(阶跃切到 10 或 11),第 15 天一次
const S10 = ev('step', 10, 10), S11 = ev('step', 10, 11)
const T13 = ev('today', 13, 13), T14 = ev('today', 14, 14), T15 = ev('today', 15, 15)
const kids = (s: EventDict, t: EventDict) => ({ step: [s.instance_id], today: [t.instance_id] })
const P13a = ev('plateau', 0, 13, 0, kids(S10, T13)), P13b = ev('plateau', 0, 13, 1, kids(S11, T13))
const P14a = ev('plateau', 0, 14, 0, kids(S10, T14)), P14b = ev('plateau', 0, 14, 1, kids(S11, T14))
const P15a = ev('plateau', 0, 15, 0, kids(S10, T15))
const hit = (id: string, p: EventDict): HitDict => ({
  hit_id: id, start_idx: p.start_idx, end_idx: p.end_idx, node_index: { plateau: p.instance_id },
  children: [p.instance_id, ...Object.values(p.child_refs ?? {}).flat()],
})

// 两族各只买一天:起于 0 的那族买第 13 根,起于 5 的那族买第 20 根
const T20 = ev('today', 20, 20)
const Q20 = ev('plateau', 5, 20, 0, kids(S10, T20))
const TWO_FAMILIES = { events: [S10, T13, T20, P13a, Q20], hits: [hit('a13', P13a), hit('q20', Q20)] }

function makeFixture(analysis: { events: EventDict[]; hits: HitDict[] } | null = null): MultiScanResultFile {
  return {
    pattern_ids: ['p1'],
    per_pattern: { p1: {
      end_node: 'plateau.today',
      pattern_spec: {
        pattern_id: 'p1',
        topology: {
          nodes: [
            { node_id: 'plateau', render_grid: 'time', where_rules: [] },
            { node_id: 'step', render_grid: 'time', where_rules: [], solve: false },
            { node_id: 'today', render_grid: 'time', where_rules: [], solve: false, is_point: true },
          ],
          edges: [],
        },
        event_styles: {},
      },
    } },
    results: [{ symbol: 'AAA', per_pattern: { p1: { analysis: analysis ?? {
      events: [S10, S11, T13, T14, T15, P13a, P13b, P14a, P14b, P15a],
      hits: [hit('a13', P13a), hit('b13', P13b), hit('a14', P14a), hit('b14', P14b), hit('a15', P15a)],
    }, summary: { hits: 5 } } } }],
    scan: { scan_ts: 't', start_date: BARS[0].date, end_date: BARS[N - 1].date,
            win_start: BARS[0].date, win_end: BARS[N - 1].date, label_horizon: 20 },
  } as any
}

/** 把视窗摆到第 from ~ to 根(下标) */
const lookAt = (from: number, to: number) => { zoom.start = (from / (N - 1)) * 100; zoom.end = (to / (N - 1)) * 100 }
/** 视窗眼下是第几根到第几根 */
const windowNow = () => [zoom.start, zoom.end].map(p => Math.round((p / 100) * (N - 1)))
const press = (key: string) => window.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true }))

describe('KlineChart · 按键走动带出的平移', () => {
  beforeEach(() => { setActivePinia(createPinia()); pans.length = 0; lookAt(0, N - 1) })

  async function setup(analysis: { events: EventDict[]; hits: HitDict[] } | null = null) {
    const view = useViewStore()
    view.loadScanFile(makeFixture(analysis))
    view.setLevel('detected')
    const w = mount(KlineChart)
    await flushPromises()
    expect(view.barDates).toHaveLength(N)
    pans.length = 0
    return { view, w }
  }

  it('← / → 把竖线带到别的日子:还在视窗里(离两边 5 根以上)不平移;出了视窗才平移,宽度不变、离边 5 根', async () => {
    const { view, w } = await setup()
    lookAt(0, 30)
    view.clickBuyDay('hits@0', 13)
    press('ArrowRight')
    expect(view.currentDay).toBe(14)
    expect(pans).toEqual([])                             // 第 14 根在 0~30 里

    lookAt(40, 70)                                       // 用户自己平移开了
    press('ArrowRight')
    expect(view.currentDay).toBe(15)                     // 竖线到了第 15 根,在视窗左边外面
    expect(pans).toHaveLength(1)
    expect(windowNow()).toEqual([10, 40])                // 左边留 5 根,宽度仍是 30 根
    w.unmount()
  })

  it('竖线没动的按键不平移:到头、↑ / ↓ 进到同一天的某一次并在几次之间换、Esc 退回这一天、再退回一族', async () => {
    const { view, w } = await setup()
    view.clickBuyDay('hits@0', 15)                       // 最后一个买点日
    lookAt(40, 70)                                       // 竖线在视窗外
    press('ArrowRight')                                  // 到头
    expect(view.currentDay).toBe(15)
    expect(pans).toEqual([])

    view.clickBuyDay('hits@0', 14)                       // 这天两次
    lookAt(40, 70)
    press('ArrowDown')
    expect(view.selPath.map(s => s.kind)).toEqual(['hit_family', 'buy', 'hit'])
    press('ArrowDown')
    press('ArrowUp')
    expect(view.currentDay).toBe(14)
    expect(pans).toEqual([])
    press('Escape')                                      // 退回这一天
    expect(view.selPath.map(s => s.kind)).toEqual(['hit_family', 'buy'])
    press('Escape')                                      // 退回一族
    expect(view.selPath.map(s => s.kind)).toEqual(['hit_family'])
    expect(view.currentDay).toBe(14)
    expect(pans).toEqual([])
    expect(windowNow()).toEqual([40, 70])
    w.unmount()
  })

  it('从一族换到旁边一族:竖线不动,不平移', async () => {
    const { view, w } = await setup(TWO_FAMILIES)
    view.setCurrentDay(13)
    view.clickFamilyLine('hits@0')
    lookAt(40, 70)                                       // 竖线(第 13 根)在视窗外
    press('ArrowRight')
    expect(view.selPath).toEqual([{ kind: 'hit_family', familyKey: 'hits@5' }])
    expect(view.currentDay).toBe(13)
    expect(pans).toEqual([])
    expect(windowNow()).toEqual([40, 70])
    w.unmount()
  })

  it('Esc 退一层把竖线带回了别的日子、而且在视窗外:平移过去', async () => {
    const { view, w } = await setup()
    view.focusEvent(S11.instance_id)                     // 竖线落在阶跃的终点第 11 根
    lookAt(0, 30)
    press('ArrowRight')                                  // 进到它牵出的买点日
    expect(view.selPath.map(s => s.kind)).toEqual(['node', 'event', 'buy'])
    expect(view.currentDay).toBe(13)
    expect(pans).toEqual([])
    lookAt(40, 70)
    press('Escape')                                      // 退回这个 event:竖线回到第 11 根
    expect(view.selPath.map(s => s.kind)).toEqual(['node', 'event'])
    expect(view.currentDay).toBe(11)
    expect(pans).toHaveLength(1)
    expect(windowNow()).toEqual([6, 36])
    w.unmount()
  })
})
