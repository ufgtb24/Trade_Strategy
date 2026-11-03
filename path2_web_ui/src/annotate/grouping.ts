/**
 * 归组与 pattern 页的派生量(纯函数,不碰网络和界面):一个 pattern(或 unsorted)的全部样本、unsorted 页按骨架
 * 分行、pattern 里各段的先后、features 区的块、计数与点开后的分排、打开样本时的图窗。
 *
 * 成员框一律经 membership.ts 的 currentMemberBoxes 取(存下的、还在这张图上、在样本日当天或之前结束的);
 * 骨架、成员框树也用 membership.ts 的实现(和参照实现过同一组例子)。算框套框要这张图的交易日:daysOf(symbol)
 * 给得出就用它,给不出(这张图还没打开过)用周一到周五代替(model.ts 的 daysFor;只差节假日,
 * 只在长短几乎一样的情形下可能换个所属的框)。
 *
 * 计数(决策票 15):
 * - 一律数样本,写成 pos k/N · neg m/M;点开后按同一划分分排,排头写 pos a · neg b,各排之和等于分母;0 也显示。
 * - in:分母是这个 pattern 的全部样本,分子是成员框里有这个特征的框(哪一层都算)的样本;点开分 in / not_in。
 * - 属性 true:分母是有这个特征的框的样本;一个样本收了几个这个特征的框时按「任一个」算:任一个 true 就算 true,
 *   都没判算 null,其余算 false(待验证,V-15-1);点开分 true / false / null。
 * - samples:页头按 judgment 各一个数,点开是那一排样本。
 */
import { currentMemberBoxes, memberTree, skeleton, type TreeNode } from './membership'
import { attrState, daysFor, sampleOrder, type AnnBox, type AnnChart, type AnnSample, type AnnState, type AttrState } from './model'
import type { ViewWindow } from '../types'

/** 一个样本连同它所在的图。 */
export interface PSample { sample: AnnSample; chart: AnnChart }
/** 一张图的交易日;给不出时为 null / undefined。 */
export type DaysOf = (symbol: string) => readonly string[] | null | undefined

/** pattern(null 为 unsorted)的全部样本:按股票代码、再按样本日排。 */
export function patternSamples(s: AnnState, pattern: string | null): PSample[] {
  const out: PSample[] = []
  for (const chart of s.charts) {
    for (const sample of [...chart.samples].sort(sampleOrder)) if (sample.pattern === pattern) out.push({ sample, chart })
  }
  return out
}

/** 样本现在的成员框,按框的先后(起点早的在前,同起点长的在前,再按编号)。 */
export function membersOf(x: PSample): AnnBox[] {
  return currentMemberBoxes(x.sample, x.chart.boxes).sort((a, b) =>
    a.start < b.start ? -1 : a.start > b.start ? 1 : a.end > b.end ? -1 : a.end < b.end ? 1 : a.id < b.id ? -1 : a.id > b.id ? 1 : 0)
}

function memberIdsOf(x: PSample): string[] {
  return currentMemberBoxes(x.sample, x.chart.boxes).map(b => b.id)
}

/** 样本的骨架:成员框树顶层框的特征编号按先后排(还没标特征的为 null);子框和属性不进骨架。 */
export function sampleSkeleton(x: PSample, daysOf: DaysOf): (string | null)[] {
  return skeleton(memberIdsOf(x), x.chart.boxes, daysFor(x.chart.boxes, daysOf(x.chart.symbol)))
}

/** 样本的成员框树(框套框只在成员框之间找)。 */
export function sampleTree(x: PSample, daysOf: DaysOf): TreeNode[] {
  return memberTree(memberIdsOf(x), x.chart.boxes, daysFor(x.chart.boxes, daysOf(x.chart.symbol)))
}

// ── unsorted 页:按骨架分行 ────────────────────────────────────────────

/** unsorted 页的一行:judgment 与骨架都相同的样本。 */
export interface SkeletonRow { judgment: AnnSample['judgment']; skeleton: (string | null)[]; samples: PSample[] }

/**
 * unsorted 的样本按(judgment、骨架)分行。行序:骨架按特征名逐个比(名字按字符比,短的前缀排在前面,
 * 于是只差尾巴的几行挨着),没有成员框的排最后;同一骨架 pos 在 neg 前。nameOf 给特征名(还没起名的为 null)。
 */
export function unsortedRows(s: AnnState, daysOf: DaysOf, nameOf: (fid: string | null) => string | null): SkeletonRow[] {
  const rows = new Map<string, SkeletonRow>()
  for (const x of patternSamples(s, null)) {
    const sk = sampleSkeleton(x, daysOf)
    const key = JSON.stringify([x.sample.judgment, sk])
    if (!rows.has(key)) rows.set(key, { judgment: x.sample.judgment, skeleton: sk, samples: [] })
    rows.get(key)!.samples.push(x)
  }
  const names = (r: SkeletonRow) => r.skeleton.map(f => nameOf(f) ?? '')
  const cmp = (p: SkeletonRow, q: SkeletonRow) => {
    if (!p.skeleton.length !== !q.skeleton.length) return p.skeleton.length ? -1 : 1
    const a = names(p), b = names(q)
    for (let i = 0; i < Math.min(a.length, b.length); i++) if (a[i] !== b[i]) return a[i] < b[i] ? -1 : 1
    if (a.length !== b.length) return a.length - b.length
    const k = JSON.stringify(p.skeleton), l = JSON.stringify(q.skeleton)
    if (k !== l) return k < l ? -1 : 1
    return p.judgment === q.judgment ? 0 : p.judgment === 'pos' ? -1 : 1
  }
  return [...rows.values()].sort(cmp)
}

// ── pattern 里各段的先后 ──────────────────────────────────────────────

/**
 * 一组样本(一个 pattern 的全部样本)里各特征的先后,特征编号 → 名次(0 起)。annotate 的轨序和 features 区共用。
 * 两两比先后:两个特征同在一个样本的成员框里时,谁在前的次数多谁排前(成员框按框的先后排,子框也算)。
 * 每次从剩下的特征里取「没有谁多数时候排在它前面」的,有几个就取在样本里平均位置(0 = 最前、1 = 最后)
 * 最靠前的;从没同时出现过的也按平均位置定;先后互相矛盾(成环)时在剩下的全部里按平均位置取。
 * 还一样就按特征编号。不取平均位置直接排,是因为骨架长短不一时平均位置会被拉偏。
 */
export function featureOrder(samples: readonly PSample[]): Map<string, number> {
  const before = new Map<string, Map<string, number>>()
  const pos = new Map<string, number[]>()
  for (const x of samples) {
    const fs = membersOf(x).map(b => b.feature).filter((f): f is string => f !== null)
    fs.forEach((f, i) => {
      if (!pos.has(f)) pos.set(f, [])
      pos.get(f)!.push(fs.length > 1 ? i / (fs.length - 1) : 0)
      for (const g of fs.slice(i + 1)) if (g !== f) {
        if (!before.has(f)) before.set(f, new Map())
        before.get(f)!.set(g, (before.get(f)!.get(g) ?? 0) + 1)
      }
    })
  }
  const n = (a: string, b: string) => before.get(a)?.get(b) ?? 0
  const avg = (f: string) => { const v = pos.get(f)!; return v.reduce((p, q) => p + q, 0) / v.length }
  const left = new Set(pos.keys())
  const out = new Map<string, number>()
  while (left.size) {
    const ks = [...left]
    let cand = ks.filter(k => ks.every(m => m === k || n(m, k) <= n(k, m)))
    if (!cand.length) cand = ks
    const k = cand.sort((a, b) => avg(a) - avg(b) || (a < b ? -1 : a > b ? 1 : 0))[0]
    out.set(k, out.size)
    left.delete(k)
  }
  return out
}

// ── features 区 ──────────────────────────────────────────────────────

/** features 区的一块:一个特征,以及在它的框里当过子框的特征(挂在它下面,写 ⊃)。 */
export interface FeatureBlock { feature: string; kids: FeatureBlock[] }

/**
 * features 区:全部样本(正、负都算)成员框树里出现过的顶层特征,按 order 排;在某个特征的框里当过子框的特征
 * 挂在那一块下面(一层层往下),也按 order 排。还没标特征的框不成块,它下面的子框也不收。
 * 同一个特征可以既是顶层块、又挂在别的块下面;一块下面不再挂它的上层(防成环)。
 */
export function featureBlocks(samples: readonly PSample[], daysOf: DaysOf, order: ReadonlyMap<string, number>): FeatureBlock[] {
  const tops = new Set<string>()
  const kidsOf = new Map<string, Set<string>>()
  const featureById = (x: PSample) => new Map(x.chart.boxes.map(b => [b.id, b.feature]))
  for (const x of samples) {
    const fid = featureById(x)
    const walk = (node: TreeNode) => {
      const f = fid.get(node.box) ?? null
      if (f === null) return
      for (const k of node.kids) {
        const g = fid.get(k.box) ?? null
        if (g === null) continue
        if (!kidsOf.has(f)) kidsOf.set(f, new Set())
        kidsOf.get(f)!.add(g)
        walk(k)
      }
    }
    for (const node of sampleTree(x, daysOf)) {
      const f = fid.get(node.box) ?? null
      if (f === null) continue
      tops.add(f)
      walk(node)
    }
  }
  const rank = (f: string) => order.get(f) ?? Number.POSITIVE_INFINITY
  const sorted = (fs: Iterable<string>) => [...fs].sort((a, b) =>
    rank(a) !== rank(b) ? (rank(a) < rank(b) ? -1 : 1) : a < b ? -1 : a > b ? 1 : 0)
  const block = (f: string, path: readonly string[]): FeatureBlock => ({
    feature: f,
    kids: sorted(kidsOf.get(f) ?? []).filter(g => g !== f && !path.includes(g)).map(g => block(g, [...path, f])),
  })
  return sorted(tops).map(f => block(f, []))
}

/** 这组样本的成员框里,这个特征的框判过(true 或 false)的属性,按第一次出现的先后。 */
export function attrsUsed(samples: readonly PSample[], fid: string): string[] {
  const out: string[] = []
  for (const x of samples) for (const b of membersOf(x)) if (b.feature === fid) {
    for (const k of Object.keys(b.attrs ?? {})) if (!out.includes(k)) out.push(k)
  }
  return out
}

// ── 计数与分排 ────────────────────────────────────────────────────────

/** 样本的成员框里有没有这个特征的框(哪一层都算)。 */
export function hasFeature(x: PSample, fid: string): boolean {
  return membersOf(x).some(b => b.feature === fid)
}

/** 样本上「这个特征的框的这个属性」:任一个 true 就算 true,都没判算 null,其余算 false(待验证,V-15-1)。 */
export function attrOf(x: PSample, fid: string, wid: string): AttrState {
  const ss = membersOf(x).filter(b => b.feature === fid).map(b => attrState(b, wid))
  return ss.includes('true') ? 'true' : ss.every(v => v === 'null') ? 'null' : 'false'
}

/** 一个能点开的计数:samples(按 judgment)、in(有没有这个特征的框)、attr(这个特征的框的属性)。 */
export type CountKey =
  | { kind: 'samples'; judgment: AnnSample['judgment'] }
  | { kind: 'in'; feature: string }
  | { kind: 'attr'; feature: string; attr: string }

/** 计数的编号:界面上记「点开的是哪个数」用。 */
export function countId(k: CountKey): string {
  return k.kind === 'samples' ? `samples|${k.judgment}` : k.kind === 'in' ? `in|${k.feature}` : `attr|${k.feature}|${k.attr}`
}

/** 点开后的一排:排名(pos、neg、in、not_in、true、false、null)和这一排的样本(正样本在前)。 */
export interface Part { label: 'pos' | 'neg' | 'in' | 'not_in' | AttrState; samples: PSample[] }

const posFirst = (xs: PSample[]) => [...xs.filter(x => x.sample.judgment === 'pos'), ...xs.filter(x => x.sample.judgment !== 'pos')]

/** 这个计数的分母:samples 与 in 是全部样本;attr 是有这个特征的框的样本。 */
export function denominator(samples: readonly PSample[], k: CountKey): PSample[] {
  if (k.kind === 'samples') return samples.filter(x => x.sample.judgment === k.judgment)
  if (k.kind === 'in') return [...samples]
  return samples.filter(x => hasFeature(x, k.feature))
}

/** 点开后的分排:各排是分母的一个划分(各排之和等于分母),空的排也在。第一排就是汇总里的分子。 */
export function countParts(samples: readonly PSample[], k: CountKey): Part[] {
  const ys = denominator(samples, k)
  if (k.kind === 'samples') return [{ label: k.judgment, samples: ys }]
  if (k.kind === 'in') {
    return [{ label: 'in', samples: posFirst(ys.filter(x => hasFeature(x, k.feature))) },
            { label: 'not_in', samples: posFirst(ys.filter(x => !hasFeature(x, k.feature))) }]
  }
  return (['true', 'false', 'null'] as const).map(v => ({
    label: v, samples: posFirst(ys.filter(x => attrOf(x, k.feature, k.attr) === v)),
  }))
}

/** pos 与 neg 各有几个。 */
export function byJudgment(xs: readonly PSample[]): { pos: number; neg: number } {
  let pos = 0, neg = 0
  for (const x of xs) if (x.sample.judgment === 'pos') pos++; else neg++
  return { pos, neg }
}

/** 汇总的比例:分子是第一排(in、true),分母见 denominator。pos k/N · neg m/M。 */
export interface Ratio { pos: number; posOf: number; neg: number; negOf: number }

export function countRatio(samples: readonly PSample[], k: CountKey): Ratio {
  const all = byJudgment(denominator(samples, k))
  const hit = byJudgment(countParts(samples, k)[0].samples)
  return { pos: hit.pos, posOf: all.pos, neg: hit.neg, negOf: all.neg }
}

// ── 打开样本 ─────────────────────────────────────────────────────────

const shiftDays = (d: string, n: number) => {
  const t = new Date(`${d}T00:00:00Z`)
  t.setUTCDate(t.getUTCDate() + n)
  return t.toISOString().slice(0, 10)
}

/** 打开样本时的图窗:样本的跨度(成员框最早的起点到样本日)前后各留约两个月(按日历日)。 */
export function sampleWindow(x: PSample): ViewWindow {
  let start = x.sample.date
  for (const b of currentMemberBoxes(x.sample, x.chart.boxes)) if (b.start < start) start = b.start
  return { start: shiftDays(start, -60), end: shiftDays(x.sample.date, 60) }
}
