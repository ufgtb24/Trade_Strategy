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
import { useViewStore } from '../src/stores/view'

function emptyRead(state: Partial<AnnState> = {}): AnnRead {
  return {
    state: { machine: 'pc', data_fingerprint: null, features: [], patterns: [], charts: [], ...state },
    conflicts: [], unsynced: [], violations: [],
    fingerprint: { local: 'fp', local_error: null, recorded: [], consistent: true }, merges: [],
    revs: { feature: {}, pattern: {}, box: {}, sample: {}, feedback: {} }, next_seq: 1, ignored_files: [],
    membership: { gap: 20, near: 40 },
    match: { pos: 3, neg: 1, sub: 2 },
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
    r.revs = { feature: { 'w-pc-1': 'b0#0', 'w-pc-2': 'b1#1' }, pattern: {}, box: { 'b-pc-3': 'b1#0' }, sample: {}, feedback: {} }
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

  it('工具默认都不亮;点一下亮、再点一下熄,点亮一个另一个就熄', async () => {
    const s = await withChart()
    expect(s.tool).toBe(null)
    s.toggleTool('box')
    expect(s.tool).toBe('box')
    s.toggleTool('point')
    expect(s.tool).toBe('point')
    s.toggleTool('point')
    expect(s.tool).toBe(null)
  })

  it('放样本:归当前 pattern、默认 pos,成员框按推断(跨过样本日的不收);工具熄灭,它成为选中的当前样本', async () => {
    const s = await withChart()
    s.toggleTool('point')
    const id = s.placeSample('AAA', '2025-02-28')
    expect(id).toBe('s-pc-10')
    expect(s.tool).toBe(null)
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
    const a = s.placeSample('AAA', '2025-02-28')!
    await s.flushed()
    s.clearSelection()
    expect(s.currentSampleId).toBeNull()
    s.createBox('AAA', '2025-02-20', '2025-02-26', null)
    await s.flushed()
    expect(sampleOps()).toHaveLength(1)
    // 再让 a 当一次当前样本,然后选另一个样本 b:之后补画的框只并进 b(若推断收它),不进 a
    s.selectSample(a)
    const b = s.placeSample('AAA', '2025-03-31')!
    expect(s.currentSampleId).toBe(b)
    s.createBox('AAA', '2025-02-24', '2025-02-27', null)
    await s.flushed()
    const byId = (id: string) => s.state!.charts[0].samples.find(x => x.id === id)!
    expect(byId(a).members).toEqual(['b-pc-1', 'b-pc-2'])
    expect(byId(b).members).toContain(s.selectedBoxId)
  })

  it('改起止只让当前样本期间新画的框并进;拖一下旧框不会把它收进来(手动点掉的旧框不会因此回来)', async () => {
    const s = await withChart({ charts: [{ symbol: 'AAA', boxes: boxes().slice(0, 1), samples: [] }] })
    s.placeSample('AAA', '2025-03-31')
    await s.flushed()
    s.resizeBox('b-pc-1', '2025-01-06', '2025-03-14')
    await s.flushed()
    expect(s.state!.charts[0].samples[0].members).toEqual([])
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

describe('归组与 pattern 页', () => {
  const smp = (id: string, date: string, pattern: string | null, judgment: 'pos' | 'neg' = 'pos') =>
    ({ id, date, pattern, judgment, members: [] as string[] })
  async function withSamples() {
    const r = emptyRead({ patterns: [{ name: 'W底', flags: [{ feature: 'w-pc-9', mapping_row: 1 }] }], charts: [
      { symbol: 'AAA', boxes: [], samples: [smp('s-pc-1', '2025-02-03', null), smp('s-pc-2', '2025-02-10', null, 'neg')] },
      { symbol: 'BBB', boxes: [], samples: [smp('s-pc-3', '2025-03-03', null), smp('s-pc-4', '2025-03-10', 'W底')] },
    ] })
    r.next_seq = 10
    return ready(r)
  }

  it('整行 move:一批改这一行全部样本的 pattern;新名字同一批新建 pattern', async () => {
    const s = await withSamples()
    s.moveSamples(['s-pc-1', 's-pc-3'], 'W底')
    await s.flushed()
    expect(fake.batches).toEqual([[
      { kind: 'sample', id: 's-pc-1', base: null, value: { ...smp('s-pc-1', '2025-02-03', 'W底'), symbol: 'AAA' } },
      { kind: 'sample', id: 's-pc-3', base: null, value: { ...smp('s-pc-3', '2025-03-03', 'W底'), symbol: 'BBB' } },
    ]])
    s.moveSamples(['s-pc-2'], ' 旗形 ')
    await s.flushed()
    expect(fake.batches[1].map((o: any) => [o.kind, o.id, o.value.pattern ?? o.value.name])).toEqual([
      ['pattern', '旗形', '旗形'], ['sample', 's-pc-2', '旗形']])
    expect(s.state!.charts.flatMap(c => c.samples.map(x => [x.id, x.pattern]))).toEqual([
      ['s-pc-1', 'W底'], ['s-pc-2', '旗形'], ['s-pc-3', 'W底'], ['s-pc-4', 'W底']])
    expect(s.currentPattern).toBeNull()                    // 只改归类,不换当前 pattern
  })

  it('pattern 的定义:写进这个 pattern(flags 照旧),空着就拿掉;没改不送', async () => {
    const s = await withSamples()
    s.setPatternDefinition('W底', ' 两个低点,第二个不破第一个 ')
    s.setPatternDefinition('W底', '两个低点,第二个不破第一个')
    await s.flushed()
    expect(fake.batches).toEqual([[{ kind: 'pattern', id: 'W底', base: null, value: {
      name: 'W底', flags: [{ feature: 'w-pc-9', mapping_row: 1 }], definition: '两个低点,第二个不破第一个' } }]])
    s.setPatternDefinition('W底', '  ')
    await s.flushed()
    expect(fake.batches[1]).toEqual([{ kind: 'pattern', id: 'W底', base: 'pc-batch-1#0',
      value: { name: 'W底', flags: [{ feature: 'w-pc-9', mapping_row: 1 }] } }])
  })

  it('点开的计数换当前 pattern 时收起;从 pattern 页打开样本时侧栏留在当前页', async () => {
    const s = await withSamples()
    s.tab = 'pattern'
    s.openCount = 'samples|pos'
    s.setCurrentPattern(null)
    expect(s.openCount).toBe('samples|pos')
    s.setCurrentPattern('W底')
    expect(s.openCount).toBeNull()
    s.selectSample('s-pc-4', { keepTab: true })
    expect([s.tab, s.selectedSampleId, s.currentSampleId]).toEqual(['pattern', 's-pc-4', 's-pc-4'])
    s.selectSample('s-pc-1')
    expect(s.tab).toBe('selection')
  })
})

describe('反馈', () => {
  const fbRec = (id: string, extra: Record<string, unknown> = {}) => ({
    id, pattern: 'p', app_id: 'app1', app_ver: 'v0', start: '2025-01-06', end: '2025-01-10', target: 'family',
    source: 'picked', answer: 'neg', note: '追高', family_start: '2025-01-02', ...extra }) as any

  /** compare 下 AAA 的现算结果(app_ver 是单股预览带回的指纹)。 */
  function inCompare(symbol = 'AAA', appVer: string | null = 'v1') {
    const view = useViewStore()
    view.symbol = symbol
    view.mode = 'compare'
    view.setLinkedRun({ symbol, app: 'app1', analysis: { events: [], hits: [] },
                        pattern_spec: {} as any, scan: { end_node: 'plateau.today', app_ver: appVer ?? undefined } as any })
    return view
  }

  it('新建:编号字母 f、带机器名;pattern 取当前 pattern,app 与版本取现算结果;source 为 picked', async () => {
    const s = await ready()
    s.setCurrentPattern('p')
    inCompare()
    const id = s.saveFeedback({ symbol: 'AAA', start: '2025-01-06', end: '2025-01-10', target: 'family',
                                family_start: '2025-01-02', answer: 'neg', note: ' 追高 ', segments: ['step'] })
    expect(id).toBe('f-pc-1')
    expect(s.feedbackOf('AAA').map(f => f.id)).toEqual(['f-pc-1'])          // 还没存完就显示
    await s.flushed()
    expect(fake.batches.at(-1)).toEqual([{ kind: 'feedback', id: 'f-pc-1', base: null, value: {
      id: 'f-pc-1', symbol: 'AAA', pattern: 'p', app_id: 'app1', app_ver: 'v1', start: '2025-01-06', end: '2025-01-10',
      target: 'family', source: 'picked', answer: 'neg', note: '追高', family_start: '2025-01-02' } }])
    expect(fake.read.state.charts[0].feedback).toHaveLength(1)
    expect(fake.read.state.charts[0].samples).toEqual([])
  })

  it('改:同编号整条重写,base 取最新,app_ver 刷新为当前值;redraw 成 range 去掉 family_start;别的 pattern 的不改', async () => {
    const r = emptyRead({ patterns: [{ name: 'p' }, { name: 'q' }],
      charts: [{ symbol: 'AAA', boxes: [], samples: [], feedback: [fbRec('f-pc-1')] }] })
    r.revs.feedback = { 'f-pc-1': 'pc-batch-0#0' }
    r.next_seq = 2
    const s = await ready(r)
    s.setCurrentPattern('q')
    inCompare()
    const draft = { id: 'f-pc-1', symbol: 'AAA', start: '2025-01-07', end: '2025-01-09', target: 'range' as const,
                    answer: 'off_pattern' as const, note: '', segments: ['step', 'today'] }
    expect(s.saveFeedback(draft)).toBeNull()             // 当前 pattern 是 q,这条是 p 的:不改(出处会混)
    s.setCurrentPattern('p')
    const id = s.saveFeedback(draft)
    expect(id).toBe('f-pc-1')
    await s.flushed()
    expect(fake.batches).toEqual([[{ kind: 'feedback', id: 'f-pc-1', base: 'pc-batch-0#0', value: {
      id: 'f-pc-1', symbol: 'AAA', pattern: 'p', app_id: 'app1', app_ver: 'v1', start: '2025-01-07', end: '2025-01-09',
      target: 'range', source: 'picked', answer: 'off_pattern', segments: ['step', 'today'] } }]])
  })

  it('不存:保存条件不满足、这只股票没有现算结果或没带版本、要改的是盲看标记;和原来一模一样时不写', async () => {
    const r = emptyRead({ patterns: [{ name: 'p' }], charts: [{ symbol: 'AAA', boxes: [], samples: [], feedback: [
      fbRec('f-pc-1', { app_ver: 'v1' }),
      fbRec('f-pc-2', { source: 'random', target: 'point', start: '2025-01-13', end: '2025-01-13', family_start: undefined }),
    ] }] })
    const s = await ready(r)
    s.setCurrentPattern('p')
    const range = { symbol: 'AAA', start: '2025-01-06', end: '2025-01-10', target: 'range' as const }
    expect(s.saveFeedback({ ...range, answer: 'neg', note: 'x' })).toBeNull()              // 还没进 compare
    inCompare()
    useViewStore().mode = 'app'
    expect(s.saveFeedback({ ...range, answer: 'neg', note: 'x' })).toBeNull()              // app 模式(现算的)不存
    inCompare('BBB')
    expect(s.saveFeedback({ ...range, answer: 'neg', note: 'x' })).toBeNull()              // 现算的是别的股票
    inCompare('AAA', null)
    expect(s.saveFeedback({ ...range, answer: 'neg', note: 'x' })).toBeNull()              // 预览没带版本
    inCompare()
    expect(s.saveFeedback({ ...range, answer: 'neg', note: ' ' })).toBeNull()              // neg 没写理由
    expect(s.saveFeedback({ ...range, answer: 'off_pattern' })).toBeNull()                // 分段、理由都没有
    expect(s.saveFeedback({ ...range, id: 'f-pc-2', target: 'point', start: '2025-01-13', end: '2025-01-13',
                            answer: 'neg', note: 'x' })).toBeNull()                        // 盲看标记不可改
    expect(s.saveFeedback({ ...range, id: 'f-pc-1', target: 'family', family_start: '2025-01-02',
                            answer: 'neg', note: '追高' })).toBe('f-pc-1')                 // 一模一样
    await s.flushed()
    expect(fake.batches).toEqual([])
  })

  it('删:一条删除操作,base 取最新;删光了这只股票不出 feedback 键;盲看标记删不得', async () => {
    const r = emptyRead({ patterns: [{ name: 'p' }], charts: [
      { symbol: 'AAA', boxes: [], samples: [], feedback: [fbRec('f-pc-1')] },
      { symbol: 'BBB', boxes: [{ id: 'b-pc-3', feature: null, start: '2025-01-02', end: '2025-01-03' }], samples: [],
        feedback: [fbRec('f-pc-2', { source: 'random', target: 'point', start: '2025-01-13', end: '2025-01-13',
                                     family_start: undefined })] },
    ] })
    r.revs.feedback = { 'f-pc-1': 'pc-batch-0#0', 'f-pc-2': 'pc-batch-0#1' }
    const s = await ready(r)
    s.deleteFeedback('f-pc-2')
    s.deleteFeedback('f-pc-1')
    await s.flushed()
    expect(fake.batches).toEqual([[{ kind: 'feedback', id: 'f-pc-1', base: 'pc-batch-0#0', value: null }]])
    expect(s.state!.charts.map(c => c.symbol)).toEqual(['BBB'])
    expect(s.state!.charts[0].feedback!.map(f => f.id)).toEqual(['f-pc-2'])
  })

  it('取反馈:这只股票、跨股票,都只取当前 pattern(或给定的 pattern)的', async () => {
    const r = emptyRead({ patterns: [{ name: 'p' }, { name: 'q' }], charts: [
      { symbol: 'AAA', boxes: [], samples: [], feedback: [fbRec('f-pc-1'), fbRec('f-pc-2', { pattern: 'q' })] },
      { symbol: 'BBB', boxes: [], samples: [], feedback: [fbRec('f-pc-3')] },
    ] })
    const s = await ready(r)
    s.setCurrentPattern('p')
    expect(s.feedbackOf('AAA').map(f => f.id)).toEqual(['f-pc-1'])
    expect(s.feedbackOf('AAA', 'q').map(f => f.id)).toEqual(['f-pc-2'])
    expect(s.feedbackOf('CCC')).toEqual([])
    expect(s.feedbackOfPattern().map(x => [x.symbol, x.feedback.id])).toEqual([['AAA', 'f-pc-1'], ['BBB', 'f-pc-3']])
    s.setCurrentPattern(null)
    expect(s.feedbackOfPattern()).toEqual([])
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

describe('删样本带框与撤销删除', () => {
  const keys = (ops: AnnOp[]) => ops.map(o => `${o.kind}:${o.id}`)
  // AAA:s-pc-5 的成员 b1、b2、b3;b3 也是 s-pc-6 的成员;b2、b4 挂在 b1 上;s-pc-7 存着 b2 但 b2 跨过它的样本日
  function chartWithSamples() {
    const r = emptyRead({ patterns: [{ name: 'p' }], charts: [{ symbol: 'AAA',
      boxes: [{ id: 'b-pc-1', feature: null, start: '2025-01-06', end: '2025-01-10' },
              { id: 'b-pc-2', feature: null, start: '2025-01-07', end: '2025-01-09', attach: 'b-pc-1' },
              { id: 'b-pc-3', feature: null, start: '2025-01-13', end: '2025-01-17' },
              { id: 'b-pc-4', feature: null, start: '2025-01-08', end: '2025-01-10', attach: 'b-pc-1' }],
      samples: [{ id: 's-pc-7', date: '2025-01-08', pattern: 'p', judgment: 'pos', members: ['b-pc-2'] },
                { id: 's-pc-5', date: '2025-02-10', pattern: 'p', judgment: 'pos', members: ['b-pc-1', 'b-pc-2', 'b-pc-3'] },
                { id: 's-pc-6', date: '2025-02-12', pattern: 'p', judgment: 'pos', members: ['b-pc-3', 'b-pc-4'] }] }] })
    r.revs.box = { 'b-pc-1': 'x#1', 'b-pc-2': 'x#2', 'b-pc-3': 'x#3', 'b-pc-4': 'x#4' }
    r.revs.sample = { 's-pc-5': 'x#5', 's-pc-6': 'x#6', 's-pc-7': 'x#7' }
    r.next_seq = 8
    return r
  }

  it('删样本带只服务它的框:一批里删样本和这些框;一起删的两个框之间不清 attach(否则同一个框既删又改)', async () => {
    const s = await ready(chartWithSamples())
    s.selectBox('b-pc-2')
    s.deleteSample('s-pc-5', ['b-pc-1', 'b-pc-2'])
    expect(s.selectedBoxId).toBeNull()                      // 选中的框被一并删了
    await s.flushed()
    expect(fake.batches).toHaveLength(1)
    const ops = fake.batches[0]
    expect(keys(ops)).toEqual(['sample:s-pc-5', 'box:b-pc-1', 'box:b-pc-2', 'sample:s-pc-7', 'box:b-pc-4'])
    expect(new Set(keys(ops)).size).toBe(ops.length)        // 同一对象只出现一次(后端 duplicate_op)
    expect(ops.slice(0, 3).map((o: AnnOp) => [o.base, o.value])).toEqual([['x#5', null], ['x#1', null], ['x#2', null]])
    expect(ops[3].value.members).toEqual([])               // 别的样本存着的被删框照删框的规矩拿掉
    expect(ops[4].value).not.toHaveProperty('attach')       // 本批不删的框:挂在被删框上的 attach 拿掉
    expect(s.state!.charts[0].boxes.map(b => b.id)).toEqual(['b-pc-4', 'b-pc-3'])
    expect(s.lastDeletion!.removed.map(x => `${x.kind}:${x.id}`)).toEqual(['sample:s-pc-5', 'box:b-pc-1', 'box:b-pc-2'])
  })

  it('删样本不带框:只删样本,框都留在图上;记下的删除只有这个样本', async () => {
    const s = await ready(chartWithSamples())
    s.deleteSample('s-pc-5')
    await s.flushed()
    expect(fake.batches).toEqual([[{ kind: 'sample', id: 's-pc-5', base: 'x#5', value: null }]])
    expect(s.state!.charts[0].boxes).toHaveLength(4)
    expect(s.lastDeletion!.removed.map(x => x.id)).toEqual(['s-pc-5'])
  })

  it('撤销删框:框用原编号写回(base 取删除那次);成员与 attach 只加回当前值,删后改的 judgment 不被冲掉', async () => {
    const s = await ready(emptyRead({ charts: [{ symbol: 'AAA',
      boxes: [{ id: 'b-pc-1', feature: null, start: '2025-01-06', end: '2025-01-10' },
              { id: 'b-pc-2', feature: null, start: '2025-01-09', end: '2025-01-14', attach: 'b-pc-1' }],
      samples: [{ id: 's-pc-3', date: '2025-01-15', pattern: null, judgment: 'pos', members: ['b-pc-1', 'b-pc-2'] }] }] }))
    const before: AnnState = structuredClone(fake.read.state)
    s.deleteBox('b-pc-1')
    await s.flushed()
    s.setJudgment('s-pc-3', 'neg')
    await s.flushed()
    expect(s.lastDeletion).not.toBeNull()                   // 别的修改不清掉可撤的删除
    s.undoDeletion()
    expect(s.lastDeletion).toBeNull()
    await s.flushed()
    expect(fake.batches).toHaveLength(3)
    expect(fake.batches[2]).toEqual([
      { kind: 'box', id: 'b-pc-1', base: 'pc-batch-1#0',
        value: { id: 'b-pc-1', symbol: 'AAA', feature: null, start: '2025-01-06', end: '2025-01-10' } },
      { kind: 'sample', id: 's-pc-3', base: 'pc-batch-2#0',
        value: { id: 's-pc-3', symbol: 'AAA', date: '2025-01-15', pattern: null, judgment: 'neg', members: ['b-pc-1', 'b-pc-2'] } },
      { kind: 'box', id: 'b-pc-2', base: 'pc-batch-1#2',
        value: { id: 'b-pc-2', symbol: 'AAA', feature: null, start: '2025-01-09', end: '2025-01-14', attach: 'b-pc-1' } },
    ])
    expect(s.state!.charts[0].boxes).toEqual(before.charts[0].boxes)
    expect(s.state!.charts[0].samples[0]).toMatchObject({ judgment: 'neg', members: ['b-pc-1', 'b-pc-2'] })
    s.undoDeletion()                                        // 撤过就不能再撤
    await s.flushed()
    expect(fake.batches).toHaveLength(3)
  })

  it('撤销删样本(连同框):样本与框写回原值;删后改过的框保留改动,只把 attach 加回;越过样本日的存着的成员不加回', async () => {
    const s = await ready(chartWithSamples())
    const before: AnnState = structuredClone(fake.read.state)
    s.deleteSample('s-pc-5', ['b-pc-1', 'b-pc-2'])
    await s.flushed()
    s.setBoxNote('b-pc-4', '后加的')
    await s.flushed()
    s.undoDeletion()
    await s.flushed()
    const ops = fake.batches[2]
    expect(keys(ops)).toEqual(['sample:s-pc-5', 'box:b-pc-1', 'box:b-pc-2', 'box:b-pc-4'])
    expect(ops.slice(0, 3).map((o: AnnOp) => o.base)).toEqual(['pc-batch-1#0', 'pc-batch-1#1', 'pc-batch-1#2'])
    expect(ops[3]).toMatchObject({ base: 'pc-batch-2#0', value: { note: '后加的', attach: 'b-pc-1' } })
    const st = s.state!.charts[0]
    expect(st.samples).toEqual(before.charts[0].samples.map(x => (x.id === 's-pc-7' ? { ...x, members: [] } : x)))
    expect(st.boxes.find(b => b.id === 'b-pc-2')).toEqual(before.charts[0].boxes.find(b => b.id === 'b-pc-2'))
  })

  it('撤销删反馈:用原编号写回原值,base 取删除那次', async () => {
    const fb = { id: 'f-pc-1', pattern: 'p', app_id: 'app1', app_ver: 'v0', start: '2025-01-06', end: '2025-01-10',
                 target: 'range', source: 'picked', answer: 'neg', note: '追高' } as any
    const r = emptyRead({ patterns: [{ name: 'p' }], charts: [{ symbol: 'AAA', boxes: [], samples: [], feedback: [fb] }] })
    r.revs.feedback = { 'f-pc-1': 'x#0' }
    const s = await ready(r)
    s.deleteFeedback('f-pc-1')
    await s.flushed()
    expect(s.state!.charts).toEqual([])
    s.undoDeletion()
    await s.flushed()
    expect(fake.batches[1]).toEqual([{ kind: 'feedback', id: 'f-pc-1', base: 'pc-batch-1#0', value: { ...fb, symbol: 'AAA' } }])
    expect(s.state!.charts[0].feedback).toEqual([fb])
  })

  it('再删一次换成新的;删除没保存成(被拒)不留可撤的记录;显示的状态里没什么可删时不换', async () => {
    const s = await ready(chartWithSamples())
    s.deleteBox('b-pc-3')
    s.deleteBox('b-pc-4')
    expect(s.lastDeletion!.removed[0].id).toBe('b-pc-4')
    s.deleteBox('b-pc-4')                                    // 已经删了:不换记录
    expect(s.lastDeletion!.removed[0].id).toBe('b-pc-4')
    await s.flushed()
    expect(s.lastDeletion!.removed[0].id).toBe('b-pc-4')
    fake.reject = [{ code: 'member_missing', message: 'x' }]
    s.deleteSample('s-pc-6')
    expect(s.lastDeletion!.removed[0].id).toBe('s-pc-6')
    await s.flushed()
    expect(s.lastDeletion).toBeNull()
  })
})

it('applyOps 被假后端用到(防止 mock 与真实现走样)', () => {
  expect(applyOps(emptyRead(), []).next_seq).toBe(1)
})
