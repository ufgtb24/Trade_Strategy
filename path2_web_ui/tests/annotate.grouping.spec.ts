// 归组与 pattern 页的派生量(annotate/grouping.ts):
// - unsorted 页按骨架分行,和成员推断共用例子文件 membership_examples.json 里骨架的答案一致;
// - 计数照决策票 15:一律数样本、pos k/N · neg m/M、点开分排各排之和等于分母、0 也算出来、同名框按「任一个」;
// - pattern 里各段的先后(features 区与 annotate 轨序共用)。
// 计数用一份固定的例子标注:tests/path2_web/fixtures/annotation_grouping_v1 下的批次文件(标注存储的格式),
// 这里把它的操作套到空状态上;下面的数字是对着这份例子手算的答案。
import { describe, it, expect } from 'vitest'
import { readdirSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { applyOps, computeLanes, type AnnRead, type AnnState } from '../src/annotate/model'
import {
  attrOf, attrsUsed, countId, countParts, countRatio, countText, denominator, featureBlocks, featureOrder, partCount,
  patternSamples, sampleWindow, unsortedRows, type ChartSample, type CountKey, type FeatureBlock,
} from '../src/annotate/grouping'

const DIR = resolve(__dirname, '../../tests/path2_web/fixtures/annotation_grouping_v1/batches')
const EXAMPLES = resolve(__dirname, '../../tests/path2_web/fixtures/membership_examples.json')

function emptyRead(): AnnRead {
  return {
    state: { machine: 'pc', data_fingerprint: null, features: [], patterns: [], charts: [] },
    conflicts: [], unsynced: [], violations: [],
    fingerprint: { local: null, local_error: null, recorded: [], consistent: true }, merges: [],
    revs: { feature: {}, pattern: {}, box: {}, sample: {}, feedback: {} }, next_seq: 1, ignored_files: [],
    membership: { gap: 20, near: 40 },
    match: { pos: 3, neg: 1, sub: 2 },
  }
}

function fixtureState(): AnnState {
  let r = emptyRead()
  for (const f of readdirSync(DIR).sort()) r = applyOps(r, JSON.parse(readFileSync(resolve(DIR, f), 'utf8')).ops)
  return r.state
}

const st = fixtureState()
const fid = (name: string) => st.features.find(f => f.name === name)!.id
const nameOf = (f: string | null) => (f === null ? null : st.features.find(x => x.id === f)?.name ?? f)
const noDays = () => null               // 例子里的图都没打开过:框套框用周一到周五代替
const ratio = (xs: ChartSample[], k: CountKey) => {
  const r = countRatio(xs, k)
  return `pos ${r.pos}/${r.posOf} · neg ${r.neg}/${r.negOf}`
}
const tag = (x: ChartSample) => `${x.chart.symbol} ${x.sample.date}`

describe('unsorted 页按骨架分行', () => {
  it('和成员推断的例子文件里骨架的答案一致;同一骨架同一 judgment 并成一行,neg 另起一行', () => {
    const doc = JSON.parse(readFileSync(EXAMPLES, 'utf8'))
    const days: string[] = doc.days
    const cases = (doc.cases as any[]).filter(c => c.fn === 'tree')
    expect(cases.length).toBeGreaterThan(0)
    const charts = cases.flatMap((c, i) => {
      const boxes = c.boxes.map((b: any) => ({ ...b, start: days[b.start], end: days[b.end] }))
      const last = Math.max(...c.members.map((m: string) => c.boxes.find((b: any) => b.id === m).end))
      const mk = (symbol: string, judgment: 'pos' | 'neg') => ({
        symbol, boxes, samples: [{ id: `s-${symbol}`, date: days[last], pattern: null, judgment, members: c.members }],
      })
      // 第一个例子再放到另一张图上(同骨架、同 judgment)和一个 neg 版本
      return i === 0 ? [mk(`C${i}`, 'pos'), mk(`C${i}b`, 'pos'), mk(`C${i}n`, 'neg')] : [mk(`C${i}`, 'pos')]
    })
    const state: AnnState = { machine: 'pc', data_fingerprint: null, features: [], patterns: [], charts }
    const rows = unsortedRows(state, () => days, f => f)
    for (const [i, c] of cases.entries()) {
      const row = rows.find(r => r.judgment === 'pos' && r.samples.some(x => x.chart.symbol === `C${i}`))!
      expect(row.skeleton).toEqual(c.expect.skeleton)
    }
    const first = rows.find(r => r.samples.some(x => x.chart.symbol === 'C0'))!
    expect(first.samples.map(x => x.chart.symbol)).toEqual(['C0', 'C0b'])
    const neg = rows.find(r => r.judgment === 'neg')!
    expect(neg.samples.map(x => x.chart.symbol)).toEqual(['C0n'])
    expect(neg.skeleton).toEqual(cases[0].expect.skeleton)
  })

  it('例子标注:子框不进骨架;行按骨架的特征名排,同骨架 pos 在 neg 前,没有成员框的排最后', () => {
    const rows = unsortedRows(st, noDays, nameOf)
    expect(rows.map(r => [r.judgment, r.skeleton.map(nameOf).join(' → '), r.samples.map(tag)])).toEqual([
      ['pos', '回踩', ['MSFT 2024-07-15']],
      ['pos', '横盘 → 突破', ['MSFT 2024-05-08', 'NVDA 2024-07-09']],     // MSFT 那个样本收了 缩量(横盘的子框)
      ['neg', '横盘 → 突破', ['AAPL 2024-09-09']],
      ['pos', '', ['NVDA 2024-10-15']],
    ])
  })
})

describe('pattern 里各段的先后', () => {
  it('两两比先后;从没同时出现过的按平均位置', () => {
    expect([...featureOrder(patternSamples(st, 'W底')).keys()].map(nameOf)).toEqual(['横盘', '缩量', '突破', '派发'])
    expect([...featureOrder(patternSamples(st, null)).keys()].map(nameOf)).toEqual(['横盘', '回踩', '缩量', '突破'])
    expect(featureOrder([]).size).toBe(0)
  })

  it('annotate 的轨序按当前 pattern 的先后,不在其中的特征按这张图上首次出现排在后面;子框轨仍紧跟父轨', () => {
    const msft = st.charts.find(c => c.symbol === 'MSFT')!
    const lanes = (order?: Map<string, number>) =>
      computeLanes(msft.boxes, f => nameOf(f)!, [], order).map(l => (l.parent ? `${nameOf(l.key)} ⊂ ${nameOf(l.parent)}` : nameOf(l.key)))
    expect(lanes()).toEqual(['派发', '横盘', '缩量 ⊂ 横盘', '突破', '回踩'])
    expect(lanes(featureOrder(patternSamples(st, 'W底')))).toEqual(['横盘', '缩量 ⊂ 横盘', '突破', '派发', '回踩'])
    expect(lanes(featureOrder(patternSamples(st, null)))).toEqual(['横盘', '缩量 ⊂ 横盘', '回踩', '突破', '派发'])
  })
})

describe('pattern 页的 features 区', () => {
  const xs = patternSamples(st, 'W底')
  const blocks = featureBlocks(xs, noDays, featureOrder(xs))
  const named = (b: FeatureBlock): unknown => ({ f: nameOf(b.feature), kids: b.kids.map(named) })

  it('收正、负样本成员框里的顶层特征,按先后排;当过子框的挂在父块下面;只在负样本里出现的也列', () => {
    expect(blocks.map(named)).toEqual([
      { f: '横盘', kids: [{ f: '缩量', kids: [] }] }, { f: '突破', kids: [] }, { f: '派发', kids: [] }])
    expect(attrsUsed(xs, fid('横盘')).map(nameOf)).toEqual(['窄幅'])
    expect(attrsUsed(xs, fid('突破')).map(nameOf)).toEqual(['放量'])
    expect(attrsUsed(xs, fid('派发'))).toEqual([])
  })

  it('各处计数:一律数样本,pos k/N · neg m/M,0 也算出来', () => {
    expect(denominator(xs, { kind: 'samples', judgment: 'pos' })).toHaveLength(3)
    expect(denominator(xs, { kind: 'samples', judgment: 'neg' })).toHaveLength(1)
    const inOf = (n: string) => ratio(xs, { kind: 'in', feature: fid(n) })
    const trueOf = (n: string, w: string) => ratio(xs, { kind: 'attr', feature: fid(n), attr: fid(w) })
    expect(inOf('横盘')).toBe('pos 3/3 · neg 1/1')
    expect(inOf('缩量')).toBe('pos 1/3 · neg 0/1')
    expect(inOf('突破')).toBe('pos 3/3 · neg 0/1')
    expect(inOf('派发')).toBe('pos 0/3 · neg 1/1')
    expect(trueOf('横盘', '窄幅')).toBe('pos 1/3 · neg 0/1')
    // NVDA 那个样本收了两个突破框,一个放量 false、一个 true:按「任一个」算 true
    expect(trueOf('突破', '放量')).toBe('pos 2/3 · neg 0/0')
    // 界面上的写法
    expect(countText(xs, { kind: 'samples', judgment: 'pos' })).toBe('pos 3')
    expect(countText(xs, { kind: 'in', feature: fid('派发') })).toBe('in pos 0/3 · neg 1/1')
    expect(countText(xs, { kind: 'attr', feature: fid('突破'), attr: fid('放量') })).toBe('true pos 2/3 · neg 0/0')
    // 一个样本都没有的 pattern:全是 0
    const none = patternSamples(st, '旗形')
    expect(none).toEqual([])
    expect(ratio(none, { kind: 'in', feature: fid('横盘') })).toBe('pos 0/0 · neg 0/0')
  })

  it('点开分排:各排之和等于分母,空的排也在,排里正样本在前', () => {
    const keys: CountKey[] = [{ kind: 'samples', judgment: 'pos' }, { kind: 'samples', judgment: 'neg' }]
    const walk = (b: FeatureBlock) => {
      keys.push({ kind: 'in', feature: b.feature })
      for (const w of attrsUsed(xs, b.feature)) keys.push({ kind: 'attr', feature: b.feature, attr: w })
      b.kids.forEach(walk)
    }
    blocks.forEach(walk)
    expect(keys).toHaveLength(2 + 4 + 2)
    for (const k of keys) {
      const parts = countParts(xs, k)
      const ids = parts.flatMap(p => p.samples.map(x => x.sample.id))
      expect(new Set(ids).size, countId(k)).toBe(ids.length)
      expect(ids.sort(), countId(k)).toEqual(denominator(xs, k).map(x => x.sample.id).sort())
      expect(parts[0].samples.length, countId(k)).toBe(countRatio(xs, k).pos + countRatio(xs, k).neg)
    }
    const parts = (k: CountKey) => countParts(xs, k).map(p => [p.label, p.samples.map(tag)])
    expect(parts({ kind: 'in', feature: fid('派发') })).toEqual([
      ['in', ['AAPL 2024-06-17']],
      ['not_in', ['AAPL 2024-03-11', 'MSFT 2024-02-08', 'NVDA 2024-04-15']]])
    expect(parts({ kind: 'attr', feature: fid('横盘'), attr: fid('窄幅') })).toEqual([
      ['true', ['AAPL 2024-03-11']], ['false', ['AAPL 2024-06-17']], ['null', ['MSFT 2024-02-08', 'NVDA 2024-04-15']]])
    expect(parts({ kind: 'attr', feature: fid('突破'), attr: fid('放量') })).toEqual([
      ['true', ['AAPL 2024-03-11', 'NVDA 2024-04-15']], ['false', ['MSFT 2024-02-08']], ['null', []]])
    expect(parts({ kind: 'samples', judgment: 'neg' })).toEqual([['neg', ['AAPL 2024-06-17']]])
    const heads = (k: CountKey) => countParts(xs, k).map(p => `${p.label}${partCount(k, p)}`)
    expect(heads({ kind: 'attr', feature: fid('突破'), attr: fid('放量') }))
      .toEqual(['true pos 2 · neg 0', 'false pos 1 · neg 0', 'null pos 0 · neg 0'])
    expect(heads({ kind: 'samples', judgment: 'pos' })).toEqual(['pos 3'])
  })
})

describe('同名框的「任一个」', () => {
  const x = (attrs: (boolean | undefined)[]): ChartSample => {
    const boxes = attrs.map((v, i) => ({
      id: `b${i}`, feature: 'f', start: `2024-01-0${i + 1}`, end: `2024-01-0${i + 1}`, ...(v === undefined ? {} : { attrs: { w: v } }),
    }))
    return { chart: { symbol: 'X', boxes, samples: [] },
             sample: { id: 's', date: '2024-01-31', pattern: 'p', judgment: 'pos', members: boxes.map(b => b.id) } }
  }
  it('任一个 true 就算 true;都没判算 null;其余算 false', () => {
    expect(attrOf(x([false, true]), 'f', 'w')).toBe('true')
    expect(attrOf(x([undefined, true]), 'f', 'w')).toBe('true')
    expect(attrOf(x([undefined, undefined]), 'f', 'w')).toBe('null')
    expect(attrOf(x([undefined, false]), 'f', 'w')).toBe('false')
    expect(attrOf(x([false]), 'f', 'w')).toBe('false')
  })
})

describe('打开样本的图窗', () => {
  it('样本的跨度前后各留约两个月', () => {
    const [aapl] = patternSamples(st, 'W底')
    expect(tag(aapl)).toBe('AAPL 2024-03-11')
    expect(sampleWindow(aapl)).toEqual({ start: '2023-12-03', end: '2024-05-10' })
  })
})
