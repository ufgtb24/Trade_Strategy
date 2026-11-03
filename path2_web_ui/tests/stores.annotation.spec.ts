// 标注 store:每个动作送出的那一批操作(base 取最新的 revs、新编号带机器名)、属性回到 null 存的是「没有键」、
// 改名一处生效、合并先预览再改、拆回恢复原样、删框连带样本成员、保存被拒时退回、冲突只提示一次。
// 后端换成内存里的假实现:收到一批就套到状态上,给每条操作记一个引用,和真后端的 revs 一样。
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { applyOps, weekdaysCovering, type AnnOp, type AnnRead, type AnnState } from '../src/annotate/model'

const fake = vi.hoisted(() => ({
  read: null as any,
  batches: [] as any[],
  reject: null as any,
  n: 0,
}))

vi.mock('../src/api', async () => {
  const model = await vi.importActual<typeof import('../src/annotate/model')>('../src/annotate/model')
  class AnnotationSaveError extends Error {
    constructor(message: string, readonly status: number, readonly reasons: any[]) { super(message) }
  }
  return {
    AnnotationSaveError,
    getAnnotations: async () => structuredClone(fake.read),
    postAnnotationBatch: async (ops: AnnOp[]) => {
      fake.batches.push(structuredClone(ops))
      if (fake.reject) throw new AnnotationSaveError('rejected', 400, fake.reject)
      const stem = `pc-batch-${++fake.n}`
      const next = model.applyOps(fake.read, ops)
      const revs = structuredClone(fake.read.revs)
      ops.forEach((op, i) => { revs[op.kind][op.id] = `${stem}#${i}` })
      // 真后端从文件里认出合并;这里只模拟「词放回词表后,那条合并不再列出」
      const merges = (fake.read.merges ?? []).filter((m: any) => !next.state.features.some((f: any) => f.id === m.feature.id))
      fake.read = { ...next, revs, merges }
      return { file: `${stem}.json`, ...structuredClone(fake.read) }
    },
  }
})

import { useAnnotationStore } from '../src/stores/annotation'

function emptyRead(state: Partial<AnnState> = {}): AnnRead {
  return {
    state: { machine: 'pc', data_fingerprint: null, features: [], patterns: [], charts: [], ...state },
    conflicts: [], unsynced: [], violations: [],
    fingerprint: { local: 'fp', local_error: null, recorded: [], consistent: true }, merges: [],
    revs: { feature: {}, pattern: {}, box: {}, sample: {} }, next_seq: 1, ignored_files: [],
    membership: { gap: 20, near: 40 },
  }
}

async function ready(read: AnnRead = emptyRead()) {
  fake.read = read
  const s = useAnnotationStore()
  await s.load()
  return s
}

beforeEach(() => {
  setActivePinia(createPinia())
  fake.batches = []
  fake.reject = null
  fake.n = 0
  localStorage.clear()
})

describe('画框与起名', () => {
  it('拖框后马上起一个新名字:两批依次送,第二批的 base 是第一批刚写的那次修改', async () => {
    const s = await ready()
    const id = s.createBox('AAA', '2025-01-06', '2025-01-10', null)
    expect(id).toBe('b-pc-1')
    expect(s.selectedBoxId).toBe('b-pc-1')
    s.setBoxFeature(id!, { name: ' 横盘 ' })
    // 还没保存完就已经显示出来
    expect(s.state!.charts[0].boxes[0].feature).toBe('w-pc-2')
    expect(s.nameOf('w-pc-2')).toBe('横盘')
    await s.flushed()
    expect(fake.batches).toHaveLength(2)
    expect(fake.batches[0]).toEqual([{ kind: 'box', id: 'b-pc-1', base: null,
      value: { id: 'b-pc-1', symbol: 'AAA', feature: null, start: '2025-01-06', end: '2025-01-10' } }])
    expect(fake.batches[1]).toEqual([
      { kind: 'feature', id: 'w-pc-2', base: null, value: { id: 'w-pc-2', name: '横盘' } },
      { kind: 'box', id: 'b-pc-1', base: 'pc-batch-1#0',
        value: { id: 'b-pc-1', symbol: 'AAA', feature: 'w-pc-2', start: '2025-01-06', end: '2025-01-10' } },
    ])
  })

  it('输入的名字和已有的词相同:用那个词,不新起', async () => {
    const s = await ready(emptyRead({ features: [{ id: 'w-upc-1', name: '横盘' }],
      charts: [{ symbol: 'AAA', samples: [], boxes: [{ id: 'b-upc-2', feature: null, start: '2025-01-06', end: '2025-01-10' }] }] }))
    s.setBoxFeature('b-upc-2', { name: '横盘' })
    await s.flushed()
    expect(fake.batches[0].map((o: AnnOp) => o.kind)).toEqual(['box'])
    expect(fake.batches[0][0].value.feature).toBe('w-upc-1')
  })

  it('在特征轨上拖出的框直接带这个特征,不要求起名', async () => {
    const s = await ready(emptyRead({ features: [{ id: 'w-pc-1', name: '横盘' }] }))
    s.createBox('AAA', '2025-01-06', '2025-01-10', 'w-pc-1')
    await s.flushed()
    expect(fake.batches[0][0].value.feature).toBe('w-pc-1')
  })
})

describe('属性三态', () => {
  it('true → 再点一下 → null:存进去的是没有这个键,不是 false', async () => {
    const s = await ready(emptyRead({ features: [{ id: 'w-pc-1', name: '横盘' }, { id: 'w-pc-2', name: '放量' }],
      charts: [{ symbol: 'AAA', samples: [], boxes: [{ id: 'b-pc-3', feature: 'w-pc-1', start: '2025-01-06', end: '2025-01-10' }] }] }))
    s.setAttr('b-pc-3', 'w-pc-2', true)
    s.setAttr('b-pc-3', 'w-pc-2', true)
    await s.flushed()
    expect(fake.batches[0][0].value.attrs).toEqual({ 'w-pc-2': true })
    expect(fake.batches[1][0].value).not.toHaveProperty('attrs')
    expect(fake.read.state.charts[0].boxes[0]).not.toHaveProperty('attrs')
  })

  it('挂一条新属性:新词进词表,先判 true', async () => {
    const s = await ready(emptyRead({ features: [{ id: 'w-pc-1', name: '横盘' }], next_seq: 3,
      charts: [{ symbol: 'AAA', samples: [], boxes: [{ id: 'b-pc-2', feature: 'w-pc-1', start: '2025-01-06', end: '2025-01-10' }] }] } as any))
    fake.read.next_seq = 3
    await s.load()
    s.addAttr('b-pc-2', '突破过好几个峰')
    await s.flushed()
    expect(fake.batches[0]).toEqual([
      { kind: 'feature', id: 'w-pc-3', base: null, value: { id: 'w-pc-3', name: '突破过好几个峰' } },
      { kind: 'box', id: 'b-pc-2', base: null,
        value: { id: 'b-pc-2', symbol: 'AAA', feature: 'w-pc-1', start: '2025-01-06', end: '2025-01-10', attrs: { 'w-pc-3': true } } },
    ])
  })
})

describe('词表', () => {
  const base = () => emptyRead({
    features: [{ id: 'w-pc-1', name: '放量' }, { id: 'w-pc-2', name: '量大', definition: '比前一段量大' }],
    charts: [
      { symbol: 'AAA', samples: [], boxes: [{ id: 'b-pc-3', feature: 'w-pc-2', start: '2025-01-06', end: '2025-01-10' }] },
      { symbol: 'BBB', samples: [], boxes: [{ id: 'b-pc-4', feature: 'w-pc-1', start: '2025-01-06', end: '2025-01-10', attrs: { 'w-pc-2': true } }] },
    ],
  })

  it('改名只改词表一处;和别的词重名不改', async () => {
    const s = await ready(base())
    expect(s.renameFeature('w-pc-1', '量大')).toBe('name_taken')
    expect(s.renameFeature('w-pc-1', '放巨量')).toBe('ok')
    await s.flushed()
    expect(fake.batches).toEqual([[{ kind: 'feature', id: 'w-pc-1', base: null, value: { id: 'w-pc-1', name: '放巨量' } }]])
    expect(s.nameOf('w-pc-1')).toBe('放巨量')
  })

  it('定义只在还空着时写得进去', async () => {
    const s = await ready(base())
    s.setDefinition('w-pc-2', '改掉')
    s.setDefinition('w-pc-1', '量是前 20 根均量的两倍以上')
    await s.flushed()
    expect(fake.batches).toEqual([[{ kind: 'feature', id: 'w-pc-1', base: null,
      value: { id: 'w-pc-1', name: '放量', definition: '量是前 20 根均量的两倍以上' } }]])
  })

  it('合并:先预览波及几个框;送出的一批改写涉及的框、删掉被并的词', async () => {
    const s = await ready(base())
    const plan = s.previewMerge('w-pc-2', 'w-pc-1')!
    expect([plan.box, plan.attr]).toEqual([1, 1])
    s.applyMerge('w-pc-2', 'w-pc-1')
    await s.flushed()
    const merged = fake.batches[0]
    expect(merged.map((o: AnnOp) => [o.kind, o.id, o.value === null])).toEqual([
      ['box', 'b-pc-3', false], ['box', 'b-pc-4', false], ['feature', 'w-pc-2', true]])
    expect(merged[0].value.feature).toBe('w-pc-1')
    expect(merged[1].value.attrs).toEqual({ 'w-pc-1': true })      // 属性「量大」挪成「放量」
    expect(fake.read.state.features.map((f: any) => f.id)).toEqual(['w-pc-1'])
  })

  it('拆回:按后端认出的合并,词用原编号放回(base 取它被删的那次),框改回合并前;之后不再列出', async () => {
    const before = base()
    const r = base()
    r.state.features = [{ id: 'w-pc-1', name: '放量' }]
    r.state.charts[0].boxes[0] = { ...r.state.charts[0].boxes[0], feature: 'w-pc-1' }
    r.revs = { feature: { 'w-pc-1': 'b0#0', 'w-pc-2': 'b1#1' }, pattern: {}, box: { 'b-pc-3': 'b1#0' }, sample: {} }
    r.merges = [{ ref: 'b1#1', machine: 'pc', ts: 't', feature: { id: 'w-pc-2', name: '量大', definition: '比前一段量大' },
      into: 'w-pc-1', boxes: [{ id: 'b-pc-3',
        before: { ...before.state.charts[0].boxes[0], symbol: 'AAA' }, after: { ...r.state.charts[0].boxes[0], symbol: 'AAA' } }] }]
    const s = await ready(r)
    expect(s.merges.map(m => [m.from.name, m.into, m.box, m.attr])).toEqual([['量大', 'w-pc-1', 1, 0]])
    s.unmerge(0)
    await s.flushed()
    expect(fake.batches[0]).toEqual([
      { kind: 'feature', id: 'w-pc-2', base: 'b1#1', value: { id: 'w-pc-2', name: '量大', definition: '比前一段量大' } },
      { kind: 'box', id: 'b-pc-3', base: 'b1#0',
        value: { id: 'b-pc-3', symbol: 'AAA', feature: 'w-pc-2', start: '2025-01-06', end: '2025-01-10' } },
    ])
    expect(fake.read.state.charts).toEqual(before.state.charts)
    expect(s.merges).toEqual([])
  })
})

describe('删框与保存失败', () => {
  it('删框:同一批把它从样本的成员里拿掉,挂在它上面的 attach 一并拿掉', async () => {
    const s = await ready(emptyRead({ charts: [{ symbol: 'AAA',
      boxes: [{ id: 'b-pc-1', feature: null, start: '2025-01-06', end: '2025-01-10' },
              { id: 'b-pc-2', feature: null, start: '2025-01-09', end: '2025-01-14', attach: 'b-pc-1' }],
      samples: [{ id: 's-pc-3', date: '2025-01-15', pattern: null, judgment: 'pos', members: ['b-pc-1', 'b-pc-2'] }] }] }))
    s.selectBox('b-pc-1')
    s.deleteBox('b-pc-1')
    expect(s.selectedBoxId).toBeNull()
    await s.flushed()
    const ops = fake.batches[0]
    expect(ops.map((o: AnnOp) => [o.kind, o.id, o.value === null])).toEqual([
      ['box', 'b-pc-1', true], ['sample', 's-pc-3', false], ['box', 'b-pc-2', false]])
    expect(ops[1].value.members).toEqual(['b-pc-2'])
    expect(ops[2].value).not.toHaveProperty('attach')
  })

  it('保存被拒:显示退回后端的状态,原因留给界面显示', async () => {
    const s = await ready(emptyRead({ charts: [{ symbol: 'AAA', samples: [],
      boxes: [{ id: 'b-pc-1', feature: null, start: '2025-01-06', end: '2025-01-10' }] }] }))
    fake.reject = [{ code: 'box_crosses_sample_date', message: 'x' }]
    s.resizeBox('b-pc-1', '2025-01-06', '2025-01-20')
    expect(s.state!.charts[0].boxes[0].end).toBe('2025-01-20')
    await s.flushed()
    expect(s.state!.charts[0].boxes[0].end).toBe('2025-01-10')
    expect(s.saveError).toEqual([{ code: 'box_crosses_sample_date', message: 'x' }])
  })
})

describe('样本与成员框', () => {
  // AAA 的交易日:2025 年 1~3 月的工作日(1-20、2-17 休市);框 b-pc-1、b-pc-2 在样本日 2-28 之前,b-pc-3 跨过它
  const DAYS = weekdaysCovering([{ start: '2025-01-02', end: '2025-03-31' }])
    .filter(d => !['2025-01-20', '2025-02-17'].includes(d))
  const boxes = () => [
    { id: 'b-pc-1', feature: 'w-pc-9', start: '2025-01-06', end: '2025-01-17' },
    { id: 'b-pc-2', feature: 'w-pc-9', start: '2025-02-03', end: '2025-02-14' },
    { id: 'b-pc-3', feature: 'w-pc-9', start: '2025-02-24', end: '2025-03-05' },
  ]
  async function withChart(extra: Partial<AnnState> = {}) {
    const r = emptyRead({ features: [{ id: 'w-pc-9', name: '横盘' }], charts: [{ symbol: 'AAA', boxes: boxes(), samples: [] }], ...extra })
    r.next_seq = 10
    const s = await ready(r)
    s.setDays('AAA', DAYS)
    return s
  }
  const sampleOps = () => fake.batches.flat().filter((o: any) => o.kind === 'sample')

  it('放样本:归当前 pattern、默认 pos,成员框按推断(跨过样本日的不收);工具切回 box,它成为选中的当前样本', async () => {
    const s = await withChart()
    s.tool = 'point'
    const id = s.placeSample('AAA', '2025-02-28')
    expect(id).toBe('s-pc-10')
    expect(s.tool).toBe('box')
    expect(s.selectedSampleId).toBe(id)
    expect(s.currentSampleId).toBe(id)
    await s.flushed()
    expect(fake.batches).toEqual([[{ kind: 'sample', id: 's-pc-10', base: null, value: {
      id: 's-pc-10', symbol: 'AAA', date: '2025-02-28', pattern: null, judgment: 'pos', members: ['b-pc-1', 'b-pc-2'] } }]])
  })

  it('同一 pattern 同一天已有样本:点下去就是选中它,不新放;别的 pattern 同一天各放各的', async () => {
    const s = await withChart({ patterns: [{ name: 'P' }] })
    const a = s.placeSample('AAA', '2025-02-28')
    await s.flushed()
    s.clearSelection()
    expect(s.placeSample('AAA', '2025-02-28')).toBe(a)
    expect(s.selectedSampleId).toBe(a)
    s.setCurrentPattern('P')
    const b = s.placeSample('AAA', '2025-02-28')
    expect(b).not.toBe(a)
    await s.flushed()
    expect(s.state!.charts[0].samples.map(x => x.pattern)).toEqual([null, 'P'])
  })

  it('当前样本期间新画的框,推断会收的就同一批并进它;跨过样本日的不收', async () => {
    const s = await withChart()
    const id = s.placeSample('AAA', '2025-02-28')!
    await s.flushed()
    const nb = s.createBox('AAA', '2025-02-20', '2025-02-26', null)!
    s.createBox('AAA', '2025-02-21', '2025-03-04', null)
    await s.flushed()
    expect(fake.batches[1].map((o: any) => o.kind)).toEqual(['box', 'sample'])
    expect(fake.batches[2].map((o: any) => o.kind)).toEqual(['box'])
    expect(s.state!.charts[0].samples[0].members).toEqual(['b-pc-1', 'b-pc-2', nb])
    expect(s.currentSampleId).toBe(id)
  })

  it('换掉当前样本(点空白处、选另一个样本)后冻结:之后补画的框不再并进旧样本', async () => {
    const s = await withChart()
    s.placeSample('AAA', '2025-02-28')
    await s.flushed()
    s.clearSelection()
    expect(s.currentSampleId).toBeNull()
    s.createBox('AAA', '2025-02-20', '2025-02-26', null)
    await s.flushed()
    expect(sampleOps()).toHaveLength(1)
    expect(s.state!.charts[0].samples[0].members).toEqual(['b-pc-1', 'b-pc-2'])
  })

  it('选中框不换当前样本;改起止让新框进了推断范围也并进来(连带够得着的旧框不收:只收这期间动过的)', async () => {
    const s = await withChart({ charts: [{ symbol: 'AAA', boxes: boxes().slice(0, 1), samples: [] }] })
    const id = s.placeSample('AAA', '2025-03-31')!
    await s.flushed()
    expect(s.state!.charts[0].samples[0].members).toEqual([])
    const nb = s.createBox('AAA', '2025-01-02', '2025-01-03', null)!
    s.selectBox('b-pc-1')
    expect(s.currentSampleId).toBe(id)
    s.resizeBox(nb, '2025-01-02', '2025-03-14')
    await s.flushed()
    expect(s.state!.charts[0].samples[0].members).toEqual([nb])
  })

  it('手动点进点出:改存下的成员框、记 members_edited;点掉的新框不会被推断收回来;跨过样本日的点不进', async () => {
    const s = await withChart()
    const id = s.placeSample('AAA', '2025-02-28')!
    const nb = s.createBox('AAA', '2025-02-20', '2025-02-26', null)!
    await s.flushed()
    s.toggleMember(id, nb)
    s.toggleMember(id, 'b-pc-1')
    await s.flushed()
    expect(s.state!.charts[0].samples[0]).toMatchObject({ members: ['b-pc-2'], members_edited: true })
    s.resizeBox(nb, '2025-02-19', '2025-02-26')
    await s.flushed()
    expect(s.state!.charts[0].samples[0].members).toEqual(['b-pc-2'])
    const n = fake.batches.length
    s.toggleMember(id, 'b-pc-3')
    await s.flushed()
    expect(fake.batches).toHaveLength(n)
    s.toggleMember(id, 'b-pc-1')
    await s.flushed()
    expect(s.state!.charts[0].samples[0].members).toEqual(['b-pc-1', 'b-pc-2'])
  })

  it('样本页:改 judgment、note、pattern(新名字同一批新建 pattern);删样本后它不再是当前样本', async () => {
    const s = await withChart()
    const id = s.placeSample('AAA', '2025-02-28')!
    s.setJudgment(id, 'neg')
    s.setSampleNote(id, '放量不够')
    s.setSamplePattern(id, ' W底 ')
    await s.flushed()
    expect(fake.batches.at(-1)!.map((o: any) => o.kind)).toEqual(['pattern', 'sample'])
    expect(s.state!.patterns).toEqual([{ name: 'W底' }])
    expect(s.state!.charts[0].samples[0]).toMatchObject({ judgment: 'neg', note: '放量不够', pattern: 'W底' })
    s.deleteSample(id)
    expect(s.currentSampleId).toBeNull()
    expect(s.selectedSampleId).toBeNull()
    await s.flushed()
    expect(fake.batches.at(-1)).toEqual([{ kind: 'sample', id, base: 'pc-batch-4#1', value: null }])
    expect(s.state!.charts[0].samples).toEqual([])
  })

  it('顶栏 + new:新建 pattern 并成为当前 pattern,记在浏览器里;刷新后不在词表里的名字退回 unsorted', async () => {
    let s = await withChart()
    s.setCurrentPattern('W底')
    await s.flushed()
    expect(fake.batches).toEqual([[{ kind: 'pattern', id: 'W底', base: null, value: { name: 'W底' } }]])
    expect(s.currentPattern).toBe('W底')
    setActivePinia(createPinia())
    s = useAnnotationStore()
    await s.load()
    expect(s.currentPattern).toBe('W底')
    localStorage.setItem('path2_web_ui.annotation.current_pattern.v1', JSON.stringify('不存在'))
    setActivePinia(createPinia())
    s = useAnnotationStore()
    await s.load()
    expect(s.currentPattern).toBeNull()
  })

  it('保存被拒:原因留给界面显示,并重读一次,显示后端眼下的状态(另一台机器同步来的修改)', async () => {
    const s = await withChart({ charts: [{ symbol: 'AAA', boxes: boxes(), samples: [
      { id: 's-pc-5', date: '2025-02-28', pattern: null, judgment: 'pos', members: ['b-pc-1'] }] }] })
    // 另一台机器把 b-pc-2 也收进了 s-pc-5,本页还不知道
    fake.read = { ...fake.read, state: { ...fake.read.state, charts: [{ ...fake.read.state.charts[0],
      samples: [{ ...fake.read.state.charts[0].samples[0], members: ['b-pc-1', 'b-pc-2'] }] }] } }
    fake.reject = [{ code: 'box_crosses_sample_date', message: 'x', sample: 's-pc-5', box: 'b-pc-2' }]
    s.resizeBox('b-pc-2', '2025-02-03', '2025-03-04')
    await s.flushed()
    expect(s.saveError).toEqual(fake.reject)
    expect(s.state!.charts[0].samples[0].members).toEqual(['b-pc-1', 'b-pc-2'])
    expect(s.state!.charts[0].boxes.find(b => b.id === 'b-pc-2')!.end).toBe('2025-02-14')
  })
})

describe('冲突提示一次', () => {
  it('看过的冲突记下来,再读也不再算新的', async () => {
    const r = emptyRead()
    r.conflicts = [{ kind: 'feature', id: 'w-pc-2', base: 'a#1',
      later: { ref: 'pc-x#0', machine: 'pc', ts: 't2' }, earlier: { ref: 'upc-y#3', machine: 'upc', ts: 't1' } }]
    let s = await ready(r)
    expect(s.newConflicts).toHaveLength(1)
    s.ackConflicts()
    expect(s.newConflicts).toHaveLength(0)
    setActivePinia(createPinia())
    s = await ready(r)
    expect(s.newConflicts).toHaveLength(0)
  })
})

it('applyOps 被假后端用到(防止 mock 与真实现走样)', () => {
  expect(applyOps(emptyRead(), []).next_seq).toBe(1)
})
