// 标注数据层的纯函数:操作套到状态上、属性三态(null 不算「没有」)、词表用量与起名候选、
// 特征轨的排法与子框轨、合并与拆回、parent 一行的 detach / attach。
import { describe, it, expect } from 'vitest'
import {
  applyOps, attrCounts, attrState, attrWordsOf, boxValue, computeLanes, featureUsage, kidWordsOf,
  mergePlan, mergeRecords, parentRows, rankSuggestions, toggleAttr, toggleParent, unmergedBox, weekdaysCovering,
  type AnnBox, type AnnRead, type AnnState,
} from '../src/annotate/model'

// 2025 年 1 月的交易日(1-01、1-20 休市)
const DAYS = weekdaysCovering([{ start: '2025-01-02', end: '2025-01-31' }]).filter(d => d !== '2025-01-20')

function read(state: Partial<AnnState>): AnnRead {
  return {
    state: { machine: 'pc', data_fingerprint: null, features: [], patterns: [], charts: [], ...state },
    conflicts: [], unsynced: [], violations: [],
    fingerprint: { local: 'x', local_error: null, recorded: [], consistent: true }, merges: [],
    revs: { feature: {}, pattern: {}, box: {}, sample: {} }, next_seq: 1, ignored_files: [],
  }
}

const box = (id: string, feature: string | null, start: string, end: string, extra: Partial<AnnBox> = {}): AnnBox =>
  ({ id, feature, start, end, ...extra })

describe('applyOps', () => {
  it('新建、改、删各种对象;框按起止排;next_seq 接到用过的最大号之后', () => {
    let r = read({})
    r = applyOps(r, [
      { kind: 'feature', id: 'w-pc-1', base: null, value: { id: 'w-pc-1', name: '横盘' } },
      { kind: 'box', id: 'b-pc-3', base: null, value: { id: 'b-pc-3', symbol: 'AAA', feature: 'w-pc-1', start: '2025-01-10', end: '2025-01-15' } },
      { kind: 'box', id: 'b-pc-2', base: null, value: { id: 'b-pc-2', symbol: 'AAA', feature: null, start: '2025-01-03', end: '2025-01-06' } },
    ])
    expect(r.next_seq).toBe(4)
    expect(r.state.charts).toHaveLength(1)
    expect(r.state.charts[0].boxes.map(b => b.id)).toEqual(['b-pc-2', 'b-pc-3'])
    expect(r.state.charts[0].boxes[0]).not.toHaveProperty('symbol')
    r = applyOps(r, [
      { kind: 'feature', id: 'w-pc-1', base: 'x', value: { id: 'w-pc-1', name: '盘整' } },
      { kind: 'box', id: 'b-pc-2', base: 'x', value: null },
      { kind: 'box', id: 'b-pc-3', base: 'x', value: null },
    ])
    expect(r.state.features).toEqual([{ id: 'w-pc-1', name: '盘整' }])
    expect(r.state.charts).toEqual([])
  })
})

describe('属性三态', () => {
  it('true → 再点一下 → null:键被拿掉,不是 false', () => {
    let attrs = toggleAttr(undefined, 'w1', true)
    expect(attrs).toEqual({ w1: true })
    attrs = toggleAttr(attrs, 'w1', true)
    expect(attrs).toEqual({})
    expect('w1' in attrs).toBe(false)
    expect(attrState({ attrs }, 'w1')).toBe('null')
    expect(boxValue('AAA', box('b1', 'w0', '2025-01-02', '2025-01-03', { attrs }))).not.toHaveProperty('attrs')
  })
  it('false 与 true 互换;false 再点一下也回到 null', () => {
    expect(toggleAttr({ w1: true }, 'w1', false)).toEqual({ w1: false })
    expect(toggleAttr({ w1: false }, 'w1', false)).toEqual({})
  })
  it('null 不算「没有」:没看过的框单独计数,不并进 false', () => {
    const boxes = [
      box('b1', 'w0', '2025-01-02', '2025-01-03', { attrs: { w1: true } }),
      box('b2', 'w0', '2025-01-06', '2025-01-07', { attrs: { w1: false } }),
      box('b3', 'w0', '2025-01-08', '2025-01-09'),
      box('b4', 'w0', '2025-01-10', '2025-01-13', { attrs: { w2: true } }),
    ]
    expect(attrCounts(boxes, 'w1')).toEqual({ true: 1, false: 1, null: 2 })
    const usage = featureUsage({ machine: 'pc', data_fingerprint: null, patterns: [],
      features: [{ id: 'w1', name: '放量' }], charts: [{ symbol: 'AAA', boxes, samples: [] }] })
    expect(usage.get('w1')).toEqual({ box: 0, attr: 2 })    // 只数判过的两个
  })
})

describe('词表', () => {
  const features = [
    { id: 'w1', name: '横盘' }, { id: 'w2', name: '放量突破' }, { id: 'w3', name: '缩量', definition: '量比前段小' },
    { id: 'w4', name: '回踩' },
  ]
  const usage = new Map([['w1', { box: 3, attr: 0 }], ['w2', { box: 1, attr: 0 }], ['w3', { box: 0, attr: 2 }],
                         ['w4', { box: 0, attr: 0 }]])
  it('没输入时只列当过框特征的词,按用量排', () => {
    expect(rankSuggestions('', features, usage).map(s => s.feature.id)).toEqual(['w1', 'w2'])
  })
  it('和输入有共同字(词名或定义里)的排最前、标相近;只当过属性的词相近时才列出来', () => {
    const got = rankSuggestions('放量', features, usage)
    expect(got.map(s => [s.feature.id, s.near])).toEqual([['w2', true], ['w3', true], ['w1', false]])
  })
  it('同一特征的框用过的属性按第一次出现的先后', () => {
    const charts = [{ symbol: 'A', samples: [], boxes: [box('b1', 'w1', '2025-01-02', '2025-01-03', { attrs: { w3: true } })] },
                    { symbol: 'B', samples: [], boxes: [box('b2', 'w1', '2025-01-02', '2025-01-03', { attrs: { w2: false, w3: true } }),
                                                       box('b3', 'w2', '2025-01-02', '2025-01-03', { attrs: { w4: true } })] }]
    expect(attrWordsOf('w1', charts)).toEqual(['w3', 'w2'])
  })
  it('画成过子框的词:全部图里,这个特征的框包住的框的特征', () => {
    const charts = [{ symbol: 'A', samples: [], boxes: [
      box('b1', 'w1', '2025-01-02', '2025-01-31'), box('b2', 'w3', '2025-01-06', '2025-01-10'),
      box('b3', 'w2', '2025-01-28', '2025-02-05') ] }]
    expect(kidWordsOf('w1', charts)).toEqual(['w3'])
    expect(kidWordsOf('w3', charts)).toEqual([])
  })
})

describe('特征轨', () => {
  const name = (f: string) => ({ w1: '横盘', w2: '缩量', w3: '放量', w4: '回踩' } as Record<string, string>)[f]
  it('按特征首次出现的先后;子框轨紧跟父轨;还没起名的放最后;交叠的框分行', () => {
    const boxes = [
      box('b1', 'w3', '2025-01-02', '2025-01-03'),      // 放量最早
      box('b2', 'w1', '2025-01-06', '2025-01-24'),      // 横盘
      box('b3', 'w2', '2025-01-08', '2025-01-10'),      // 缩量 ⊂ 横盘
      box('b4', 'w4', '2025-01-07', '2025-01-28'),      // 回踩比缩量早出现、和横盘交叠,但缩量是横盘的子框轨
      box('b5', 'w2', '2025-01-14', '2025-01-16'),
      box('b6', null, '2025-01-27', '2025-01-28'),
      box('b7', 'w3', '2025-01-02', '2025-01-06'),      // 和 b1 交叠
    ]
    const lanes = computeLanes(boxes, name, DAYS)
    expect(lanes.map(l => [l.key, l.parent])).toEqual([
      ['w3', null], ['w1', null], ['w2', 'w1'], ['w4', null], [null, null]])
    const fang = lanes[0]
    expect(fang.rows).toBe(2)
    expect(Object.fromEntries(fang.boxes.map(lb => [lb.box.id, lb.row]))).toEqual({ b7: 0, b1: 1 })
  })
  it('一个特征的框不全属于同一个特征的框,就不是子框轨', () => {
    const boxes = [box('b1', 'w1', '2025-01-02', '2025-01-24'), box('b2', 'w2', '2025-01-06', '2025-01-08'),
                   box('b3', 'w2', '2025-01-27', '2025-01-29')]
    expect(computeLanes(boxes, name, DAYS).map(l => [l.key, l.parent])).toEqual([['w1', null], ['w2', null]])
  })
  it('detach 掉的框不算子框', () => {
    const boxes = [box('b1', 'w1', '2025-01-02', '2025-01-24'), box('b2', 'w2', '2025-01-06', '2025-01-08', { detach: true })]
    expect(computeLanes(boxes, name, DAYS).map(l => l.parent)).toEqual([null, null])
  })
})

describe('合并与拆回', () => {
  const state: AnnState = {
    machine: 'pc', data_fingerprint: null, patterns: [],
    features: [{ id: 'w1', name: '放量' }, { id: 'w2', name: '量大' }, { id: 'w3', name: '横盘' }],
    charts: [{ symbol: 'A', samples: [], boxes: [
      box('b1', 'w2', '2025-01-02', '2025-01-03'),
      box('b2', 'w3', '2025-01-06', '2025-01-10', { attrs: { w2: true } }),
      box('b3', 'w3', '2025-01-13', '2025-01-17', { attrs: { w2: false, w1: true } }),
      box('b4', 'w1', '2025-01-21', '2025-01-22'),
    ] }],
  }
  it('预览:当特征用的、当属性用的各几个框;属性挪到并进的词上,那个词已判过的保留', () => {
    const plan = mergePlan(state, 'w2', 'w1')
    expect([plan.box, plan.attr]).toEqual([1, 2])
    const after = Object.fromEntries(plan.changes.map(c => [c.after.id, c.after]))
    expect(after.b1.feature).toBe('w1')
    expect(after.b2.attrs).toEqual({ w1: true })
    expect(after.b3.attrs).toEqual({ w1: true })
    expect(plan.changes.map(c => c.after.id)).not.toContain('b4')
  })
  it('拆回:没再动过的框整个改回;动过起止的只改回特征和属性', () => {
    const plan = mergePlan(state, 'w2', 'w1')
    const [c1, c2] = plan.changes
    expect(unmergedBox(c1, c1.after, 'w2', 'w1')).toEqual(c1.before)
    const moved = { ...c2.after, end: '2025-01-09' }
    expect(unmergedBox(c2, moved, 'w2', 'w1')).toEqual({ ...c2.before, end: '2025-01-09' })
  })
})

describe('parent 一行(框套框的 detach / attach)', () => {
  const outer = box('b1', 'w1', '2025-01-02', '2025-01-24')
  it('被包住:默认属于它,点掉 = detach;再点 = 拿掉 detach', () => {
    const inner = box('b2', 'w2', '2025-01-06', '2025-01-08')
    const [row] = parentRows(inner, [outer, inner], DAYS)
    expect([row.other.id, row.on, row.via]).toEqual(['b1', true, 'default'])
    const detached = toggleParent(inner, row)
    expect(detached.detach).toBe(true)
    const [row2] = parentRows(detached, [outer, detached], DAYS)
    expect([row2.other.id, row2.on, row2.via]).toEqual(['b1', false, 'detached'])
    expect(toggleParent(detached, row2)).toEqual(inner)
  })
  it('没被包住、和更长的框交叠:点上 = attach;再点 = 拿掉 attach', () => {
    const edge = box('b3', 'w3', '2025-01-22', '2025-01-28')
    const [row] = parentRows(edge, [outer, edge], DAYS)
    expect([row.other.id, row.on, row.via]).toEqual(['b1', false, 'candidate'])
    const attached = toggleParent(edge, row)
    expect(attached.attach).toBe('b1')
    const [row2] = parentRows(attached, [outer, attached], DAYS)
    expect([row2.on, row2.via]).toEqual([true, 'attach'])
    expect(toggleParent(attached, row2)).toEqual(edge)
  })
  it('能挂上的框都列出来,按长短排;被包住的框也能改挂到别的交叠、更长的框上', () => {
    const inner = box('b2', 'w2', '2025-01-06', '2025-01-08')
    const long = box('b4', 'w4', '2025-01-07', '2025-01-31')
    const mid = box('b5', 'w5', '2025-01-08', '2025-01-28')
    const rows = parentRows(inner, [outer, inner, long, mid], DAYS)
    expect(rows.map(r => [r.other.id, r.via])).toEqual([['b1', 'default'], ['b5', 'candidate'], ['b4', 'candidate']])
    expect(toggleParent(inner, rows[1]).attach).toBe('b5')
  })
  it('没有包住、也没有交叠的更长框:没有这一行', () => {
    expect(parentRows(outer, [outer], DAYS)).toEqual([])
  })
})

describe('读结果里的合并记录', () => {
  it('被并的词、并进的词、改过的框,以及当特征、当属性各几个框', () => {
    const r = read({})
    r.merges = [{ ref: 'f#2', machine: 'pc', ts: 't', feature: { id: 'w2', name: '量大' }, into: 'w1', boxes: [
      { id: 'b1', before: { ...box('b1', 'w2', '2025-01-02', '2025-01-03'), symbol: 'A' },
                  after: { ...box('b1', 'w1', '2025-01-02', '2025-01-03'), symbol: 'A' } },
      { id: 'b2', before: { ...box('b2', 'w3', '2025-01-06', '2025-01-07', { attrs: { w2: true } }), symbol: 'B' },
                  after: { ...box('b2', 'w3', '2025-01-06', '2025-01-07', { attrs: { w1: true } }), symbol: 'B' } },
    ] }]
    const [m] = mergeRecords(r)
    expect([m.from.id, m.into, m.box, m.attr]).toEqual(['w2', 'w1', 1, 1])
    expect(m.changes.map(c => c.symbol)).toEqual(['A', 'B'])
  })
})
