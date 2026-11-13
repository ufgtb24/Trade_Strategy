// compare store 的接线:聚焦样本不改档位、选中的只是样本;← / → 在样本间走等于点它、↑ / ↓ 进到样本日在场的
// hit 并在它们之间走(和 diagnose 卡片同一个先后);点框选中这个框,← / → 换到旁边的框;子框只认「配对 node 的子 node」。
// 纯函数(pairOn / matchOf)的规则在 annotate.compare-read.spec.ts,这里只测 store 把它们接到
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
import { slotText } from '../src/render/selSnapshot'
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

function annRead(extraBoxes: ReturnType<typeof box>[] = []): AnnRead {
  return {
    state: {
      machine: 'pc', data_fingerprint: null,
      features: [{ id: 'f_plat', name: '站上新平台' }, { id: 'f_step', name: '阶跃' }, { id: 'f_other', name: '别的' }],
      patterns: [{ name: 'p' }],
      charts: [{
        symbol: 'AAA',
        boxes: [box('b-step', 'f_step', 10, 11), box('b-other', 'f_other', 10, 11), ...extraBoxes],
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

async function setup(extraBoxes: ReturnType<typeof box>[] = []) {
  const view = useViewStore()
  const ann = useAnnotationStore()
  const appLink = useAppLinkStore()
  ann.currentPattern = 'p'
  ann.server = annRead(extraBoxes)
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
  const slots = (view: ReturnType<typeof useViewStore>) =>
    [slotText(view.selInfo!.day), slotText(view.selInfo!.stack)]

  it('聚焦样本不改档位:选中的只是这个样本(配对的 event 不算选中),当前日落在样本日', async () => {
    const { view, cmp } = await setup()
    view.setLevel('in_hit')
    expect(cmp.focusSample('sC')).toBe(true)           // 第 15 天只有没成 hit 的 P3
    expect(view.level).toBe('in_hit')
    expect(view.selPath).toEqual([{ kind: 'sample', sampleId: 'sC' }])
    expect([view.selectedInstanceId, view.focusedHitId]).toEqual([null, null])
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
    expect([view.selInfo!.kind, view.selInfo!.date, view.selInfo!.name]).toEqual(['sample', '2024-02-14', 'b pos'])
    expect(slots(view)).toEqual(['samples 2/3', 'into hits ×2'])
    view.stepPos(1)
    expect(ann.selectedSampleId).toBe('sC')
    expect([slotText(view.selInfo!.day), view.currentDay]).toEqual(['samples 3/3', 15])
    ann.selectSample(null)
    view.stepPos(1)                                      // 已是最后一个
    expect(ann.selectedSampleId).toBeNull()
    view.stepPos(-1)
    expect(ann.selectedSampleId).toBe('sB')
  })

  it('样本日在场的 hit:点样本时哪一次都不算选中;↓ 进去先落配对那次,↑ / ↓ 走它们,竖线不动;顺序和 diagnose 卡片一样', async () => {
    const { view, cmp } = await setup()
    cmp.focusSample('sA')                                // 配对的是 h1(子框阶跃到 11)
    expect(view.focusedHitId).toBeNull()
    expect(slots(view)).toEqual(['samples 1/3', 'into hits ×2'])
    expect(view.selInfo!.hits).toEqual({ head: '×2', lines: ['step→2024-02-12', 'step→2024-02-11'] })
    const read = cmp.sampleReads.get('sA')!
    expect(cmp.stackCards(read.pairing, 'plateau').map(c => c.hitIds)).toEqual([['h1'], ['h0']])
    view.stepStack(1)
    expect([view.focusedHitId, view.currentDay, slotText(view.selInfo!.stack)]).toEqual(['h1', 13, 'hits 1/2'])
    cmp.focusSample('sA')                                // 已经停在这个样本里面:不动
    expect(view.focusedHitId).toBe('h1')
    view.stepStack(1)
    expect([view.focusedHitId, view.currentDay]).toEqual(['h0', 13])
    cmp.pickCard('sA', P1.instance_id)                   // 点 diagnose 里 P1 那块:跳回 h1
    expect(view.focusedHitId).toBe('h1')
    expect(view.selPath).toEqual([{ kind: 'sample', sampleId: 'sA' }, { kind: 'hit', hitId: 'h1', day: 13 }])
    cmp.pickCard('sA', P3.instance_id)                   // 不在 hits 组里的块:只选中那个 event(仍属于这个样本),竖线不动
    expect([view.selectedInstanceId, view.focusedHitId, view.currentDay]).toEqual([P3.instance_id, null, 13])
    expect(view.selPath[0]).toEqual({ kind: 'sample', sampleId: 'sA' })
    expect(slots(view)).toEqual([null, null])
  })

  it('聚焦样本:画细框的只有配对的那一次,亮出来的是它的组成;在场的别的几次要 ↓ 进去才看', async () => {
    const { view, cmp } = await setup()
    cmp.focusSample('sA')                                // 配对的是 h1(子框阶跃到 11)
    expect([...view.candidateHitIds]).toEqual(['h1'])
    expect([...view.highlightedEventIds].sort()).toEqual([P1.instance_id, S11.instance_id, T13.instance_id].sort())
    expect(view.focusedHitId).toBeNull()                 // 细框不等于选中
    cmp.focusSample('sB')                                // 同一天的另一个样本配对的是 h0
    expect([...view.candidateHitIds]).toEqual(['h0'])
    expect([...view.highlightedEventIds].sort()).toEqual([P0.instance_id, S10.instance_id, T13.instance_id].sort())
    cmp.focusSample('sC')                                // 样本日没有在场的 hit:没有细框,也没有亮着的组成
    expect([view.candidateHitIds.size, view.highlightedEventIds.size]).toEqual([0, 0])
  })

  it('点框:选中的是这个框,当前日落在框终点;← / → 换到旁边的框,标注那边选中的框一并换成它', async () => {
    const { view, ann, cmp } = await setup()
    expect(cmp.focusBox('b-step')).toBe(true)
    expect(view.selPath).toEqual([{ kind: 'box', boxId: 'b-step' }])
    expect([view.selInfo!.kind, view.selInfo!.node, view.selInfo!.date, view.selInfo!.name])
      .toEqual(['box', 'step', '2024-02-11→2024-02-12', '阶跃'])
    expect(slots(view)).toEqual(['boxes 2/2', null])     // 框终点那天没有在场的 hit:↑ / ↓ 不适用
    expect(view.currentDay).toBe(11)
    view.stepPos(-1)
    expect(view.selPath).toEqual([{ kind: 'box', boxId: 'b-other' }])
    expect(ann.selectedBoxId).toBe('b-other')
  })

  it('亲手再点一次样本 / 框(reset):停在它里面的某一次时回到只选中它自己;不带 reset(按键走到、标注那边跟过来)时不动', async () => {
    // 多放一个对到 plateau 的框,终点在第 13 天:那天在场两次 hit,能从框进到其中一次
    const { view, cmp } = await setup([box('b-plat', 'f_plat', 0, 13)])
    const sA = { kind: 'sample', sampleId: 'sA' }, bPlat = { kind: 'box', boxId: 'b-plat' }
    cmp.focusSample('sA')
    view.stepStack(1)
    expect(view.selPath).toEqual([sA, { kind: 'hit', hitId: 'h1', day: 13 }])
    cmp.focusSample('sA')
    expect(view.selPath).toHaveLength(2)
    cmp.focusSample('sA', { reset: true })
    expect(view.selPath).toEqual([sA])
    expect(view.focusedHitId).toBeNull()

    cmp.focusBox('b-plat')
    expect(slots(view)[1]).toBe('into hits ×2')
    view.stepStack(1)
    expect(view.selPath.map(s => s.kind)).toEqual(['box', 'hit'])
    const inside = [...view.selPath]
    cmp.focusBox('b-plat')
    expect(view.selPath).toEqual(inside)
    cmp.focusBox('b-plat', { reset: true })
    expect(view.selPath).toEqual([bPlat])
    expect(view.focusedHitId).toBeNull()
  })

  it('选中的框 / 样本被删掉:图上的选中清空,聚焦样本作废', async () => {
    const { view, ann, cmp } = await setup()
    cmp.focusBox('b-step')
    await nextTick()
    ann.deleteBox('b-step')
    await nextTick()
    expect(view.selPath).toEqual([])
    expect(cmp.focusedSampleId).toBeNull()

    cmp.focusSample('sC')
    await nextTick()
    expect(cmp.focusedSampleId).toBe('sC')
    ann.deleteSample('sC')
    await nextTick()
    expect(view.selPath).toEqual([])
    expect(cmp.focusedSampleId).toBeNull()
  })

  it('选着样本时改了别的东西(别的框、别的样本)、或标注正在重读:选中不清', async () => {
    const { view, ann, cmp } = await setup()
    const sC = [{ kind: 'sample', sampleId: 'sC' }]
    cmp.focusSample('sC')
    await nextTick()
    ann.setBoxNote('b-other', '量不够')                  // 改别的框
    await nextTick()
    expect([view.selPath, cmp.focusedSampleId]).toEqual([sC, 'sC'])
    ann.deleteBox('b-other')                             // 删别的框(它是 sB 的成员,不是 sC 的)
    await nextTick()
    expect([view.selPath, cmp.focusedSampleId]).toEqual([sC, 'sC'])
    ann.deleteSample('sA')                               // 删别的样本
    await nextTick()
    expect([view.selPath, cmp.focusedSampleId]).toEqual([sC, 'sC'])
    ann.server = null                                    // 读结果暂时为空(还没读到 / 正在重读):不算选中的东西没了
    await nextTick()
    expect([view.selPath, cmp.focusedSampleId]).toEqual([sC, 'sC'])
  })

  it('换了标注的当前 pattern:最外一节是样本 / 框 / 反馈的选中清空、聚焦样本作废;选中的是 app 的东西时不动', async () => {
    const { view, ann, cmp } = await setup()
    // 另一个 pattern q 也对到同一个 app:换 pattern 不离开 compare、app 的产物也不换,变的只有「按哪个 pattern 看标注」
    const appLink = useAppLinkStore()
    appLink.mappings = [...(appLink.mappings ?? []), { app: 'app1', pattern: 'q', problem: null, features: {} }]
    /** 换到 q 再换回来,各等一次刷新;返回换过去那一刻的选中与聚焦样本 */
    const swap = async () => {
      ann.currentPattern = 'q'
      await nextTick()
      expect(view.comparing).toBe(true)
      const seen = [[...view.selPath], cmp.focusedSampleId]
      ann.currentPattern = 'p'
      await nextTick()
      expect(cmp.ready).toBe(true)
      return seen
    }
    cmp.focusSample('sC')
    await nextTick()
    expect(cmp.focusedSampleId).toBe('sC')
    expect(await swap()).toEqual([[], null])

    cmp.focusSample('sA')
    view.stepStack(1)                                    // 停在样本里面的那次 hit:最外一节仍是样本
    await nextTick()
    expect(view.selPath.map(s => s.kind)).toEqual(['sample', 'hit'])
    expect(await swap()).toEqual([[], null])

    cmp.focusBox('b-step')
    await nextTick()
    expect(await swap()).toEqual([[], null])

    view.setPath([{ kind: 'feedback', id: 'f-1' }])
    await nextTick()
    expect(view.selPath).toHaveLength(1)
    expect(await swap()).toEqual([[], null])

    view.clickBuyDay('hits@0', 13)                       // app 的一族的这一天:不按 pattern 分
    await nextTick()
    const path = [...view.selPath]
    expect(path.map(s => s.kind)).toEqual(['hit_family', 'buy'])
    expect(await swap()).toEqual([path, null])
  })

  it('子框只认对到配对 node 的子 node 的框:对到 step 的按子框挑 hit,对到别的 node 的不算子框', async () => {
    const { cmp } = await setup()
    expect(cmp.sampleReads.get('sA')?.pairing.hitId).toBe('h1')   // 子框阶跃到 11 → S11 那次
    expect(cmp.sampleReads.get('sB')?.pairing.hitId).toBe('h0')   // 不当子框 → 当天第一个 hit
  })

  it('选中换走(Esc、点了 app 的格)后聚焦样本作废', async () => {
    const { view, cmp } = await setup()
    cmp.focusSample('sC')
    await nextTick()                                     // 聚焦和 Esc 是两次操作,中间隔着一次刷新
    view.clearFocus()
    await nextTick()
    expect(cmp.focusedSampleId).toBeNull()
  })
})

describe('view store · 结果换了(重跑)', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  const ALL = [S10, S11, T13, T15, P0, P1, P3]
  const HIT_ID = new Map([[P0, 'h0'], [P1, 'h1'], [P3, 'h3']])
  /** 一次重跑的产物:这几个 plateau 成了 hit(第 13 天的 P0、P1,第 15 天的 P3),drop 里的 event 这次没生成 */
  const runOf = (plateaus: EventDict[], drop: EventDict[] = []): LinkedRun => ({
    ...RUN,
    analysis: { events: ALL.filter(x => !drop.includes(x)), hits: plateaus.map(p => hit(HIT_ID.get(p)!, p)) } as any,
  })
  const FAM = { kind: 'hit_family', familyKey: 'hits@0' }
  const buy = (day: number) => ({ kind: 'buy', day })
  const full = () => runOf([P0, P1, P3])

  async function at(run: LinkedRun) {
    const { view } = await setup()
    view.setLinkedRun(run)
    await nextTick()
    return view
  }
  async function rerun(view: ReturnType<typeof useViewStore>, run: LinkedRun | null) {
    view.setLinkedRun(run)
    await nextTick()
  }

  it('路径上的那次 hit 没了、那天还有别的 hit:退到那一天', async () => {
    const view = await at(full())
    view.clickBuyDay('hits@0', 13)
    view.stepStack(1)
    view.stepStack(1)
    expect(view.selPath).toEqual([FAM, buy(13), { kind: 'hit', hitId: 'h1', day: 13 }])
    await rerun(view, runOf([P0, P3]))
    expect(view.selPath).toEqual([FAM, buy(13)])
    expect([view.focusedHitId, view.currentDay]).toEqual(['h0', 13])   // 那天只剩一次:这一天就是那次 hit
  })

  it('那次 hit 没了、那天也没有别的 hit:退到那一族;一族的 hit 全没了:清空', async () => {
    const view = await at(full())
    view.clickBuyDay('hits@0', 13)
    view.stepStack(1)
    expect(view.selPath).toHaveLength(3)
    await rerun(view, runOf([P3]))
    expect(view.selPath).toEqual([FAM])
    await rerun(view, runOf([]))
    expect(view.selPath).toEqual([])
    expect([view.focusedHitId, view.currentDay]).toEqual([null, null])
  })

  it('选中的 event 没了:退到它那条 band;还在的不动', async () => {
    const view = await at(full())
    view.setLevel('detected')
    view.focusEvent(S11.instance_id)
    const path = [{ kind: 'node', band: 'step' }, { kind: 'event', instanceId: S11.instance_id }]
    expect(view.selPath).toEqual(path)
    await rerun(view, runOf([P0], [P3, T15]))                 // 别的东西变了,S11 还在
    expect(view.selPath).toEqual(path)
    await rerun(view, runOf([P0], [S11, P1]))
    expect(view.selPath).toEqual([{ kind: 'node', band: 'step' }])
    expect(view.selectedInstanceId).toBeNull()
  })

  it('结果还没到(空)时不动;同样的结果再来一次也不动', async () => {
    const view = await at(full())
    view.clickBuyDay('hits@0', 13)
    view.stepStack(1)
    const path = [...view.selPath]
    expect(path).toHaveLength(3)
    await rerun(view, null)
    expect(view.selPath).toEqual(path)
    await rerun(view, full())
    expect(view.selPath).toEqual(path)
  })
})
