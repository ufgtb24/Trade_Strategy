// 副图族行上的点击:bracket 记号 / 买入日 ▼ / band 格各选中什么,带上当前日与当家行。
import { describe, it, expect, beforeEach, vi } from 'vitest'

vi.mock('../src/api', () => ({ saveWcMirror: async () => ({ ok: true } as any), clearWcMirror: async () => ({ ok: true } as any),
  getDiagnose: vi.fn(() => Promise.resolve(null)),
  listScans: vi.fn(() => Promise.resolve([])),
}))
vi.mock('../src/stores/config', () => ({
  useConfigStore: vi.fn(() => ({ config: null })),
}))
import { setActivePinia, createPinia } from 'pinia'
import { useViewStore } from '../src/stores/view'
import { handleChartClick } from '../src/components/KlineChart'
import type { EventDict, HitDict, MultiScanResultFile } from '../src/types'

const ev = (node: string, s: number, e: number, idx = 0, child_refs: Record<string, string[]> = {}): EventDict =>
  ({ instance_id: `${node}_${s}_${e}#${idx}`, node_id: node, instance_idx: idx, start_idx: s, end_idx: e, child_refs })

// new_step 式:plateau 容器引用 step / today;同一个阶跃前缀被几天的 plateau 共用
const S10 = ev('step', 10, 10), S11 = ev('step', 10, 11)
const T13 = ev('today', 13, 13), T14 = ev('today', 14, 14), T15 = ev('today', 15, 15)
const P0 = ev('plateau', 0, 13, 0, { step: [S10.instance_id], today: [T13.instance_id] })
const P1 = ev('plateau', 0, 13, 1, { step: [S11.instance_id], today: [T13.instance_id] })
const P2 = ev('plateau', 0, 14, 0, { step: [S10.instance_id], today: [T14.instance_id] })
const P3 = ev('plateau', 0, 15, 0, { step: [S10.instance_id], today: [T15.instance_id] })   // 没成 hit
const hit = (id: string, p: EventDict): HitDict => ({
  hit_id: id, start_idx: p.start_idx, end_idx: p.end_idx, node_index: { plateau: p.instance_id },
  children: [p.instance_id, ...Object.values(p.child_refs ?? {}).flat()],
})

function makeFixture(): MultiScanResultFile {
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
    results: [{ symbol: 'AAA', per_pattern: { p1: { analysis: {
      events: [S10, S11, T13, T14, T15, P0, P1, P2, P3],
      hits: [hit('h0', P0), hit('h1', P1), hit('h2', P2)],
    }, summary: { hits: 3 } } } }],
    scan: { win_start: '2020-01-01', win_end: '2020-12-31', label_horizon: 20 },
  } as any
}

describe('handleChartClick · 族行', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  function setup() {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.setLevel('detected')
    return view
  }

  it('bracket 上一格、这一列有 ▼(这天两次 hit)→ 和点 ▼ 一样选中这一天整体,哪一次都不算选中', () => {
    const view = setup()
    const handled = handleChartClick({ seriesName: 'brackets',
      data: { kind: 'mark', hit_id: 'h0', hit_ids: ['h0', 'h1'], buy_day: 13, family_key: 'hits@0', value: [13, 13, 0, 1] } }, [], view)
    expect(handled).toBe(true)
    expect(view.selPath).toEqual([{ kind: 'hit_family', familyKey: 'hits@0' }, { kind: 'buy', day: 13 }])
    expect(view.focusedHitId).toBeNull()
    expect(view.selDayHitIds).toEqual(['h0', 'h1'])
    expect(view.currentDay).toBe(13)
    expect(view.activeFamilyKey).toBe('hits@0')
  })

  it('bracket 上一格、这一列没有 ▼(格里两次 hit)→ 选中其中第一次,当前日 = 它的买入日,当家行 = 这一族', () => {
    const view = setup()
    const handled = handleChartClick({ seriesName: 'brackets',
      data: { kind: 'mark', hit_id: 'h0', hit_ids: ['h0', 'h1'], family_key: 'hits@0', value: [13, 13, 0, 1] } }, [], view)
    expect(handled).toBe(true)
    expect(view.candidateHitIds.size).toBe(0)
    expect(view.focusedHitId).toBe('h0')
    expect(view.currentDay).toBe(13)
    expect(view.activeFamilyKey).toBe('hits@0')
  })

  it('bracket 上一格(没有 ▼ 的那一列)几次 hit 买入日不一样 → 选中第一次,竖线落在它的买入日,别的几次在这一族里按日子走', () => {
    const view = setup()
    handleChartClick({ seriesName: 'brackets',
      data: { kind: 'mark', hit_id: 'h0', hit_ids: ['h0', 'h2'], family_key: 'hits@0', value: [13, 14, 0, 1] } }, [], view)
    expect(view.candidateHitIds.size).toBe(0)
    expect([view.focusedHitId, view.currentDay, view.activeFamilyKey]).toEqual(['h0', 13, 'hits@0'])
  })

  it('bracket 买入日 ▼ → 选中这一天;这天只有一次 hit 时就是那次 hit,当前日 = 买入日', () => {
    const view = setup()
    handleChartClick({ seriesName: 'brackets',
      data: { kind: 'buy', hit_id: 'h2', hit_ids: ['h2'], buy_day: 14, family_key: 'hits@0', value: [14, 14, 0, 1] } }, [], view)
    expect(view.focusedHitId).toBe('h2')
    expect(view.currentDay).toBe(14)
  })

  it('band 一格(几个成员)→ 选中其中第一个 event,用到它的 hit 画细框、不算选中;一个成员的格选中它;竖线落在它的终点', () => {
    const view = setup()
    handleChartClick({ seriesName: 'intervals',
      data: { instance_id: P0.instance_id, member_ids: [P0.instance_id, P1.instance_id], family_key: 'plateau@0',
              value: [13, 13, 0, 0, 3, 1] } }, [], view)
    expect(view.selPath).toEqual([{ kind: 'node', band: 'plateau' }, { kind: 'event', instanceId: P0.instance_id }])
    expect([view.selectedInstanceId, view.focusedHitId]).toEqual([P0.instance_id, null])
    expect([...view.candidateHitIds]).toEqual(['h0'])
    handleChartClick({ seriesName: 'intervals',
      data: { instance_id: P2.instance_id, member_ids: [P2.instance_id], family_key: 'plateau@0',
              value: [14, 14, 0, 0, 3, 1] } }, [], view)
    expect([view.selectedInstanceId, view.focusedHitId]).toEqual([P2.instance_id, null])
    expect([...view.candidateHitIds]).toEqual(['h2'])
    expect(view.currentDay).toBe(14)
    expect(view.activeFamilyKey).toBeNull()             // 选中 event 时,band 的族底线(plateau@0)不加粗
  })

  it('点空白 → 清焦点,返回 false', () => {
    const view = setup()
    view.focusHit('h0')
    expect(handleChartClick({ seriesName: '' } as any, [], view)).toBe(false)
    expect(view.focusedHitId).toBeNull()
    expect(view.currentDay).toBeNull()
  })
})
