// 选中卡:选中的那一个在右侧栏的细节,十一行、行序固定,每行「标签 值」。
// 不适用的行照占位置、写 `—`;适用但是空的写 `none`。
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { setActivePinia, createPinia } from 'pinia'

// store 里的读请求一律挂起:app 产物、标注、mapping 由测试直接放进 store
vi.mock('../src/api', async (orig) => {
  const m: Record<string, unknown> = await orig()
  return Object.fromEntries(Object.entries(m).map(([k, v]) =>
    [k, typeof v === 'function' ? vi.fn(() => new Promise(() => {})) : v]))
})
vi.mock('../src/stores/config', () => ({ useConfigStore: vi.fn(() => ({ config: null, saveLastPattern: vi.fn() })) }))

import { useViewStore, type LinkedRun } from '../src/stores/view'
import { useAnnotationStore } from '../src/stores/annotation'
import { useAppLinkStore } from '../src/stores/appLink'
import { useCompareStore } from '../src/stores/compare'
import SelectionCard from '../src/components/SelectionCard.vue'
import type { AnnRead } from '../src/annotate/model'
import type { EventDict, HitDict, MultiScanResultFile } from '../src/types'

const ev = (node: string, s: number, e: number, idx = 0, child_refs: Record<string, string[]> = {}): EventDict =>
  ({ instance_id: `${node}_${s}_${e}#${idx}`, node_id: node, instance_idx: idx, start_idx: s, end_idx: e, child_refs })
const hit = (id: string, p: EventDict): HitDict => ({
  hit_id: id, start_idx: p.start_idx, end_idx: p.end_idx, node_index: { plateau: p.instance_id },
  children: [p.instance_id, ...Object.values(p.child_refs ?? {}).flat()],
})

const ROWS = ['buys', 'hits', 'nodes', 'family', 'feedback', 'sample', 'paired', 'level', 'failed', 'id', 'copy']
type W = ReturnType<typeof mount>
/** 卡上的行:[标签, 值的各行];不适用的行值是 ['—'] */
const rows = (w: W): Record<string, string[]> => Object.fromEntries(w.findAll('.row').map(r => {
  const lines = r.findAll('.line').map(l => l.text())
  return [r.get('.lb').text(), lines.length ? lines : [r.get('.na').text()]]
}))
const NA = ['—']

describe('SelectionCard · app 模式', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  // 旧平台 O 被全部 hit 共用;两种阶跃切法 S10(一根)、S11(两根);13、14 两天各有两种切法,15 只有一根那种;
  // 16 那天的 today 与 plateau 没成 hit
  const O = ev('old_plat', 0, 9)
  const S10 = ev('step', 10, 10), S11 = ev('step', 10, 11)
  const T13 = ev('today', 13, 13), T14 = ev('today', 14, 14), T15 = ev('today', 15, 15), T16 = ev('today', 16, 16)
  const kids = (s: EventDict, t: EventDict) => ({ old: [O.instance_id], step: [s.instance_id], today: [t.instance_id] })
  const P13a = ev('plateau', 0, 13, 0, kids(S10, T13)), P13b = ev('plateau', 0, 13, 1, kids(S11, T13))
  const P14a = ev('plateau', 0, 14, 0, kids(S10, T14)), P14b = ev('plateau', 0, 14, 1, kids(S11, T14))
  const P15a = ev('plateau', 0, 15, 0, kids(S10, T15))
  const P16a = ev('plateau', 0, 16, 0, kids(S10, T16))
  const DATES = Array.from({ length: 20 }, (_, i) => `2024-11-${String(i + 1).padStart(2, '0')}`)

  function makeFixture(extra: EventDict[] = []): MultiScanResultFile {
    return {
      pattern_ids: ['p1'],
      per_pattern: { p1: {
        end_node: 'plateau.today',
        pattern_spec: {
          pattern_id: 'p1',
          topology: {
            nodes: [
              { node_id: 'plateau', render_grid: 'time', where_rules: [] },
              { node_id: 'old_plat', render_grid: 'time', where_rules: [], solve: false },
              { node_id: 'step', render_grid: 'time', where_rules: [], solve: false },
              { node_id: 'today', render_grid: 'time', where_rules: [], solve: false, is_point: true },
            ],
            edges: [],
          },
          event_styles: {},
        },
      } },
      results: [{ symbol: 'AAA', per_pattern: { p1: { analysis: {
        events: [O, S10, S11, T13, T14, T15, T16, P13a, P13b, P14a, P14b, P15a, P16a, ...extra],
        hits: [hit('a13', P13a), hit('b13', P13b), hit('a14', P14a), hit('b14', P14b), hit('a15', P15a)],
      }, summary: { hits: 5 } } } }],
      scan: { win_start: '2020-01-01', win_end: '2020-12-31', label_horizon: 20 },
    } as any
  }

  function setup(extra: EventDict[] = []) {
    const view = useViewStore()
    view.loadScanFile(makeFixture(extra))
    view.setLevel('detected')
    view.setBarDates(DATES)
    return { view, w: mount(SelectionCard) }
  }

  it('什么都没选中:不出这张卡', () => {
    const { w } = setup()
    expect(w.find('[data-testid="sel-card"]').exists()).toBe(false)
  })

  it('十一行行序固定,不论选中的是什么', async () => {
    const { view, w } = setup()
    view.clickFamilyLine('hits@0')
    await nextTick()
    expect(w.findAll('.row .lb').map(l => l.text())).toEqual(ROWS)
    expect(w.findAll('.row').map(r => r.attributes('data-testid'))).toEqual(ROWS.map(n => `sel-card-${n}`))
    view.selectNode('step')
    await nextTick()
    expect(w.findAll('.row .lb').map(l => l.text())).toEqual(ROWS)
  })

  it('hit 的一族:牵出的买点日与 hit;其余不适用;copy 是 Shift+C 会复制的那一行', async () => {
    const { view, w } = setup()
    view.clickFamilyLine('hits@0')
    await nextTick()
    expect(rows(w)).toEqual({
      buys: ['2024-11-14…2024-11-16 ×3'], hits: ['×5'], nodes: NA, family: NA, feedback: NA, sample: NA, paired: NA,
      level: NA, failed: NA, id: NA, copy: ['AAA p1 hit_family 2024-11-01 buys 2024-11-14…2024-11-16 ×3 hits ×5'],
    })
  })

  it('买点日(这天两次):hits 写个数、逐次写区别;family 是它那一族的起点', async () => {
    const { view, w } = setup()
    view.clickBuyDay('hits@0', 13)
    await nextTick()
    expect(rows(w)).toEqual({
      buys: NA, hits: ['×2', 'step→2024-11-11', 'step→2024-11-12'], nodes: NA, family: ['2024-11-01'],
      feedback: NA, sample: NA, paired: NA, level: NA, failed: NA, id: NA, copy: ['AAA p1 buy 2024-11-14 hits ×2'],
    })
  })

  it('一次 hit:nodes 一行一个 node 的起止;id 是它的内部编号', async () => {
    const { view, w } = setup()
    view.clickBuyDay('hits@0', 13)
    view.stepStack(1); view.stepStack(1)
    await nextTick()
    expect(rows(w)).toEqual({
      buys: ['2024-11-14 ×1'], hits: NA,
      nodes: ['plateau 2024-11-01→2024-11-14', 'old_plat 2024-11-01→2024-11-10', 'step 2024-11-11→2024-11-12', 'today 2024-11-14'],
      family: ['2024-11-01'], feedback: NA, sample: NA, paired: NA, level: NA, failed: NA, id: ['b13'],
      copy: ['AAA p1 hit 2024-11-01→2024-11-14 step→2024-11-12 buys 2024-11-14 ×1 [b13]'],
    })
  })

  it('进了 hit 的 event:level 写档位;没有没过的 where 时 failed 写 none', async () => {
    const { view, w } = setup()
    view.focusMark([S10.instance_id])
    await nextTick()
    expect(rows(w)).toEqual({
      buys: ['2024-11-14…2024-11-16 ×3'], hits: ['×3'], nodes: NA, family: NA, feedback: NA, sample: NA, paired: NA,
      level: ['in_hit'], failed: ['none'], id: [S10.instance_id],
      copy: [`AAA p1 event step 2024-11-11 buys 2024-11-14…2024-11-16 ×3 hits ×3 [${S10.instance_id}]`],
    })
  })

  it('没被 hit 用到的 event:buys、hits 适用但是空,写 none(不是 —);failed 写没过的 where 名', async () => {
    const { view, w } = setup()
    view.focusMark([P16a.instance_id])
    view.diag = { symbol: 'AAA', pattern_id: 'p1', note: '', nodes: { plateau: { rel: [], attr: [
      { instance_id: P16a.instance_id, node_id: 'plateau', start_idx: 0, end_idx: 16, clauses: {
        width: { satisfied: false, measured: 1, op: '>=', threshold: 2 },
        vol: { satisfied: true, measured: 3, op: '>=', threshold: 2 } } },
    ] } } } as any
    await nextTick()
    const r = rows(w)
    expect([r.buys, r.hits, r.level, r.failed, r.id]).toEqual([['none'], ['none'], ['detected'], ['width'], [P16a.instance_id]])
    expect(r.copy).toEqual([`AAA p1 event plateau 2024-11-01→2024-11-17 [${P16a.instance_id}]`])
  })

  it('当前档位下画不出来的 event:level 后面写 hidden', async () => {
    const { view, w } = setup()
    view.setLevel('in_hit')
    view.focusEvent(P16a.instance_id)                 // 只到 detected
    await nextTick()
    expect(rows(w).level).toEqual(['detected hidden'])
  })

  it('hidden 看的是这个 event 自己画没画出来:同一条 band 同一天另有画出来的 event,它自己没画时照样写 hidden', async () => {
    // 第 13 天那一格多一个没成 hit 的 plateau:in_hit 档下这一格画的是 P13a、P13b,不画它
    const P13c = ev('plateau', 0, 13, 2, kids(S10, T13))
    const { view, w } = setup([P13c])
    view.setLevel('in_hit')
    view.focusEvent(P13c.instance_id)
    await nextTick()
    expect(rows(w).level).toEqual(['detected hidden'])
    view.focusEvent(P13a.instance_id)                 // 同一格里画出来的那个
    await nextTick()
    expect(rows(w).level).toEqual(['in_hit'])
    view.setLevel('detected')                         // 这一档三个都画
    view.focusEvent(P13c.instance_id)
    await nextTick()
    expect(rows(w).level).toEqual(['detected'])
  })

  it('node:卡上各行都不适用,只有 copy', async () => {
    const { view, w } = setup()
    view.selectNode('step')
    await nextTick()
    expect(rows(w)).toEqual({
      buys: NA, hits: NA, nodes: NA, family: NA, feedback: NA, sample: NA, paired: NA, level: NA, failed: NA, id: NA,
      copy: ['AAA p1 node step'],
    })
  })
})

describe('SelectionCard · compare 下的 feedback / sample / paired 三行', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  // 第 13 天两个 plateau,阶跃分别到 10、11(两次 hit);第 15 天的 plateau 没成 hit
  const S10 = ev('step', 10, 10), S11 = ev('step', 10, 11)
  const T13 = ev('today', 13, 13), T15 = ev('today', 15, 15)
  const P0 = ev('plateau', 0, 13, 0, { step: [S10.instance_id], today: [T13.instance_id] })
  const P1 = ev('plateau', 0, 13, 1, { step: [S11.instance_id], today: [T13.instance_id] })
  const P3 = ev('plateau', 0, 15, 0, { step: [S10.instance_id], today: [T15.instance_id] })
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
        ],
        edges: [],
      },
      event_styles: {},
    } as any,
    scan: { end_node: 'plateau.today' } as any,
  }
  function annRead(more: { samples?: any[]; feedback?: any[] } = {}): AnnRead {
    return {
      state: {
        machine: 'pc', data_fingerprint: null,
        features: [{ id: 'f_step', name: '阶跃' }],
        patterns: [{ name: 'p' }],
        charts: [{
          symbol: 'AAA',
          boxes: [{ id: 'b-step', feature: 'f_step', start: DATES[10], end: DATES[11] }],
          samples: [
            { id: 'sA', date: DATES[13], pattern: 'p', judgment: 'pos', members: ['b-step'] },   // 子框阶跃到 11:配对 h1
            { id: 'sB', date: DATES[13], pattern: 'p', judgment: 'pos', members: [] },           // 配对当天第一次 h0
            { id: 'sC', date: DATES[15], pattern: 'p', judgment: 'neg', members: [] },
            ...(more.samples ?? []),
          ],
          ...(more.feedback ? { feedback: more.feedback } : {}),
        }],
      },
      conflicts: [], unsynced: [], violations: [], merges: [], ignored_files: [], next_seq: 1,
      fingerprint: { local: null, local_error: null, recorded: [] },
      revs: {} as any, membership: {} as any,
      match: { pos: 3, neg: 1, sub: 0 },
    } as any
  }

  async function setup(run: LinkedRun = RUN, read: AnnRead = annRead()) {
    const view = useViewStore()
    const ann = useAnnotationStore()
    const appLink = useAppLinkStore()
    ann.currentPattern = 'p'
    ann.server = read
    appLink.mappings = [{ app: 'app1', pattern: 'p', problem: null, features: { f_step: 'step' } }]
    view.symbol = 'AAA'
    view.barDates = DATES
    view.mode = 'compare'
    await nextTick()
    view.setLinkedRun(run)
    const cmp = useCompareStore()
    expect(cmp.ready).toBe(true)
    return { view, cmp, w: mount(SelectionCard) }
  }

  it('样本:sample 写它自己(字母、判断、样本日、✓ / ✗),paired 写配对的 event;feedback 不适用', async () => {
    const { cmp, w } = await setup()
    cmp.focusSample('sA')
    await nextTick()
    expect(rows(w)).toEqual({
      buys: NA, hits: ['×2', 'step→2024-02-12', 'step→2024-02-11'], nodes: NA, family: NA, feedback: NA,
      sample: ['a pos 2024-02-14 ✓'], paired: ['event plateau 2024-02-01→2024-02-14'],
      level: NA, failed: NA, id: ['sA'], copy: ['AAA p sample 2024-02-14 a pos hits ×2 [sA]'],
    })
  })

  it('样本日没有在场的 hit(只有没成 hit 的 event):hits 适用但是空,写 none;paired 照样写配对的那个 event', async () => {
    const { cmp, w } = await setup()
    cmp.focusSample('sC')                                // 第 15 天只有没成 hit 的 P3
    await nextTick()
    const r = rows(w)
    expect([r.hits, r.sample, r.id]).toEqual([['none'], ['c neg 2024-02-16 ✓'], ['sC']])
    expect(r.paired).toEqual(['event plateau 2024-02-01→2024-02-16'])
  })

  it('一次 hit:sample 写样本日在场有它的样本,paired 只写配对到它的样本;这张图上没有反馈时 feedback 写 none', async () => {
    const { view, cmp, w } = await setup()
    cmp.focusSample('sA')
    view.stepStack(1)                                    // 进到配对的那次 h1
    await nextTick()
    expect(rows(w)).toEqual({
      buys: ['2024-02-14 ×1'], hits: NA,
      nodes: ['plateau 2024-02-01→2024-02-14', 'step 2024-02-11→2024-02-12', 'today 2024-02-14'],
      family: ['2024-02-01'], feedback: ['none'],
      sample: ['a pos 2024-02-14 ✓', 'b pos 2024-02-14 ✓'], paired: ['sample a pos 2024-02-14 ✓'],
      level: NA, failed: NA, id: ['h1'],
      copy: ['AAA p hit 2024-02-01→2024-02-14 step→2024-02-12 buys 2024-02-14 ×1 [h1]'],
    })
  })
})

describe('SelectionCard · feedback 行按牵出的 hit 的全部买点日找反馈', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  // 第 13 天两次 hit(h0、h1,各买第 13 天);另一次 h9 的 today 跨第 17、18 两天——一次 hit 买两天
  const S10 = ev('step', 10, 10), S11 = ev('step', 10, 11)
  const T13 = ev('today', 13, 13), T18 = ev('today', 17, 18)
  const P0 = ev('plateau', 0, 13, 0, { step: [S10.instance_id], today: [T13.instance_id] })
  const P1 = ev('plateau', 0, 13, 1, { step: [S11.instance_id], today: [T13.instance_id] })
  const P9 = ev('plateau', 0, 18, 0, { step: [S10.instance_id], today: [T18.instance_id] })
  const DATES = Array.from({ length: 20 }, (_, i) => `2024-02-${String(i + 1).padStart(2, '0')}`)
  const RUN: LinkedRun = {
    symbol: 'AAA', app: 'app1',
    analysis: { events: [S10, S11, T13, T18, P0, P1, P9], hits: [hit('h0', P0), hit('h1', P1), hit('h9', P9)] } as any,
    pattern_spec: {
      pattern_id: 'app1',
      topology: {
        nodes: [
          { node_id: 'plateau', render_grid: 'time', where_rules: [] },
          { node_id: 'step', render_grid: 'time', where_rules: [], solve: false, produced_by: 'plateau', child_slot: 'step' },
          { node_id: 'today', render_grid: 'time', where_rules: [], solve: false, is_point: true,
            produced_by: 'plateau', child_slot: 'today' },
        ],
        edges: [],
      },
      event_styles: {},
    } as any,
    scan: { end_node: 'plateau.today' } as any,
  }
  const point = (id: string, day: number) => ({ id, pattern: 'p', app_id: 'app1', app_ver: 'v0',
    start: DATES[day], end: DATES[day], target: 'point', source: 'picked', note: 'x' })
  // 三条反馈各点一天:第 13、17、18 天;样本 sD 放在第 18 天(h9 那天在场)
  const read = (): AnnRead => ({
    state: {
      machine: 'pc', data_fingerprint: null, features: [], patterns: [{ name: 'p' }],
      charts: [{
        symbol: 'AAA', boxes: [],
        samples: [{ id: 'sD', date: DATES[18], pattern: 'p', judgment: 'pos', members: [] }],
        feedback: [point('f13', 13), point('f17', 17), point('f18', 18)],
      }],
    },
    conflicts: [], unsynced: [], violations: [], merges: [], ignored_files: [], next_seq: 1,
    fingerprint: { local: null, local_error: null, recorded: [] },
    revs: {} as any, membership: {} as any,
    match: { pos: 3, neg: 1, sub: 0 },
  } as any)

  async function setup() {
    const view = useViewStore()
    const ann = useAnnotationStore()
    const appLink = useAppLinkStore()
    ann.currentPattern = 'p'
    ann.server = read()
    appLink.mappings = [{ app: 'app1', pattern: 'p', problem: null, features: {} }]
    view.symbol = 'AAA'
    view.barDates = DATES
    view.mode = 'compare'
    await nextTick()
    view.setLinkedRun(RUN)
    const cmp = useCompareStore()
    return { view, cmp, w: mount(SelectionCard) }
  }

  it('从样本进到在场的那次 hit:按这次 hit 的买点日找(第 17、18 天),不是只看样本日', async () => {
    const { view, cmp, w } = await setup()
    expect(cmp.focusSample('sD')).toBe(true)
    await nextTick()
    expect(rows(w).feedback).toEqual(NA)                 // 样本自己不写反馈
    view.stepStack(1)
    await nextTick()
    expect(view.selPath).toEqual([{ kind: 'sample', sampleId: 'sD' }, { kind: 'hit', hitId: 'h9', day: 18 }])
    expect(rows(w).feedback).toEqual(['2024-02-18', '2024-02-19'])
  })

  it('一次 hit 买好几天:哪个买点日上的反馈都列出;选中一整天(那天有几次)时只列那一天的', async () => {
    const { view, w } = await setup()
    view.focusHit('h9')
    await nextTick()
    expect(view.focusedHitId).toBe('h9')
    expect(rows(w).feedback).toEqual(['2024-02-18', '2024-02-19'])
    view.clickBuyDay('hits@0', 13)                       // 这天两次:选中的是这一天整体
    await nextTick()
    expect(view.focusedHitId).toBeNull()
    expect(rows(w).feedback).toEqual(['2024-02-14'])
  })
})
