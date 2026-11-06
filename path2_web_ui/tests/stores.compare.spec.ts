// compare store 的接线:聚焦样本不改档位、不选中样本;←/→ 在样本间走等于点它;子框只认「配对 node 的子 node」。
// 纯函数(pairOn / matchOf / stepSample)的规则在 annotate.compare-read.spec.ts,这里只测 store 把它们接到
// 当前图、当前 app 产物与标注上的那一层。
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { nextTick } from 'vue'
import { setActivePinia, createPinia } from 'pinia'

// store 里的读请求一律挂起:这里只测接线,app 产物、标注、mapping 由测试直接放进 store
vi.mock('../src/api', async (orig) => {
  const m: Record<string, unknown> = await orig()
  return Object.fromEntries(Object.entries(m).map(([k, v]) =>
    [k, typeof v === 'function' ? vi.fn(() => new Promise(() => {})) : v]))
})

import { useViewStore, type LinkedRun } from '../src/stores/view'
import { useAnnotationStore } from '../src/stores/annotation'
import { useAppLinkStore } from '../src/stores/appLink'
import { useCompareStore, SAMPLES_ROW } from '../src/stores/compare'
import type { AnnRead } from '../src/annotate/model'
import type { EventDict, HitDict } from '../src/types'

const ev = (node: string, s: number, e: number, idx = 0, child_refs: Record<string, string[]> = {}): EventDict =>
  ({ instance_id: `${node}_${s}_${e}#${idx}`, node_id: node, instance_idx: idx, start_idx: s, end_idx: e, child_refs })

// new_step 式:plateau 容器引用 step / today。第 13 天两个 plateau,阶跃分别到 10、11(两次 hit);
// 第 15 天的 plateau 没成 hit
const S10 = ev('step', 10, 10), S11 = ev('step', 10, 11)
const T13 = ev('today', 13, 13), T15 = ev('today', 15, 15)
const P0 = ev('plateau', 0, 13, 0, { step: [S10.instance_id], today: [T13.instance_id] })
const P1 = ev('plateau', 0, 13, 1, { step: [S11.instance_id], today: [T13.instance_id] })
const P3 = ev('plateau', 0, 15, 0, { step: [S10.instance_id], today: [T15.instance_id] })
const hit = (id: string, p: EventDict): HitDict => ({
  hit_id: id, start_idx: p.start_idx, end_idx: p.end_idx, node_index: { plateau: p.instance_id },
  children: [p.instance_id, ...Object.values(p.child_refs ?? {}).flat()],
})

const DATES = Array.from({ length: 20 }, (_, i) => `2024-02-${String(i + 1).padStart(2, '0')}`)

const RUN: LinkedRun = {
  symbol: 'AAA', app: 'app1',
  analysis: { events: [S10, S11, T13, T15, P0, P1, P3], hits: [hit('h0', P0), hit('h1', P1)] } as any,
  pattern_spec: {
    pattern_id: 'app1',
    topology: {
      nodes: [
        { node_id: 'plateau', render_grid: 'time', where_rules: [] },
        { node_id: 'step', render_grid: 'time', where_rules: [], solve: false, produced_by: 'plateau', child_slot: 'step' },
        { node_id: 'today', render_grid: 'time', where_rules: [], solve: false, is_point: true,
          produced_by: 'plateau', child_slot: 'today' },
        // 别的容器的子 node,槽名恰好也叫 step:只看槽名会把对到它的框错当成 plateau 的阶跃子框
        { node_id: 'elsewhere', render_grid: 'time', where_rules: [] },
        { node_id: 'other', render_grid: 'time', where_rules: [], solve: false, produced_by: 'elsewhere', child_slot: 'step' },
      ],
      edges: [],
    },
    event_styles: {},
  } as any,
  scan: { end_node: 'plateau.today' } as any,
}

const box = (id: string, feature: string, s: number, e: number) => ({ id, feature, start: DATES[s], end: DATES[e] })

function annRead(): AnnRead {
  return {
    state: {
      machine: 'pc', data_fingerprint: null,
      features: [{ id: 'f_plat', name: '站上新平台' }, { id: 'f_step', name: '阶跃' }, { id: 'f_other', name: '别的' }],
      patterns: [{ name: 'p' }],
      charts: [{
        symbol: 'AAA',
        boxes: [box('b-step', 'f_step', 10, 11), box('b-other', 'f_other', 10, 11)],
        samples: [
          { id: 'sA', date: DATES[13], pattern: 'p', judgment: 'pos', members: ['b-step'] },
          { id: 'sB', date: DATES[13], pattern: 'p', judgment: 'pos', members: ['b-other'] },
          { id: 'sC', date: DATES[15], pattern: 'p', judgment: 'neg', members: [] },
        ],
      }],
    },
    conflicts: [], unsynced: [], violations: [], merges: [], ignored_files: [], next_seq: 1,
    fingerprint: { local: null, local_error: null, recorded: [] },
    revs: {} as any, membership: {} as any,
    // 子框容差 0:阶跃到 11 的子框只对得上 S11(容差放宽到 1 两个阶跃前缀都对得上,分不出子框起没起作用)
    match: { pos: 3, neg: 1, sub: 0 },
  } as any
}

async function setup() {
  const view = useViewStore()
  const ann = useAnnotationStore()
  const appLink = useAppLinkStore()
  ann.currentPattern = 'p'
  ann.server = annRead()
  appLink.mappings = [{ app: 'app1', pattern: 'p', problem: null,
                        features: { f_plat: 'plateau', f_step: 'step', f_other: 'other' } }]
  view.symbol = 'AAA'
  view.barDates = DATES
  view.mode = 'compare'
  await nextTick()          // appLink 进 compare 时清掉旧产物、去跑(挂起);之后放进测试的产物
  view.setLinkedRun(RUN)
  const cmp = useCompareStore()
  expect(cmp.ready).toBe(true)
  return { view, ann, cmp }
}

describe('compare store · 聚焦与配对', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it('聚焦样本不改档位:配对的 event 在当前档位下画不出来时只选中它、当前日落在样本日', async () => {
    const { view, cmp } = await setup()
    view.setLevel('in_hit')
    expect(cmp.focusSample('sC')).toBe(true)           // 第 15 天只有没成 hit 的 P3
    expect(view.level).toBe('in_hit')
    expect(view.selectedInstanceId).toBe(P3.instance_id)
    expect(view.currentDay).toBe(15)
    expect(view.activeFamilyKey).toBe(SAMPLES_ROW)
  })

  it('聚焦样本不选中它:selection 页照样拿到它的 diagnose', async () => {
    const { ann, cmp } = await setup()
    cmp.focusSample('sC')
    expect(ann.selectedSampleId).toBeNull()
    expect(cmp.focusedSample?.id).toBe('sC')
    expect(cmp.diagnose?.read.id).toBe('sC')
    ann.selectSample('sA')                               // 选中别的样本后 diagnose 跟着选中的
    expect(cmp.focusedSample).toBeNull()
    expect(cmp.diagnose?.read.id).toBe('sA')
  })

  it('←/→ 在样本间走等于点它(选中下一个),到头不动', async () => {
    const { view, ann, cmp } = await setup()
    cmp.focusSample('sB')
    view.stepFocus(1)
    expect(ann.selectedSampleId).toBe('sC')
    cmp.focusSample('sC')
    ann.selectSample(null)
    view.stepFocus(1)                                    // 已是最后一个
    expect(ann.selectedSampleId).toBeNull()
    view.stepFocus(-1)
    expect(ann.selectedSampleId).toBe('sB')
  })

  it('子框只认对到配对 node 的子 node 的框:对到 step 的按子框挑 hit,对到别的 node 的不算子框', async () => {
    const { cmp } = await setup()
    expect(cmp.sampleReads.get('sA')?.pairing.hitId).toBe('h1')   // 子框阶跃到 11 → S11 那次
    expect(cmp.sampleReads.get('sB')?.pairing.hitId).toBe('h0')   // 不当子框 → 当天第一个 hit
  })

  it('当家行换走(Esc、点了 app 的格)后聚焦样本作废', async () => {
    const { view, cmp } = await setup()
    cmp.focusSample('sC')
    await nextTick()                                     // 聚焦和 Esc 是两次操作,中间隔着一次刷新
    view.setActiveFamily(null)
    await nextTick()
    expect(cmp.focusedSampleId).toBeNull()
  })
})
