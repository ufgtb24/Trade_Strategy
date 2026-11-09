// 页面引导里随反馈做的部分(spec 6.14 G3、G4):
// - 特征定义格写之前就提示(灰字占位 fixed once written,悬停写意思变了怎么办);
// - pattern 定义框悬停「定级照这句定」;样本的 judgment 与 delete 悬停写分流口诀;
// - 删样本:有只服务它的框才展开一行问(yes 一起删 / no 只删样本 / cancel 不删),没有就直接删;
// - 提示条 deleted … undo:删框、删样本、删反馈后出现,点 undo 放回并消失。
// 后端换成内存里的假实现;别的读请求一律挂起。
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import type { AnnOp, AnnRead } from '../src/annotate/model'

const fake = vi.hoisted(() => ({ read: null as any, batches: [] as any[] }))

vi.mock('../src/api', async (orig) => {
  const m: Record<string, any> = await orig()
  const model = await vi.importActual<typeof import('../src/annotate/model')>('../src/annotate/model')
  const out: Record<string, any> = Object.fromEntries(Object.entries(m).map(([k, v]) =>
    [k, typeof v === 'function' && /^[a-z]/.test(k) ? vi.fn(() => new Promise(() => {})) : v]))
  return {
    ...out,
    getAnnotations: async () => structuredClone(fake.read),
    postAnnotationBatch: async (ops: AnnOp[]) => {
      fake.batches.push(structuredClone(ops))
      const next = model.applyOps(fake.read, ops)
      const revs = structuredClone(fake.read.revs)
      ops.forEach((op, i) => { revs[op.kind][op.id] = `pc-batch-${fake.batches.length}#${i}` })
      fake.read = { ...next, revs }
      return { file: 'x.json', ...structuredClone(fake.read) }
    },
  }
})

import AnnotationNotices from '../src/components/AnnotationNotices.vue'
import DefinitionField from '../src/components/DefinitionField.vue'
import PatternPanel from '../src/components/PatternPanel.vue'
import SamplePanel from '../src/components/SamplePanel.vue'
import { useAnnotationStore } from '../src/stores/annotation'

const TRIAGE = 'visible that day it should not buy → neg; not this pattern at all → move to unsorted or another pattern; '
  + 'bad data → delete'

// AAA:s-pc-5 的成员 b1、b2(b2 挂在 b1 上,两个都只服务它)、b3(也是 s-pc-6 的成员);s-pc-6 只有共用的 b3
function annRead(): AnnRead {
  return {
    state: {
      machine: 'pc', data_fingerprint: null,
      features: [{ id: 'w-pc-9', name: '横盘' }, { id: 'w-pc-8', name: '放量' }],
      patterns: [{ name: 'p', definition: '台阶后的平台' }],
      charts: [{ symbol: 'AAA',
        boxes: [{ id: 'b-pc-1', feature: 'w-pc-9', start: '2025-01-06', end: '2025-01-10' },
                { id: 'b-pc-2', feature: null, start: '2025-01-07', end: '2025-01-09', attach: 'b-pc-1' },
                { id: 'b-pc-3', feature: null, start: '2025-01-13', end: '2025-01-17' }],
        samples: [{ id: 's-pc-5', date: '2025-02-10', pattern: 'p', judgment: 'pos', members: ['b-pc-1', 'b-pc-2', 'b-pc-3'] },
                  { id: 's-pc-6', date: '2025-02-12', pattern: 'p', judgment: 'pos', members: ['b-pc-3'] }],
        feedback: [{ id: 'f-pc-7', pattern: 'p', app_id: 'app1', app_ver: 'v0', start: '2025-01-20', end: '2025-01-24',
                     target: 'range', source: 'picked', answer: 'neg', note: '追高' }] }],
    },
    conflicts: [], unsynced: [], violations: [],
    fingerprint: { local: 'fp', local_error: null, recorded: [], consistent: true }, merges: [],
    revs: { feature: {}, pattern: {}, box: {}, sample: {}, feedback: {} }, next_seq: 10, ignored_files: [],
    membership: { gap: 20, near: 40 }, match: { pos: 3, neg: 1, sub: 2 },
  }
}

const STUBS = { MemberChain: true, PatternPicker: true, SampleDiagnose: true, BoxName: true }

async function setup() {
  const ann = useAnnotationStore()
  await ann.load()
  ann.setCurrentPattern('p')
  return ann
}

const sampleIds = (ann: ReturnType<typeof useAnnotationStore>) => ann.state!.charts[0].samples.map(x => x.id)
const boxIds = (ann: ReturnType<typeof useAnnotationStore>) => ann.state!.charts[0].boxes.map(x => x.id)

beforeEach(() => {
  setActivePinia(createPinia())
  fake.read = annRead()
  fake.batches = []
  localStorage.clear()
})

describe('悬停与占位提示', () => {
  it('特征定义格:写之前就有灰字占位 fixed once written,悬停写意思变了另起一个词', async () => {
    const ann = await setup()
    const w = mount(DefinitionField, { props: { feature: ann.state!.features[1] } })
    const area = w.get('[data-testid="definition-input"]')
    expect(area.attributes('placeholder')).toBe('fixed once written')
    expect(area.attributes('title')).toBe('fixed once written; if the meaning changes, start a new feature')
  })

  it('pattern 定义框:标签与框都悬停「定级照这句定」', async () => {
    await setup()
    const w = mount(PatternPanel, { global: { stubs: { CountButton: true, CountParts: true, FeatureBlockView: true,
                                                     PatternPicker: true, SampleCard: true } } })
    const tip = 'one sentence: what this pattern should catch; grading follows this sentence'
    expect(w.get('[data-testid="pattern-definition"]').attributes('title')).toBe(tip)
    expect(w.findAll('.ann-k').find(x => x.text() === 'definition')!.attributes('title')).toBe(tip)
  })

  it('样本页:judgment 标签与 delete 的悬停都带分流口诀(并进原来的说明,一句、小写)', async () => {
    const ann = await setup()
    ann.selectSample('s-pc-5')
    const w = mount(SamplePanel, { global: { stubs: STUBS } })
    const judgment = w.findAll('.ann-k').find(x => x.text() === 'judgment')!.attributes('title')!
    expect(judgment.startsWith("pos: the pattern's app should buy on this date; ")).toBe(true)
    expect(judgment.endsWith(TRIAGE)).toBe(true)
    const del = w.get('[data-testid="sample-delete"]').attributes('title')!
    expect(del).toBe(`delete this sample (asks first if some boxes serve only it); ${TRIAGE}`)
    for (const t of [judgment, del]) expect(t).toBe(t.toLowerCase())
  })
})

describe('删样本的提示一行', () => {
  async function panel(sampleId: string) {
    const ann = await setup()
    ann.selectSample(sampleId)
    const w = mount(SamplePanel, { global: { stubs: STUBS } })
    return { ann, w }
  }

  it('没有只服务它的框:点 delete 直接删,不展开提示', async () => {
    const { ann, w } = await panel('s-pc-6')
    await w.get('[data-testid="sample-delete"]').trigger('click')
    expect(w.find('[data-testid="sample-delete-ask"]').exists()).toBe(false)
    expect(sampleIds(ann)).toEqual(['s-pc-5'])
    await ann.flushed()
    expect(fake.batches).toEqual([[{ kind: 'sample', id: 's-pc-6', base: null, value: null }]])
  })

  it('有 2 个:展开一行和三个按钮;cancel 什么都不删、收起', async () => {
    const { ann, w } = await panel('s-pc-5')
    await w.get('[data-testid="sample-delete"]').trigger('click')
    const ask = w.get('[data-testid="sample-delete-ask"]')
    expect(ask.attributes('data-count')).toBe('2')
    expect(ask.text()).toContain('also delete 2 boxes only it uses?')
    for (const b of ['yes', 'no', 'cancel']) expect(w.get(`[data-testid="sample-delete-${b}"]`).text()).toBe(b)
    expect(sampleIds(ann)).toEqual(['s-pc-5', 's-pc-6'])        // 问的时候还没删
    await w.get('[data-testid="sample-delete-cancel"]').trigger('click')
    expect(w.find('[data-testid="sample-delete-ask"]').exists()).toBe(false)
    await ann.flushed()
    expect(fake.batches).toEqual([])
  })

  it('yes:一批里删样本和只服务它的两个框(两个框之间不清 attach),共用的框留着', async () => {
    const { ann, w } = await panel('s-pc-5')
    await w.get('[data-testid="sample-delete"]').trigger('click')
    await w.get('[data-testid="sample-delete-yes"]').trigger('click')
    expect(sampleIds(ann)).toEqual(['s-pc-6'])
    expect(boxIds(ann)).toEqual(['b-pc-3'])
    await ann.flushed()
    expect(fake.batches).toHaveLength(1)
    expect(fake.batches[0].map((o: AnnOp) => `${o.kind}:${o.id}:${o.value === null}`))
      .toEqual(['sample:s-pc-5:true', 'box:b-pc-1:true', 'box:b-pc-2:true'])
  })

  it('展开期间只服务它的框变成 0:收起;之后又有只服务它的框也不自己冒出来', async () => {
    const { ann, w } = await panel('s-pc-5')
    await w.get('[data-testid="sample-delete"]').trigger('click')
    expect(w.find('[data-testid="sample-delete-ask"]').exists()).toBe(true)
    ann.toggleMember('s-pc-6', 'b-pc-1')                    // 别的样本收进 b1、b2:不再只服务 s-pc-5
    ann.toggleMember('s-pc-6', 'b-pc-2')
    await flushPromises()
    expect(w.find('[data-testid="sample-delete-ask"]').exists()).toBe(false)
    ann.toggleMember('s-pc-6', 'b-pc-1')                    // 又只服务它了:提示行不自己出现
    await flushPromises()
    expect(w.find('[data-testid="sample-delete-ask"]').exists()).toBe(false)
    await ann.flushed()
    expect(sampleIds(ann)).toEqual(['s-pc-5', 's-pc-6'])
  })

  it('no:只删样本,框都留在图上', async () => {
    const { ann, w } = await panel('s-pc-5')
    await w.get('[data-testid="sample-delete"]').trigger('click')
    await w.get('[data-testid="sample-delete-no"]').trigger('click')
    expect(sampleIds(ann)).toEqual(['s-pc-6'])
    expect(boxIds(ann)).toEqual(['b-pc-1', 'b-pc-2', 'b-pc-3'])
  })
})

describe('提示条 deleted … undo', () => {
  it('删样本(连同 2 个框)后出现一行,点 undo 放回、这一行消失', async () => {
    const ann = await setup()
    const w = mount(AnnotationNotices)
    expect(w.find('[data-testid="notice-undo"]').exists()).toBe(false)
    ann.deleteSample('s-pc-5', ['b-pc-1', 'b-pc-2'])
    await flushPromises()
    const row = w.get('[data-testid="notice-undo"]')
    expect(row.attributes('data-kind')).toBe('sample')
    expect(row.text()).toContain('deleted')
    expect(row.text()).toContain('AAA ▲ 2025-02-10')
    expect(row.text()).toContain('+2 boxes')
    await ann.flushed()
    await w.get('[data-testid="notice-undo-btn"]').trigger('click')
    expect(w.find('[data-testid="notice-undo"]').exists()).toBe(false)
    await ann.flushed()
    expect(sampleIds(ann)).toEqual(['s-pc-5', 's-pc-6'])
    expect(boxIds(ann)).toEqual(['b-pc-1', 'b-pc-2', 'b-pc-3'])
    expect(ann.state!.charts[0].boxes[1].attach).toBe('b-pc-1')
  })

  it('ok:这一行消失,放弃撤销(之后什么都撤不回)', async () => {
    const ann = await setup()
    const w = mount(AnnotationNotices)
    ann.deleteBox('b-pc-3')
    await flushPromises()
    const ok = w.get('[data-testid="notice-undo-ok"]')
    expect(ok.text()).toBe('ok')
    expect(ok.attributes('title')).toBe('hide; this delete can no longer be undone')
    await ok.trigger('click')
    expect(w.find('[data-testid="notice-undo"]').exists()).toBe(false)
    expect(ann.lastDeletion).toBeNull()
    await ann.flushed()
    ann.undoDeletion()
    await ann.flushed()
    expect(fake.batches).toHaveLength(1)                    // 只有删除那一批
    expect(boxIds(ann)).toEqual(['b-pc-1', 'b-pc-2'])
  })

  it('删框写特征名与日期,删反馈写股票与日期;再删一次换成新的', async () => {
    const ann = await setup()
    const w = mount(AnnotationNotices)
    ann.deleteBox('b-pc-1')
    await flushPromises()
    let row = w.get('[data-testid="notice-undo"]')
    expect(row.attributes('data-kind')).toBe('box')
    expect(row.get('.biz').text()).toBe('横盘')
    expect(row.text()).toContain('AAA 2025-01-06 – 2025-01-10')
    ann.deleteFeedback('f-pc-7')
    await flushPromises()
    row = w.get('[data-testid="notice-undo"]')
    expect(row.attributes('data-kind')).toBe('feedback')
    expect(row.text()).toContain('AAA 2025-01-20 – 2025-01-24')
    expect(row.find('.biz').exists()).toBe(false)
  })
})
