/**
 * 「复制指代」:把当前选中的东西写成一行自带上下文的话,贴给会话就能定位(股票、pattern、是哪种东西、日期,
 * 末尾方括号里是内部编号)。这里全是纯函数:
 * - resolveTarget:一次选中状态的快照 → 当前指的是哪样东西;
 * - copyLadder:那样东西 → 从小到大的几行(同一个键连按逐层放大):
 *   hit:这一次 → 这一天并在一起的几次 → 整族;event:这一个 → 它所在的族;其余只有一行。
 *   相邻两层指的是同一组东西时合并掉(那天只有一次 hit 就没有「这一天的几次」这一层)。
 *
 * 行的写法(固定词都是名词,和词表里的 hit / event / node / box / sample 对上):
 *   SYM pattern hit START→END k/n 区别 [hit_id]         这一次 hit(同一天有几次时才写 k/n 与区别在哪)
 *   SYM pattern hits buy DAY ×n start START             这一天的几次 hit
 *   SYM pattern hit_family start START buys FIRST…LAST  起点相同的整族 hit
 *   SYM pattern event NODE START→END [instance_id]      一个 event(band 上的一格)
 *   SYM pattern event_family NODE start START           同一个 node、起点相同的一族 event
 *   SYM pattern node NODE                               一条 band(一个 node)
 *   SYM box 特征名 START→END [box id]                   用户的框(框不属于某个 pattern)
 *   SYM pattern sample 字母 pos|neg DATE [sample id]    用户的样本
 *   SYM pattern feedback START→END nodes a,b [id]       一条反馈
 *   SYM pattern day DATE                                什么都没选中:当前日
 */
import type { EventDict, HitDict } from '../types'
import type { AnnChart } from './model'
import { sampleLetters } from './samples'
import { buyDaysOf, foldHits, formatMemberLabel, hitLabels } from '../render/fold'

export type CopyTarget =
  | { kind: 'feedback'; id: string }
  | { kind: 'node'; node: string }
  | { kind: 'event'; instanceId: string }
  | { kind: 'hit'; hitId: string }
  | { kind: 'sample'; id: string }
  | { kind: 'box'; id: string }
  | { kind: 'day' }

/**
 * 一次选中状态的快照。反馈记号的选中会一直留着(点了别的也不清),所以另记「最后点的是不是它 / 轨名」;
 * 'card' 是在 selection 页的 diagnose 块里点了一张卡片(当家行仍是样本行,只看状态和「选中样本」分不开)。
 */
export interface PickState {
  lastPick: 'feedback' | 'node' | 'card' | null
  feedbackId: string | null
  node: string | null
  /** 待选(一个记号属于几次 hit、买入日又不全一样)时的候选数,和点下去的那个 event */
  candidateCount: number
  pendingInstanceId: string | null
  /** 当家行的种类:band 上的族、hits 行的族、外部行(compare 的样本行) */
  familyKind: 'band' | 'bracket' | 'external' | null
  instanceId: string | null
  hitId: string | null
  boxId: string | null
  /** 选中的样本;compare 下没选中时是聚焦的那个 */
  sampleId: string | null
}

/**
 * 当前指的是哪样东西。选框、选样本会顺带把配对的 hit 设成焦点,所以两边同时有值是常态,不能只看谁非空:
 * 1. 最后点的是反馈记号 / 轨名,且它还选中着 → 它;最后点的是 diagnose 的卡片 → 那张卡片的 hit(hits 组),
 *    没进 hit 的(not_in_hit 组)是那个 event;
 * 2. 待选中 → 点下去的那个 event(还没定是哪次 hit);
 * 3. 看当家行:band → 那个 event;hits 行 → 那次 hit;样本行 → 那个样本;
 * 4. 没有当家行:框 → 样本 → event → hit(选框时配对的 hit 也亮着,框在前);
 * 5. 都没有 → 当前日。
 */
export function resolveTarget(s: PickState): CopyTarget {
  if (s.lastPick === 'feedback' && s.feedbackId) return { kind: 'feedback', id: s.feedbackId }
  if (s.lastPick === 'node' && s.node) return { kind: 'node', node: s.node }
  if (s.lastPick === 'card' && s.instanceId && s.candidateCount === 0) {
    return s.hitId ? { kind: 'hit', hitId: s.hitId } : { kind: 'event', instanceId: s.instanceId }
  }
  if (s.candidateCount > 0 && s.pendingInstanceId) return { kind: 'event', instanceId: s.pendingInstanceId }
  if (s.familyKind === 'band' && s.instanceId) return { kind: 'event', instanceId: s.instanceId }
  if (s.familyKind === 'bracket' && s.hitId) return { kind: 'hit', hitId: s.hitId }
  if (s.familyKind === 'external' && s.sampleId) return { kind: 'sample', id: s.sampleId }
  if (s.boxId) return { kind: 'box', id: s.boxId }
  if (s.sampleId) return { kind: 'sample', id: s.sampleId }
  if (s.instanceId) return { kind: 'event', instanceId: s.instanceId }
  if (s.hitId) return { kind: 'hit', hitId: s.hitId }
  if (s.feedbackId) return { kind: 'feedback', id: s.feedbackId }
  if (s.node) return { kind: 'node', node: s.node }
  return { kind: 'day' }
}

export interface CopyContext {
  symbol: string
  /** app 的 pattern(compare / app 模式);annotate 下是顶栏的当前 pattern,unsorted 为 null */
  pattern: string | null
  dates: readonly string[]
  currentDay: number | null
  hits: readonly HitDict[]
  events: readonly EventDict[]
  endNode: string | null
  nodeOrder: readonly string[]
  anchorFields: readonly string[]
  chart: AnnChart | null
  featureName: (fid: string | null) => string | null
}

const UNSORTED = 'unsorted'
const join = (...parts: (string | null | undefined | false)[]): string => parts.filter(Boolean).join(' ')
const span = (a: string, b: string): string => (a === b ? a : `${a}→${b}`)

/** 那样东西 → 从小到大的几行;对象已经不在(换了图、被删)时退成当前日那一行。 */
export function copyLadder(t: CopyTarget, c: CopyContext): string[] {
  const d = (i: number): string => c.dates[i] ?? String(i)
  const head = join(c.symbol, c.pattern)
  const dayLine = (): string[] => [join(head, c.currentDay != null && `day ${d(c.currentDay)}`)]

  if (t.kind === 'node') return [join(head, 'node', t.node)]

  if (t.kind === 'box') {
    const b = c.chart?.boxes.find(x => x.id === t.id)
    if (!b) return dayLine()
    return [join(c.symbol, 'box', c.featureName(b.feature) ?? 'unnamed', span(b.start, b.end), `[${b.id}]`)]
  }

  if (t.kind === 'sample') {
    const s = c.chart?.samples.find(x => x.id === t.id)
    if (!s) return dayLine()
    const letter = sampleLetters(c.chart, s.pattern).get(s.id)
    return [join(c.symbol, s.pattern ?? UNSORTED, 'sample', letter, s.judgment, s.date, `[${s.id}]`)]
  }

  if (t.kind === 'feedback') {
    const f = c.chart?.feedback?.find(x => x.id === t.id)
    if (!f) return dayLine()
    return [join(c.symbol, f.pattern, 'feedback', span(f.start, f.end),
                 f.nodes?.length ? `nodes ${f.nodes.join(',')}` : null, `[${f.id}]`)]
  }

  if (t.kind === 'event') {
    const e = c.events.find(x => x.instance_id === t.instanceId)
    if (!e) return dayLine()
    const out = [join(head, 'event', e.node_id, span(d(e.start_idx), d(e.end_idx)), `[${e.instance_id}]`)]
    const family = c.events.filter(x => x.node_id === e.node_id && x.start_idx === e.start_idx)
    if (family.length >= 2) out.push(join(head, 'event_family', e.node_id, 'start', d(e.start_idx)))
    return out
  }

  if (t.kind === 'hit') {
    const h = c.hits.find(x => x.hit_id === t.hitId)
    if (!h) return dayLine()
    const byId = new Map(c.events.map(e => [e.instance_id, e]))
    const byHit = new Map(c.hits.map(x => [x.hit_id, x]))
    const fam = foldHits(c.hits, c.events, c.endNode).find(f => f.hitIds.includes(h.hit_id))
    const buysOf = (id: string): number[] => { const m = byHit.get(id); return m ? buyDaysOf(m, byId, c.endNode) : [] }
    const sig = buysOf(h.hit_id).join(',')
    // 同一天的几次:同一族里买入日完全一样的(只差切法)
    const same = fam && sig ? fam.hitIds.filter(id => buysOf(id).join(',') === sig) : [h.hit_id]
    const k = same.indexOf(h.hit_id)
    const label = same.length >= 2
      ? hitLabels(same, byHit, byId, c.nodeOrder, c.anchorFields).map(l => formatMemberLabel(l, c.dates))[k]
      : null
    const out = [join(head, 'hit', span(d(h.start_idx), d(h.end_idx)),
                      same.length >= 2 && `${k + 1}/${same.length}`, label?.replace(' → ', '→'), `[${h.hit_id}]`)]
    if (same.length >= 2) {
      out.push(join(head, 'hits buy', buysOf(h.hit_id).map(d).join(','), `×${same.length}`, 'start', d(h.start_idx)))
    }
    if (fam && fam.hitIds.length > same.length) {
      const days = fam.buys.map(b => b.day)
      const buys = days.length ? `buys ${days.length === 1 ? d(days[0]) : `${d(days[0])}…${d(days[days.length - 1])}`}` : null
      out.push(join(head, 'hit_family start', d(fam.start), buys))
    }
    return out
  }

  return dayLine()
}
