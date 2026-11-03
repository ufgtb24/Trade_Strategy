/**
 * 样本与成员框在界面上的派生量(纯函数,不碰网络和界面):样本字母、样本的跨度、成员链、others 一排、
 * 选中框时的 member_of 一行、改起止时框终点的上限、副图上每个框的标记。
 *
 * 成员框一律取「样本存下的成员框里,还在这张图上、且在样本日当天或之前结束的」(membership.ts 的
 * currentMemberBoxes),与参照实现读存下的成员框是同一条。成员框的推断、空槽的规则在 membership.ts。
 *
 * 当前 pattern:顶栏 pattern 一格选的那个(null 为 unsorted)。字母、框旁的字母、member_of 里能点的行都按它算;
 * 别的 pattern 的样本照画,但画淡、只读。
 */
import {
  CROSSES_SAMPLE_DATE, UNCLAIMED, currentMemberBoxes, dupFeatures, emptySlots, memberTree,
  type Slot, type TreeNode,
} from './membership'
import type { AnnBox, AnnChart, AnnSample } from './model'

const byDate = (a: AnnSample, b: AnnSample) => (a.date < b.date ? -1 : a.date > b.date ? 1 : a.id < b.id ? -1 : 1)
/** 框的先后:起点早的在前,同起点长的在前,再按编号(日期字符串比,和按序号比的先后一致)。 */
const boxOrder = (a: AnnBox, b: AnnBox) =>
  a.start < b.start ? -1 : a.start > b.start ? 1 : a.end > b.end ? -1 : a.end < b.end ? 1 : a.id < b.id ? -1 : a.id > b.id ? 1 : 0

/** 样本现在的成员框编号(存下的、还在这张图上、在样本日当天或之前结束的)。 */
export function memberIds(smp: AnnSample, chart: AnnChart): Set<string> {
  return new Set(currentMemberBoxes(smp, chart.boxes).map(b => b.id))
}

/** 框终点晚于样本日、起点不晚于样本日:跨过样本日,收不进这个样本。 */
export function crosses(b: { start: string; end: string }, smp: { date: string }): boolean {
  return b.start <= smp.date && b.end > smp.date
}

/** 同一张图、当前 pattern 的样本按日期标 a、b、c(只有一个也标 a);别的 pattern 的样本不标。 */
export function sampleLetters(chart: AnnChart | null, pattern: string | null): Map<string, string> {
  const out = new Map<string, string>()
  if (!chart) return out
  chart.samples.filter(s => s.pattern === pattern).sort(byDate)
    .forEach((s, i) => out.set(s.id, i < 26 ? String.fromCharCode(97 + i) : `z${i - 25}`))
  return out
}

/** 样本的跨度(bracket 轨上的虚线):起点 = 样本日和成员框起点里最早的,终点 = 样本日。 */
export function sampleRange(smp: AnnSample, chart: AnnChart): { start: string; end: string } {
  let start = smp.date
  for (const b of currentMemberBoxes(smp, chart.boxes)) if (b.start < start) start = b.start
  return { start, end: smp.date }
}

/** 这张图上 pattern 为 null(unsorted)的样本有几个,全部图加起来。 */
export function unsortedCount(charts: readonly AnnChart[]): number {
  return charts.reduce((n, c) => n + c.samples.filter(s => s.pattern === null).length, 0)
}

// ── 成员链与 others ───────────────────────────────────────────────────

/** 成员链上的一格:成员框树的一个顶层结点(dup 表示顶层同一特征出现两次以上),或一个空槽。 */
export type ChainItem =
  | { kind: 'node'; node: TreeNode; dup: boolean }
  | { kind: 'slot'; slot: Slot }

/**
 * 样本的成员链:成员框树的顶层结点与空槽,按框的先后排在一起。days 是这张图的交易日;charts 是全部图
 * (空槽要看特征在这个 pattern 里出现过没有)。
 */
export function memberChain(smp: AnnSample, chart: AnnChart, charts: readonly AnnChart[],
                            days: readonly string[], near: number): ChainItem[] {
  const members = [...memberIds(smp, chart)]
  const tree = memberTree(members, chart.boxes, days)
  const dup = new Set(dupFeatures(members, chart.boxes, days))
  const byId = new Map(chart.boxes.map(b => [b.id, b]))
  const items: { box: AnnBox; item: ChainItem }[] = tree.map(node => {
    const box = byId.get(node.box)!
    return { box, item: { kind: 'node', node, dup: !!box.feature && dup.has(box.feature) } }
  })
  for (const slot of emptySlots(charts, chart.symbol, smp.id, days, near)) {
    items.push({ box: byId.get(slot.box)!, item: { kind: 'slot', slot } })
  }
  return items.sort((a, b) => boxOrder(a.box, b.box)).map(x => x.item)
}

export interface OtherBox { box: AnnBox; cand: boolean; cross: boolean }

/**
 * others 一排:起点不晚于样本日、不是它的成员框的框。画了没收的(unclaimed 空槽)排最前,跨过样本日的排最后
 * (收不进),其余按框的先后。slots 是这个样本的空槽。
 */
export function othersOf(smp: AnnSample, chart: AnnChart, slots: readonly Slot[]): OtherBox[] {
  const mine = memberIds(smp, chart)
  const cand = new Set(slots.filter(s => s.reason === UNCLAIMED).map(s => s.box))
  const rank = (o: OtherBox) => (o.cand ? 0 : o.cross ? 2 : 1)
  return chart.boxes.filter(b => b.start <= smp.date && !mine.has(b.id))
    .map(b => ({ box: b, cand: cand.has(b.id), cross: crosses(b, smp) }))
    .sort((p, q) => rank(p) - rank(q) || boxOrder(p.box, q.box))
}

// ── 选中框时:member_of 一行、改起止的上限 ────────────────────────────

/**
 * member_of 一行里的一个样本:
 * - member:收了这个框;当前 pattern 的可以点掉,别的 pattern 的只读(变淡);
 * - open:当前 pattern、样本日不早于框起点、还没收它,可以点上;
 * - crosses:当前 pattern、框跨过它的样本日,收不进(变灰)。
 */
export interface MemberOfRow { sample: AnnSample; state: 'member' | 'open' | 'crosses'; editable: boolean }

/** 选中框时 member_of 一行:收了它的全部样本(含别的 pattern 的),加上当前 pattern 里能收它的样本;按样本日排。 */
export function memberOfRows(box: AnnBox, chart: AnnChart, pattern: string | null): MemberOfRow[] {
  const rows: MemberOfRow[] = []
  for (const s of [...chart.samples].sort(byDate)) {
    const mine = s.pattern === pattern
    if (memberIds(s, chart).has(box.id)) rows.push({ sample: s, state: 'member', editable: mine })
    else if (mine && s.date >= box.start) {
      rows.push(crosses(box, s) ? { sample: s, state: 'crosses', editable: false } : { sample: s, state: 'open', editable: true })
    }
  }
  return rows
}

/**
 * 改起止时框终点最多到哪天:存下的成员框里有它的样本中,样本日最早的那个(没有为 null)。
 * 按存下的成员框算(不管眼下是否越界):保存时后端对「以它为成员的样本」逐个查,越过任何一个都会被拒。
 */
export function resizeLimit(boxId: string, chart: AnnChart): AnnSample | null {
  let best: AnnSample | null = null
  for (const s of chart.samples) if (s.members.includes(boxId) && (!best || s.date < best.date)) best = s
  return best
}

// ── 副图上的框标记 ────────────────────────────────────────────────────

/**
 * 副图上一个框的标记:
 * - owners:当前 pattern 里收了它的样本的字母(框左侧的小字母);
 * - away:只被别的 pattern 的样本收进(画淡);
 * - focus(选中样本时):member 是它的成员框(加粗)、cand 是画了没收(短虚线、右侧挂 ◂)、
 *   cross 是跨过样本日收不进的空槽(右侧挂 ⇥)、dim 是其余(画淡);没选中样本时为 null。
 */
export interface BoxMark { owners: string[]; away: boolean; focus: 'member' | 'cand' | 'cross' | 'dim' | null }

export function boxMarks(chart: AnnChart | null, pattern: string | null, selected: AnnSample | null,
                         slots: readonly Slot[]): Map<string, BoxMark> {
  const out = new Map<string, BoxMark>()
  if (!chart) return out
  const letters = sampleLetters(chart, pattern)
  const owners = new Map<string, string[]>()
  const inCur = new Set<string>(), inOther = new Set<string>()
  for (const s of [...chart.samples].sort(byDate)) {
    for (const id of memberIds(s, chart)) {
      if (s.pattern === pattern) {
        inCur.add(id)
        const l = letters.get(s.id)
        if (l) owners.set(id, [...(owners.get(id) ?? []), l])
      } else inOther.add(id)
    }
  }
  const focusMembers = selected ? memberIds(selected, chart) : null
  const slotOf = new Map(slots.map(s => [s.box, s.reason]))
  for (const b of chart.boxes) {
    let focus: BoxMark['focus'] = null
    if (focusMembers) {
      const r = slotOf.get(b.id)
      focus = focusMembers.has(b.id) ? 'member' : r === UNCLAIMED ? 'cand' : r === CROSSES_SAMPLE_DATE ? 'cross' : 'dim'
    }
    out.set(b.id, { owners: owners.get(b.id) ?? [], away: inOther.has(b.id) && !inCur.has(b.id), focus })
  }
  return out
}
